# SwipeGo · 曼谷小时级旅游攻略

J 人专属的旅游规划 H5。

## 玩法

1. 答 3 题（天数 / 起床时间 / 行程强度）
2. 左滑跳过、右滑想去、下滑待定，刷完 30 张曼谷 POI 卡
3. 自动按区域聚类 + 最佳时段排出小时级行程
4. 每项可勾选打卡，进度条满满成就感

## 技术

- 单 HTML 文件 · React 18 (CDN) · Tailwind (CDN) · 原生 pointer 拖拽
- 数据：`data/bangkok-pois.json`
- 部署：GitHub Pages

## 本地预览

```bash
cd swipego
python3 -m http.server 4788
# 浏览器打开 http://localhost:4788/
```
