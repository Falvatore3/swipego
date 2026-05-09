#!/usr/bin/env python3
"""
Fetch and verify gallery images for Bangkok POIs from Wikimedia Commons.

Strategy:
  1. For each POI, query Commons search API using name_en + "Bangkok".
  2. Collect candidate File: titles, resolve each to direct upload.wikimedia.org URL.
  3. HEAD/GET verify content-type starts with image/.
  4. Keep 5-7 per POI; write back to JSON preserving all other fields.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from typing import List, Dict, Optional

POI_FILE = "/Users/frankie/WorkBuddy/2026-05-08-task-2/swipego/data/bangkok-pois.json"

UA = "Mozilla/5.0 (compatible; SwipeGoBot/1.0; +https://swipego.local)"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
SLEEP = 0.4


def http_json(url: str, params: dict, retries: int = 3) -> Optional[dict]:
    full = url + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(full, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if attempt == retries - 1:
                print(f"    !! http_json failed: {e}", file=sys.stderr)
                return None
            time.sleep(1.0 * (attempt + 1))
    return None


def verify_image(url: str, timeout: int = 12) -> bool:
    """HEAD first; fall back to GET 1 byte. Accept only 2xx + image/* content-type."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA}, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if 200 <= r.status < 300:
                ct = r.headers.get("Content-Type", "").lower()
                if ct.startswith("image/"):
                    return True
    except Exception:
        pass
    # GET fallback
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Range": "bytes=0-1024"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if 200 <= r.status < 300:
                ct = r.headers.get("Content-Type", "").lower()
                if ct.startswith("image/"):
                    return True
    except Exception:
        pass
    return False


def search_commons(keyword: str, limit: int = 20) -> List[str]:
    """Return a list of File: titles that match the keyword."""
    data = http_json(COMMONS_API, {
        "action": "query",
        "list": "search",
        "srsearch": keyword,
        "srnamespace": 6,  # File namespace
        "srlimit": limit,
        "format": "json",
    })
    if not data:
        return []
    hits = data.get("query", {}).get("search", []) or []
    return [h["title"] for h in hits]


def get_image_url(title: str) -> Optional[str]:
    """Resolve a File:xxx title to direct image URL via imageinfo."""
    data = http_json(COMMONS_API, {
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
        if url and mime.startswith("image/"):
            # Filter out svg/tif/gif if possible; prefer jpg/jpeg/png/webp
            if any(url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                return url
            # still return if it is image/* but not preferred ext
            # (some Commons files have odd urls)
    return None


def collect_for_poi(poi: Dict, target_min: int = 6, target_max: int = 7) -> List[str]:
    """Return a list of verified image URLs for this POI."""
    name_en = poi["name_en"]
    category = poi.get("category", "")
    # Build keyword candidates
    keywords = []
    primary = f"{name_en} Bangkok"
    keywords.append(primary)
    # Add alt spellings / subject-specific
    if "(" in name_en:
        base = name_en.split("(")[0].strip()
        if base:
            keywords.append(f"{base} Bangkok")
    if category in ("landmark", "art"):
        keywords.append(name_en)
    # For hidden/market/nightlife also search the district
    dist = poi.get("district", "")
    if dist and category in ("hidden", "market", "nightlife"):
        keywords.append(f"{name_en} {dist}")

    seen_titles = set()
    titles: List[str] = []
    for kw in keywords:
        for t in search_commons(kw, limit=15):
            if t not in seen_titles:
                seen_titles.add(t)
                titles.append(t)
        time.sleep(SLEEP)
        if len(titles) >= 25:
            break

    print(f"    candidates: {len(titles)}")
    if not titles:
        return []

    verified: List[str] = []
    for title in titles:
        if len(verified) >= target_max:
            break
        url = get_image_url(title)
        time.sleep(SLEEP)
        if not url:
            continue
        # skip obvious icons/maps
        low = url.lower()
        if any(bad in low for bad in ["logo", "icon_", "flag", "coat_of_arms", "map_of"]):
            continue
        if verify_image(url):
            verified.append(url)
            print(f"    OK: {url.split('/')[-1][:80]}")
        else:
            print(f"    SKIP: {url.split('/')[-1][:80]}")

    return verified[:target_max]


def main():
    with open(POI_FILE, "r", encoding="utf-8") as f:
        doc = json.load(f)

    pois = doc["pois"]
    total = len(pois)
    start_idx = int(os.environ.get("START_IDX", "0"))
    end_idx = int(os.environ.get("END_IDX", str(total)))

    for idx in range(start_idx, end_idx):
        poi = pois[idx]
        if poi.get("gallery") and len(poi["gallery"]) >= 5:
            print(f"[{idx+1}/{total}] {poi['id']} {poi['name_en']} -- already has {len(poi['gallery'])} imgs, skip")
            continue
        print(f"[{idx+1}/{total}] {poi['id']} {poi['name_en']}")
        urls = collect_for_poi(poi)
        print(f"    -> got {len(urls)} verified URLs")
        poi["gallery"] = urls

        # Checkpoint every 5 POI
        if (idx + 1) % 5 == 0 or idx == end_idx - 1:
            with open(POI_FILE, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=2)
            print(f"    >> checkpoint written at idx {idx+1}")

    # Final write
    with open(POI_FILE, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    # Summary
    print("\n===== SUMMARY =====")
    for poi in pois:
        n = len(poi.get("gallery") or [])
        status = "OK" if n >= 5 else "LOW"
        print(f"{poi['id']:8}  {n:2}  {status}  {poi['name_en'][:40]}")


if __name__ == "__main__":
    main()
