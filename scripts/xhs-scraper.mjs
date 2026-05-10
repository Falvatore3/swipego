// xhs-scraper.js — 小红书图片抓取 PoC
// 用法: node xhs-scraper.js "曼谷大皇宫" 5
// 输出：返回 N 张候选图片 URL（JSON）

import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';

const KEYWORD = process.argv[2] || '曼谷大皇宫';
const LIMIT = parseInt(process.argv[3] || '7', 10);
const OUT_DIR = process.argv[4] || null;  // 可选，传了就直接下载到这里

const SEARCH_URL = `https://www.xiaohongshu.com/search_result?keyword=${encodeURIComponent(KEYWORD)}&type=51`;
// type=51 = 综合搜索

(async () => {
  const browser = await chromium.launch({
    headless: true,
    args: ['--disable-blink-features=AutomationControlled', '--no-sandbox']
  });
  const ctx = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    viewport: { width: 1280, height: 900 },
    locale: 'zh-CN',
  });
  const page = await ctx.newPage();
  
  let imageUrls = new Set();
  
  // 拦截图片请求，提取小红书 CDN 上的图
  page.on('response', async (resp) => {
    const url = resp.url();
    // 小红书图片 CDN
    if (/xhscdn\.com|xiaohongshu\.com/.test(url) && /\.(jpg|jpeg|png|webp)/i.test(url) && !url.includes('avatar')) {
      // 过滤：只要笔记封面（通常 ?imageView 或 fileid 路径）
      if (url.includes('!') || url.includes('imageView') || url.includes('/notes/') || /sns-webpic-qc|sns-img/.test(url)) {
        imageUrls.add(url);
      }
    }
  });
  
  try {
    console.error(`搜索: ${KEYWORD}`);
    await page.goto(SEARCH_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    
    // 等内容加载（小红书懒加载）
    await page.waitForTimeout(3000);
    
    // 滚动几下让更多笔记加载
    for (let i = 0; i < 4; i++) {
      await page.evaluate(() => window.scrollBy(0, 800));
      await page.waitForTimeout(1500);
    }
    
    // 也尝试从 DOM 直接抓 img.src
    const domImgs = await page.$$eval('img', imgs => 
      imgs
        .map(img => img.src || img.getAttribute('data-src') || '')
        .filter(s => /xhscdn\.com|xiaohongshu\.com/.test(s) && /\.(jpg|jpeg|png|webp)/i.test(s) && !s.includes('avatar'))
    );
    domImgs.forEach(u => imageUrls.add(u));
    
    // 标题验证：抓页面是否真的搜索了
    const title = await page.title();
    console.error(`页面标题: ${title}`);
    
    // 检查是否有滑块/登录墙
    const hasLogin = await page.$('text=/登录|扫码登录|注册/');
    if (hasLogin) console.error('⚠️ 检测到登录提示，但匿名也能拿到部分图');
    
  } catch (e) {
    console.error('抓取出错:', e.message);
  }
  
  const urls = [...imageUrls].slice(0, LIMIT);
  console.error(`拿到 ${imageUrls.size} 张候选，截取前 ${urls.length} 张`);
  
  // 直接下载到本地
  if (OUT_DIR && urls.length) {
    fs.mkdirSync(OUT_DIR, { recursive: true });
    for (let i = 0; i < urls.length; i++) {
      const u = urls[i];
      try {
        const resp = await ctx.request.get(u, {
          headers: { Referer: 'https://www.xiaohongshu.com/' },
          timeout: 15000,
        });
        if (resp.ok()) {
          const buf = await resp.body();
          if (buf.length > 5000) {
            const ext = u.match(/\.(jpg|jpeg|png|webp)/i)?.[1] || 'jpg';
            const fp = path.join(OUT_DIR, `xhs_${i+1}.${ext.toLowerCase()}`);
            fs.writeFileSync(fp, buf);
            console.error(`  ✓ ${i+1} ${(buf.length/1024).toFixed(0)}KB -> ${fp}`);
          } else {
            console.error(`  ✗ ${i+1} too small`);
          }
        } else {
          console.error(`  ✗ ${i+1} ${resp.status()}`);
        }
      } catch (e) {
        console.error(`  ✗ ${i+1} ${e.message}`);
      }
    }
  }
  
  // stdout 输出 JSON 供脚本调用
  console.log(JSON.stringify({ keyword: KEYWORD, count: urls.length, urls }, null, 2));
  
  await browser.close();
})();
