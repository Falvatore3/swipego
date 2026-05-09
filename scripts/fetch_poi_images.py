#!/usr/bin/env python3
"""
Fetch and verify gallery images for Bangkok POIs from Wikimedia Commons.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from typing import List, Dict, Optional

POI_FILE = "/Users/frankie/WorkBuddy/2026-05-08-task-2/swipego/data/bangkok-pois.json"

# UA for Wikimedia API (must identify the bot per their policy)
UA_API = "SwipeGoBot/1.0 (https://swipego.local/; contact@swipego.local) python-urllib/3.9"
# UA for upload.wikimedia.org image CDN (browser-like works best)
UA_IMG = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
SLEEP_API = 0.5
SLEEP_VERIFY = 0.2

# Keywords to skip when they appear in filename
SKIP_KEYWORDS = [
    "logo", "coat_of_arms", "map_of", "satellite", "seal_of",
    "flag_of", "location_map", "coat of arms", "svg",
]


def strip_query(u: str) -> str:
    """Wikimedia adds utm params that cause 403 on upload.wikimedia.org; strip."""
    if "?" in u:
        return u.split("?", 1)[0]
    return u


def http_json(params: dict, retries: int = 3) -> Optional[dict]:
    full = COMMONS_API + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(full, headers={
                "User-Agent": UA_API,
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if attempt == retries - 1:
                print(f"    !! API failed: {e}", file=sys.stderr)
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def verify_image(url: str, timeout: int = 12) -> bool:
    """HEAD then fallback to GET range. Accept only 2xx + image/*."""
    url = strip_query(url)
    # HEAD
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA_IMG, "Accept": "image/*",
        }, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if 200 <= r.status < 300:
                ct = (r.headers.get("Content-Type") or "").lower()
                if ct.startswith("image/"):
                    return True
    except Exception:
        pass
    # GET small range fallback
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA_IMG, "Accept": "image/*",
            "Range": "bytes=0-2047",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if 200 <= r.status < 300:
                ct = (r.headers.get("Content-Type") or "").lower()
                if ct.startswith("image/"):
                    return True
    except Exception:
        pass
    return False


def search_commons(keyword: str, limit: int = 20) -> List[str]:
    data = http_json({
        "action": "query",
        "list": "search",
        "srsearch": keyword,
        "srnamespace": 6,
        "srlimit": limit,
        "format": "json",
    })
    if not data:
        return []
    hits = data.get("query", {}).get("search", []) or []
    return [h["title"] for h in hits]


def get_image_url(title: str) -> Optional[str]:
    data = http_json({
        "action": "query",
        "titles": title,
        "prop": "imageinfo",
        "iiprop": "url|mime|size",
        "format": "json",
    })
    if not data:
        return None
    pages = data.get("query", {}).get("pages", {})
    for _, page in pages.items():
        infos = page.get("imageinfo") or []
        if not infos:
            continue
        info = infos[0]
        mime = (info.get("mime") or "").lower()
        url = info.get("url")
        if not url or not mime.startswith("image/"):
            continue
        url = strip_query(url)
        low = url.lower()
        # skip svg/gif/tiff
        if any(low.endswith(ext) for ext in [".svg", ".tif", ".tiff", ".gif"]):
            continue
        return url
    return None


def collect_for_poi(poi: Dict, target_min: int = 6, target_max: int = 7) -> List[str]:
    name_en = poi["name_en"]
    category = poi.get("category", "")
    # Keyword candidates
    keywords: List[str] = []
    keywords.append(f"{name_en} Bangkok")
    if "(" in name_en:
        base = name_en.split("(")[0].strip()
        if base and base != name_en:
            keywords.append(f"{base} Bangkok")
    keywords.append(name_en)

    # Category-specific seeding
    if category in ("hidden", "market"):
        dist = poi.get("district", "")
        if dist:
            keywords.append(f"{name_en} {dist}")

    seen = set()
    titles: List[str] = []
    for kw in keywords:
        if kw in seen:
            continue
        seen.add(kw)
        for t in search_commons(kw, limit=18):
            if t not in titles:
                titles.append(t)
        time.sleep(SLEEP_API)
        if len(titles) >= 28:
            break

    print(f"    candidates: {len(titles)}")
    if not titles:
        return []

    verified: List[str] = []
    seen_urls = set()
    for title in titles:
        if len(verified) >= target_max:
            break
        # Skip obvious non-content
        low_title = title.lower()
        if any(kw in low_title for kw in SKIP_KEYWORDS):
            continue
        url = get_image_url(title)
        time.sleep(SLEEP_API)
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        # Extra filter on URL path
        if any(kw in url.lower() for kw in SKIP_KEYWORDS):
            continue
        if verify_image(url):
            verified.append(url)
            time.sleep(SLEEP_VERIFY)
    return verified[:target_max]


def write_checkpoint(doc):
    with open(POI_FILE, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)


def main():
    with open(POI_FILE, "r", encoding="utf-8") as f:
        doc = json.load(f)

    pois = doc["pois"]
    total = len(pois)
    start_idx = int(os.environ.get("START_IDX", "0"))
    end_idx = int(os.environ.get("END_IDX", str(total)))
    force = os.environ.get("FORCE", "0") == "1"

    for idx in range(start_idx, end_idx):
        poi = pois[idx]
        existing = poi.get("gallery") or []
        if not force and len(existing) >= 5:
            print(f"[{idx+1}/{total}] {poi['id']} {poi['name_en']} -- has {len(existing)}, skip")
            continue
        print(f"[{idx+1}/{total}] {poi['id']} {poi['name_en']}")
        try:
            urls = collect_for_poi(poi)
        except Exception as e:
            print(f"    !! exception: {e}", file=sys.stderr)
            urls = []
        print(f"    -> verified {len(urls)} URLs")
        poi["gallery"] = urls

        if (idx + 1 - start_idx) % 5 == 0:
            write_checkpoint(doc)
            print(f"    >> checkpoint at {idx+1}")

    write_checkpoint(doc)

    print("\n===== SUMMARY =====")
    ok = 0
    for poi in pois:
        n = len(poi.get("gallery") or [])
        status = "OK " if n >= 5 else "LOW"
        if n >= 5:
            ok += 1
        print(f"{poi['id']:8}  {n:2}  {status}  {poi['name_en'][:40]}")
    print(f"\n{ok}/{len(pois)} POIs have >=5 images")


if __name__ == "__main__":
    main()
