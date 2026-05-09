#!/usr/bin/env python3
"""
Fetch and verify gallery images for Bangkok POIs from Wikimedia Commons.

Strategy:
  1. Query Commons search API by keyword (name_en + Bangkok + alts).
  2. For each File: title, use imageinfo to confirm existence + mime.
  3. Build the 1280px thumbnail URL on upload.wikimedia.org CDN.
  4. Verify each candidate URL via HTTP GET (image/*) with:
     - Browser-like headers + Referer
     - 1.2s throttle between img requests
     - 429 backoff: wait 30s then retry up to 3 times
"""

import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from typing import List, Dict, Optional

POI_FILE = "/Users/frankie/WorkBuddy/2026-05-08-task-2/swipego/data/bangkok-pois.json"

UA_API = "SwipeGoBot/1.0 (https://swipego.local/; contact@swipego.local) python-urllib/3.9"
UA_IMG = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

COMMONS_API = "https://commons.wikimedia.org/w/api.php"

SLEEP_API = 0.6
SLEEP_IMG = 1.2

SKIP_KEYWORDS = [
    "logo", "coat_of_arms", "map_of", "satellite", "seal_of",
    "flag_of", "location_map", "coat of arms",
    "seal ", "crest_", "stamp_of",
]
ALLOWED_EXT = (".jpg", ".jpeg", ".png", ".webp")


def http_json(params: dict, retries: int = 3) -> Optional[dict]:
    full = COMMONS_API + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(full, headers={
                "User-Agent": UA_API,
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if attempt == retries - 1:
                print(f"    !! API err: {e}", file=sys.stderr, flush=True)
                return None
            time.sleep(3.0 * (attempt + 1))
    return None


def filename_from_title(title: str) -> str:
    s = title[5:] if title.startswith("File:") else title
    return s.replace(" ", "_")


def build_thumb_url(filename: str, width: int = 1280) -> str:
    h = hashlib.md5(filename.encode("utf-8")).hexdigest()
    a, ab = h[0], h[:2]
    enc = urllib.parse.quote(filename)
    return f"https://upload.wikimedia.org/wikipedia/commons/thumb/{a}/{ab}/{enc}/{width}px-{enc}"


def build_original_url(filename: str) -> str:
    h = hashlib.md5(filename.encode("utf-8")).hexdigest()
    a, ab = h[0], h[:2]
    enc = urllib.parse.quote(filename)
    return f"https://upload.wikimedia.org/wikipedia/commons/{a}/{ab}/{enc}"


def search_commons(keyword: str, limit: int = 18) -> List[str]:
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
    return [h["title"] for h in (data.get("query", {}).get("search") or [])]


def get_image_info(title: str) -> Optional[Dict]:
    data = http_json({
        "action": "query",
        "titles": title,
        "prop": "imageinfo",
        "iiprop": "url|mime|size",
        "format": "json",
    })
    if not data:
        return None
    for _, page in (data.get("query", {}).get("pages") or {}).items():
        infos = page.get("imageinfo") or []
        if not infos:
            continue
        info = infos[0]
        mime = (info.get("mime") or "").lower()
        if not mime.startswith("image/"):
            continue
        return {
            "mime": mime,
            "width": info.get("width", 0),
            "height": info.get("height", 0),
        }
    return None


def verify_url(url: str, max_retries: int = 3) -> bool:
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA_IMG,
                "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://commons.wikimedia.org/",
            })
            with urllib.request.urlopen(req, timeout=20) as r:
                if 200 <= r.status < 300:
                    ct = (r.headers.get("Content-Type") or "").lower()
                    if ct.startswith("image/"):
                        # Read a couple KB to confirm the body starts
                        r.read(256)
                        return True
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 20 * (attempt + 1)
                print(f"    ! 429 backoff {wait}s", flush=True)
                time.sleep(wait)
                continue
            if e.code in (404, 400):
                return False
        except Exception:
            pass
        time.sleep(2.0 * (attempt + 1))
    return False


def is_good_filename(title: str) -> bool:
    low = title.lower()
    if any(k in low for k in SKIP_KEYWORDS):
        return False
    if not any(low.endswith(ext) for ext in ALLOWED_EXT):
        return False
    return True


def collect_for_poi(poi: Dict, target_max: int = 7, target_min: int = 5) -> List[str]:
    name_en = poi["name_en"]
    category = poi.get("category", "")

    keywords: List[str] = []
    keywords.append(f"{name_en} Bangkok")
    if "(" in name_en:
        base = name_en.split("(")[0].strip()
        if base and base != name_en:
            keywords.append(f"{base} Bangkok")
    keywords.append(name_en)
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
        ts = search_commons(kw, limit=15)
        for t in ts:
            if t not in titles:
                titles.append(t)
        time.sleep(SLEEP_API)
        if len(titles) >= 22:
            break

    print(f"    raw: {len(titles)}", flush=True)
    good_titles = [t for t in titles if is_good_filename(t)]

    verified: List[str] = []
    for title in good_titles:
        if len(verified) >= target_max:
            break
        info = get_image_info(title)
        time.sleep(SLEEP_API)
        if not info:
            continue
        if info.get("width", 0) and info["width"] < 800:
            continue
        fname = filename_from_title(title)
        url = build_thumb_url(fname, 1280)
        if verify_url(url):
            verified.append(url)
            print(f"    OK  {fname[:70]}", flush=True)
        else:
            # Try original URL as fallback
            orig = build_original_url(fname)
            if verify_url(orig):
                verified.append(orig)
                print(f"    OK* {fname[:70]}", flush=True)
            else:
                print(f"    XX  {fname[:70]}", flush=True)
        time.sleep(SLEEP_IMG)

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
    force = os.environ.get("FORCE", "1") == "1"

    for idx in range(start_idx, end_idx):
        poi = pois[idx]
        existing = poi.get("gallery") or []
        if not force and len(existing) >= 5:
            print(f"[{idx+1}/{total}] {poi['id']} skip (has {len(existing)})", flush=True)
            continue
        print(f"\n[{idx+1}/{total}] {poi['id']} {poi['name_en']}", flush=True)
        try:
            urls = collect_for_poi(poi)
        except Exception as e:
            print(f"    !! exception: {e}", file=sys.stderr, flush=True)
            urls = []
        print(f"    => {len(urls)} verified", flush=True)
        poi["gallery"] = urls

        if (idx + 1 - start_idx) % 5 == 0:
            write_checkpoint(doc)
            print(f"    >> checkpoint @ {idx+1}", flush=True)

    write_checkpoint(doc)

    print("\n===== SUMMARY =====", flush=True)
    ok = 0
    for poi in pois:
        n = len(poi.get("gallery") or [])
        status = "OK " if n >= 5 else "LOW"
        if n >= 5:
            ok += 1
        print(f"{poi['id']:8}  {n:2}  {status}  {poi['name_en'][:40]}", flush=True)
    print(f"\n{ok}/{len(pois)} POIs have >=5 images", flush=True)


if __name__ == "__main__":
    main()
