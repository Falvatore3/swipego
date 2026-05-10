#!/usr/bin/env python3
"""
Google Places API → 80 POI 真实门店图批量下载
读 bangkok-pois.json，对每个 POI:
  1) Text Search 找 Place ID（用 name_en + 'Bangkok' 当 query）
  2) 拿到 photos 数组
  3) 下载前 7 张 maxWidthPx=1280 的图到 assets/pois/gallery/bkk-XXX_N.jpg
  4) 更新 JSON 的 cover_url（第 1 张）和 gallery（7 张）
"""
import json, os, time, urllib.request, urllib.parse, urllib.error, ssl, sys
from pathlib import Path

ROOT = Path('/Users/frankie/WorkBuddy/2026-05-08-task-2/swipego')
JSON_PATH = ROOT / 'data/bangkok-pois.json'
GALLERY_DIR = ROOT / 'assets/pois/gallery'
COVER_DIR = ROOT / 'assets/pois'
KEY_FILE = Path('/Users/frankie/.workbuddy/secrets/google-places.key')

KEY = KEY_FILE.read_text().strip()
PER_POI_PHOTOS = 7
MAX_WIDTH = 1280

ctx = ssl.create_default_context()

def search_place(name_en, lat=None, lng=None):
    """Text Search → 返回第一个匹配的 Place ID 和 photos 列表"""
    url = 'https://places.googleapis.com/v1/places:searchText'
    body = {
        'textQuery': f'{name_en} Bangkok Thailand',
        'languageCode': 'en',
        'maxResultCount': 1,
    }
    # 如果有坐标，加 location bias 提高精度
    if lat and lng:
        body['locationBias'] = {
            'circle': {
                'center': {'latitude': lat, 'longitude': lng},
                'radius': 500.0
            }
        }
    req = urllib.request.Request(url,
        data=json.dumps(body).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'X-Goog-Api-Key': KEY,
            'X-Goog-FieldMask': 'places.id,places.displayName,places.formattedAddress,places.photos',
        },
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            data = json.load(resp)
            places = data.get('places', [])
            if not places:
                return None, []
            p = places[0]
            return p, p.get('photos', [])
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read())
        except: err = {}
        return f'HTTP {e.code}: {err}', []
    except Exception as e:
        return f'ERR: {e}', []

def download_photo(photo_name, out_path):
    """下载一张照片到本地"""
    url = f'https://places.googleapis.com/v1/{photo_name}/media?maxWidthPx={MAX_WIDTH}&key={KEY}'
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            data = resp.read()
            if len(data) < 8 * 1024:
                return False, f'too small {len(data)}'
            out_path.write_bytes(data)
            return True, f'{len(data)//1024}KB'
    except urllib.error.HTTPError as e:
        return False, f'HTTP {e.code}'
    except Exception as e:
        return False, str(e)[:60]

def main():
    GALLERY_DIR.mkdir(parents=True, exist_ok=True)
    data = json.load(open(JSON_PATH))
    pois = data['pois']

    # 用 argv 控制：--all 全跑，或 --limit N 跑前 N 个，或 --ids bkk-051,bkk-052
    only_ids = None
    limit = None
    for a in sys.argv[1:]:
        if a.startswith('--ids='):
            only_ids = set(a.split('=',1)[1].split(','))
        elif a.startswith('--limit='):
            limit = int(a.split('=',1)[1])

    targets = []
    for p in pois:
        if only_ids and p['id'] not in only_ids:
            continue
        targets.append(p)
        if limit and len(targets) >= limit:
            break

    print(f'目标 POI: {len(targets)} 个')

    stats = {'place_ok':0, 'place_fail':0, 'photos_ok':0, 'photos_fail':0, 'cover_updated':0}
    no_match = []

    for i, p in enumerate(targets, 1):
        pid = p['id']
        name = p['name_en']
        print(f'\n[{i}/{len(targets)}] {pid} {name}')

        place, photos = search_place(name, p.get('lat'), p.get('lng'))
        if not place or isinstance(place, str):
            print(f'  ✗ 搜索失败: {place}')
            stats['place_fail'] += 1
            no_match.append((pid, name, str(place)))
            continue
        stats['place_ok'] += 1
        disp = place.get('displayName',{}).get('text','?')
        print(f'  ✓ 匹配: {disp}  / photos: {len(photos)}')

        if not photos:
            no_match.append((pid, name, 'no photos'))
            continue

        # 下载前 N 张
        new_gallery = []
        new_cover = None
        for idx, photo in enumerate(photos[:PER_POI_PHOTOS], 1):
            out = GALLERY_DIR / f'{pid}_{idx}.jpg'
            ok, msg = download_photo(photo['name'], out)
            if ok:
                rel = f'./assets/pois/gallery/{out.name}'
                new_gallery.append(rel)
                stats['photos_ok'] += 1
                print(f'    ✓ {idx} {msg}')
            else:
                stats['photos_fail'] += 1
                print(f'    ✗ {idx} {msg}')
            time.sleep(0.2)

        # 更新 JSON
        if new_gallery:
            p['gallery'] = new_gallery
            # 同时把 cover_url 升级为第一张（覆盖原本可能是 wikimedia 通用图的 cover）
            cover_path = COVER_DIR / f'{pid}.jpg'
            # 第一张直接复制为 cover
            try:
                first_local = ROOT / new_gallery[0][2:]
                cover_path.write_bytes(first_local.read_bytes())
                p['cover_url'] = f'./assets/pois/{pid}.jpg'
                stats['cover_updated'] += 1
            except Exception as e:
                print(f'    cover update fail: {e}')

        # 每 10 个写一次 checkpoint
        if i % 10 == 0:
            with open(JSON_PATH, 'w') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f'  -- checkpoint saved at {i} --')

        time.sleep(0.3)

    # 最终写回
    data['version'] = '2.1.0'
    data['updated_at'] = '2026-05-10'
    with open(JSON_PATH, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print('\n' + '='*60)
    print(f"搜索: {stats['place_ok']} 成功 / {stats['place_fail']} 失败")
    print(f"照片: {stats['photos_ok']} 下载 / {stats['photos_fail']} 失败")
    print(f"封面: {stats['cover_updated']} 个 POI 已更新 cover_url")
    if no_match:
        print(f'\n以下 POI 未找到/无图（{len(no_match)}）:')
        for x in no_match: print(f"  {x[0]} {x[1]} -> {x[2][:80]}")

if __name__ == '__main__':
    main()
