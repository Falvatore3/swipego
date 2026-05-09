#!/usr/bin/env python3
"""
下载达标 POI 的 gallery 外网 URL 到本地，并把 JSON 中的 gallery 改写为本地相对路径。
不达标的 POI（少于 5 张）保持 gallery 为空数组（前端用 cover_url 单图回退）。
"""
import json, os, time, urllib.request, urllib.error, ssl, subprocess, sys

ROOT = '/Users/frankie/WorkBuddy/2026-05-08-task-2/swipego'
JSON_PATH = f'{ROOT}/data/bangkok-pois.json'
GAL_DIR = f'{ROOT}/assets/pois/gallery'
os.makedirs(GAL_DIR, exist_ok=True)

UA = 'Mozilla/5.0 (compatible; SwipeGoBot/1.0; +https://falvatore3.github.io/swipego/)'

with open(JSON_PATH) as f:
    data = json.load(f)

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def download(url, out_path, timeout=20):
    """下载单张图，返回 (ok, msg)"""
    if os.path.exists(out_path) and os.path.getsize(out_path) > 8*1024:
        return True, 'cached'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'image/*,*/*'})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            ct = resp.headers.get('Content-Type', '')
            if not ct.startswith('image/'):
                return False, f'not image: {ct}'
            data = resp.read()
            if len(data) < 8*1024:
                return False, f'too small: {len(data)}'
            with open(out_path, 'wb') as f:
                f.write(data)
            return True, f'{len(data)//1024}KB'
    except Exception as e:
        return False, str(e)[:80]

def compress(path, max_w=1280, q=78):
    """用 sips 压到宽度 max_w"""
    try:
        sz_before = os.path.getsize(path)
        if sz_before < 250*1024:
            return  # 小于 250KB 不动
        subprocess.run(
            ['sips', '-Z', str(max_w), '-s', 'formatOptions', str(q), path, '--out', path],
            check=True, capture_output=True
        )
    except Exception as e:
        print(f'  compress fail: {e}')

stats = {'ok': 0, 'fail': 0, 'pois_done': 0, 'pois_skip': 0}
fail_log = []

for poi in data['pois']:
    pid = poi['id']
    gallery = poi.get('gallery') or []

    if len(gallery) < 5:
        # 不达标，gallery 清空（前端回退到 cover_url）
        poi['gallery'] = []
        stats['pois_skip'] += 1
        print(f'⏭️  {pid} {poi["name_zh"]}: 仅 {len(gallery)} 张，跳过本轮')
        continue

    print(f'\n▶️  {pid} {poi["name_zh"]} ({len(gallery)} 张候选)')
    new_gallery = []
    for idx, url in enumerate(gallery, 1):
        if not (url.startswith('http://') or url.startswith('https://')):
            # 已经是本地路径就保留
            new_gallery.append(url)
            continue
        ext = '.jpg'
        if '.png' in url.lower(): ext = '.png'
        elif '.webp' in url.lower(): ext = '.webp'
        out_name = f'{pid}_{idx}{ext}'
        out_path = f'{GAL_DIR}/{out_name}'
        ok, msg = download(url, out_path)
        if ok:
            compress(out_path)
            new_gallery.append(f'./assets/pois/gallery/{out_name}')
            stats['ok'] += 1
            print(f'  ✓ {idx} {msg}')
        else:
            stats['fail'] += 1
            fail_log.append((pid, idx, url, msg))
            print(f'  ✗ {idx} {msg}')
        time.sleep(0.4)  # 避免 wikimedia 429

    # 至少要剩 5 张才视为成功
    if len(new_gallery) >= 5:
        poi['gallery'] = new_gallery
        stats['pois_done'] += 1
    else:
        # 下载后剩不到 5 张，也清空保安全
        poi['gallery'] = []
        stats['pois_skip'] += 1
        print(f'  ⚠️ 下载后仅 {len(new_gallery)} 张可用，置空')

# bump version
data['version'] = '1.5.0'
data['updated_at'] = '2026-05-09'

with open(JSON_PATH, 'w') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print('\n' + '='*60)
print(f'下载成功: {stats["ok"]} / 失败: {stats["fail"]}')
print(f'POI 启用 gallery: {stats["pois_done"]} / 跳过: {stats["pois_skip"]}')
print(f'JSON 已写回 (version 1.5.0)')
if fail_log:
    print(f'\n失败明细:')
    for f in fail_log[:20]:
        print(' ', f)
