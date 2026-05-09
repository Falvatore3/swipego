#!/usr/bin/env python3
"""
Phase 1: Fetch gallery URLs for Bangkok POIs from Wikimedia Commons.

This script is the fast collection pass. It:
  - Queries Commons search API by keyword (name_en + Bangkok + alts).
  - For each File: title, uses imageinfo to confirm existence + MIME + size.
  - Builds the 1280px thumbnail URL.
  - Writes to JSON without HTTP-verifying each CDN URL (run verify_poi_images.py
    after this, which throttles heavily to dodge 429s).

The API response already tells us the file exists & MIME is image/*; the URL
construction is deterministic (md5 hash of filename). So this is essentially
correct; verify pass just hardens against rare edge cases.
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
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
SLEEP_API = 0.4

SKIP_KEYWORDS = [
    "logo", "coat_of_arms", "map_of", "satellite", "seal_of",
    "flag_of", "location_map", "coat of arms",
    "seal ", "crest_", "stamp_of", "logo_",
]
ALLOWED_EXT = (".jpg", ".jpeg", ".png", ".webp")


def http_json(params: dict, retries: int = 4) -> Optional[dict]:
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


def filename_from_title(t: str) -> str:
    s = t[5:] if t.startswith("File:") else t
    return s.replace(" ", "_")


def build_thumb_url(filename: str, width: int = 1280) -> str:
    h = hashlib.md5(filename.encode("utf-8")).hexdigest()
    a, ab = h[0], h[:2]
    enc = urllib.parse.quote(filename)
    return f"https://upload.wikimedia.org/wikipedia/commons/thumb/{a}/{ab}/{enc}/{width}px-{enc}"


def search_commons(keyword: str, limit: int = 15) -> List[str]:
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


def is_good_filename(t: str) -> bool:
    low = t.lower()
    if any(k in low for k in SKIP_KEYWORDS):
        return False
    if not any(low.endswith(ext) for ext in ALLOWED_EXT):
        return False
    return True


def collect_for_poi(poi: Dict, target_max: int = 7) -> List[str]:
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

    good_titles = [t for t in titles if is_good_filename(t)]
    print(f"    raw={len(titles)} good={len(good_titles)}", flush=True)

    urls: List[str] = []
    seen_urls = set()
    for title in good_titles:
        if len(urls) >= target_max:
            break
        info = get_image_info(title)
        time.sleep(SLEEP_API)
        if not info:
            continue
        # Skip very small images (likely icons)
        if info.get("width", 0) and info["width"] < 800:
            continue
        fname = filename_from_title(title)
        url = build_thumb_url(fname, 1280)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        urls.append(url)

    return urls[:target_max]


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
            print(f"[{idx+1}/{total}] {poi['id']} skip (has {len(existing)})", flush=True)
            continue
        print(f"[{idx+1}/{total}] {poi['id']} {poi['name_en']}", flush=True)
        try:
            urls = collect_for_poi(poi)
        except Exception as e:
            print(f"    !! {e}", file=sys.stderr, flush=True)
            urls = []
        print(f"    => {len(urls)} urls", flush=True)
        poi["gallery"] = urls

        if (idx + 1 - start_idx) % 5 == 0:
            write_checkpoint(doc)

    write_checkpoint(doc)

    # Summary
    print("\n===== COLLECT SUMMARY =====", flush=True)
    ok = 0
    for poi in pois:
        n = len(poi.get("gallery") or [])
        if n >= 5:
            ok += 1
        print(f"  {poi['id']} {n:2}  {poi['name_en'][:50]}", flush=True)
    print(f"\n{ok}/{len(pois)} POIs have >=5 images", flush=True)


if __name__ == "__main__":
    main()
