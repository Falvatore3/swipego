#!/usr/bin/env python3
"""
Phase 2: Verify gallery URLs for Bangkok POIs.

Reads the POI JSON, GET-verifies each gallery URL, drops failures, and
writes a report. Throttles aggressively on 429 backoff.
"""

import json
import os
import sys
import time
import urllib.request
from typing import List

POI_FILE = "/Users/frankie/WorkBuddy/2026-05-08-task-2/swipego/data/bangkok-pois.json"

UA_IMG = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

SLEEP_OK = 1.0       # between successful requests
SLEEP_429 = 30.0     # after 429
MAX_RETRIES_429 = 3


def verify_url(url: str) -> bool:
    for attempt in range(MAX_RETRIES_429 + 1):
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
                        r.read(256)
                        return True
                    else:
                        return False
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < MAX_RETRIES_429:
                wait = SLEEP_429 * (attempt + 1)
                print(f"    ! 429 retry {attempt+1}, wait {wait}s", flush=True)
                time.sleep(wait)
                continue
            return False
        except Exception as e:
            if attempt < MAX_RETRIES_429:
                time.sleep(3)
                continue
            return False
    return False


def main():
    with open(POI_FILE, "r", encoding="utf-8") as f:
        doc = json.load(f)

    pois = doc["pois"]
    total = len(pois)
    start_idx = int(os.environ.get("START_IDX", "0"))
    end_idx = int(os.environ.get("END_IDX", str(total)))

    all_ok = 0
    all_total = 0
    for idx in range(start_idx, end_idx):
        poi = pois[idx]
        gallery = poi.get("gallery") or []
        if not gallery:
            continue
        print(f"[{idx+1}/{total}] {poi['id']} verifying {len(gallery)} URLs", flush=True)
        verified = []
        for url in gallery:
            ok = verify_url(url)
            all_total += 1
            if ok:
                verified.append(url)
                all_ok += 1
                time.sleep(SLEEP_OK)
            else:
                print(f"    XX {url[-60:]}", flush=True)
                time.sleep(SLEEP_OK)
        poi["gallery"] = verified
        print(f"    ok: {len(verified)}/{len(gallery)}", flush=True)

        # Checkpoint every 5
        if (idx + 1 - start_idx) % 5 == 0:
            with open(POI_FILE, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=2)

    with open(POI_FILE, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    print(f"\n===== VERIFY SUMMARY =====", flush=True)
    print(f"verified: {all_ok}/{all_total}", flush=True)
    ok5 = 0
    for poi in pois:
        n = len(poi.get("gallery") or [])
        if n >= 5:
            ok5 += 1
        print(f"  {poi['id']} {n:2}  {poi['name_en'][:50]}", flush=True)
    print(f"\n{ok5}/{total} POIs have >=5 verified images", flush=True)


if __name__ == "__main__":
    main()
