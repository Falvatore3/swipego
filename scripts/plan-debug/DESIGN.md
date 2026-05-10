# SwipeGo · 行程规划 v2 架构设计

> **状态**：📐 设计稿，待实施
> **作者**：与 Frankie 在 2026-05-10 对谈定稿
> **目标**：从"AI 单次输出含时刻的行程"升级为"AI 排序 + 真实地图算时间 + 用户参与餐厅决策 + 地图可视化"
> **生产代码影响**：本设计实施前不动 `index.html` 任何一行；先在 `plan-debug/` 里把 prompt 和拼装器调通

---

## 0. 全景图

```
┌────────────────────────────────────────────────────────────────────┐
│                     用户在 SwipeGo 玩了一遍                          │
│           StepIntake → StepSwipe → 拿到 liked + maybe + intake      │
└────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│  Step ①  AI 排顺序（DeepSeek，prompt v2）                          │
│  Input :  liked + maybe + intake + open_hours                      │
│  Output:  每天 POI 顺序 + slot + duration_min                       │
│           + preferred_transport_to_next + meal_slots                │
│  特点 :  不写具体几点几分                                            │
└────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│  Step ②  真实交通时长查询（Google Maps Distance Matrix）            │
│  Input :  每对相邻 POI（含 lat/lng + AI 给的 mode 偏好 + 出发时刻）  │
│  Output:  真实分钟数 + 路线摘要（"BTS Silom 4 站"）+ Google Maps URL │
│  优化 :  并发请求；同源不复算（缓存）                                │
└────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│  Step ③  时间轴拼装（前端纯函数 fillRealTimeline）                  │
│  从 wake 时刻开始累加：POI停留 → meal坑位 → 真实交通 → 下个POI...    │
│  得到含 HH:MM 的最终 timeline[]                                     │
└────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│  Step ④  渲染                                                       │
│  ┌─────────────┐  ┌──────────────────┐  ┌──────────────────────┐  │
│  │ 每天卡片头   │→ │ Mapbox 当日地图  │→ │ 时间轴（POI/交通/餐位）│  │
│  └─────────────┘  └──────────────────┘  └──────────────────────┘  │
│  顶部 tab：[全行程总览图]（合并 N 天，按颜色区分，可保存为图片）       │
└────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│  Step ⑤  用户调整                                                   │
│  - 点 meal 坑位 → 弹餐厅抽屉（POI 库 + Google Places 搜索）          │
│  - 拖拽 POI 顺序 → 重跑 Step ② / ③                                  │
│  - 「保存为图片」→ html2canvas 出长图，引导发小红书                   │
└────────────────────────────────────────────────────────────────────┘
```

---

## 1. Prompt 层变化（v1 → v2）

详细 diff 见 `prompts/v2-no-time-with-meal.md`。这里只列**架构上的关键变化**：

| 维度 | v1 | v2 |
|---|---|---|
| AI 决策范围 | 顺序 + 时刻 + 交通 + note | 顺序 + 时段 + 时长 + 交通偏好 + note + 餐位 |
| 时刻精度 | AI 直接给 HH:MM | 后端从 wake 累加得到 |
| 交通时间 | AI 估"20-30 分钟" | Google Maps 真值 |
| 吃饭 | 规则约束（"留 60-90 分"） | 结构化 `meal_slots[]` 数组 |
| 输出体积 | 中 | 大（多了 slot/duration/transport/meal） |
| Prompt 复杂度 | 8 条规则 | 9 条规则 + 季节/机场/餐位约束 |

---

## 2. 两步法 Pipeline

### 2.1 接口契约

```ts
// 1. AI 输出（plan-debug 里 mock 时也按这个 schema）
interface AIPlan {
  days: AIDay[];
  overall_tip: string;
}
interface AIDay {
  day: number;
  theme: string;
  items: AIItem[];
  meal_slots: AIMealSlot[];
}
interface AIItem {
  poi_id: string;
  slot: 'morning' | 'noon' | 'afternoon' | 'evening' | 'night';
  duration_min: number;
  preferred_transport_to_next: 'walk' | 'transit' | 'driving' | 'boat';
  note: string;
}
interface AIMealSlot {
  after_poi_id: string;       // 插在哪个 POI 之后
  type: 'breakfast' | 'lunch' | 'dinner' | 'snack';
  earliest_slot: AIItem['slot'];
  duration_min: number;
  near_district: string;
  ai_hint: string;
}

// 2. Google Maps 接入（包一层后端代理）
interface RouteQuery {
  origin: { lat: number; lng: number };
  destination: { lat: number; lng: number };
  mode: 'walk' | 'transit' | 'driving' | 'boat';   // boat 实际走 transit + filter
  departure_time: number;     // unix ts，用于真实拥堵预测
}
interface RouteResult {
  mode: 'walking' | 'transit' | 'driving';
  duration_min: number;
  distance_m: number;
  summary: string;            // "BTS Silom Line · 4 stops" / "5 min walk"
  polyline: string;           // encoded polyline，用于 Mapbox 画线
  map_url: string;            // 跳到 Google Maps 导航的 URL
}

// 3. 拼好后的最终 timeline
interface FinalDay {
  day: number;
  theme: string;
  timeline: TimelineBlock[];  // 顺序混合 poi/transit/meal
  bbox: [[number, number], [number, number]];   // 当天地图视口
  summary: { poi_count: number; transit_total_min: number; span_km: number };
}
type TimelineBlock = PoiBlock | TransitBlock | MealBlock;
interface PoiBlock {
  type: 'poi';
  poi_id: string;
  start: string; end: string;      // "HH:MM"
  note: string;
}
interface TransitBlock {
  type: 'transit';
  start: string; end: string;
  mode: RouteResult['mode'];
  duration_min: number;
  summary: string;
  polyline: string;
  map_url: string;
}
interface MealBlock {
  type: 'meal_placeholder';
  start: string; end: string;
  meal_type: AIMealSlot['type'];
  near_district: string;
  near_lat: number; near_lng: number;
  ai_hint: string;
  user_chosen_poi: PoiLite | null;   // 用户选完餐厅填这里
}
```

### 2.2 核心函数：`fillRealTimeline()`

伪代码已在 `prompts/v2-no-time-with-meal.md` 给出，这里补**容错**：

- Google Maps 调失败 → 用 AI 偏好 + 直线距离估值兜底（**不要静默**，UI 要显示"⚠️ 估值"标记）
- AI 给的 `preferred_transport_to_next` 不合法 → 默认 `driving`
- AI 给的 `duration_min` 异常（<10 或 >360） → clamp 到 [30, 240]
- meal_slot 的 `after_poi_id` 找不到对应 POI → 丢弃这个餐位并打 console.warn

### 2.3 性能/成本

- 每天 N 个 POI → N-1 次 Distance Matrix 调用
- 3 天 5 POI → 12 次调用
- Google Maps 价格：$0.005/次 → 12 次 = $0.06 ≈ ¥0.45/单
- 每月免费额度 $200 → 够 ~3,300 单
- **优化**：同源（同两个 POI 同 mode）不重算，前端 sessionStorage 缓存

---

## 3. Google Maps 集成

### 3.1 Key 怎么藏

复用现有 CF Worker 模式（`swipego/cf-worker/`），新增一个路由：

```
POST /v1/distance-matrix
  body: { origin, destination, mode, departure_time }
  worker 加上 GOOGLE_MAPS_KEY 转发到
  https://maps.googleapis.com/maps/api/distancematrix/json?...
```

复用现有：Origin 白名单、IP 限流、body 大小校验。

### 3.2 mode 映射

DeepSeek 给的 4 种 mode → Google Maps 参数：

| AI mode | Google `mode` | 备注 |
|---|---|---|
| `walk` | `walking` | |
| `transit` | `transit` | 含 BTS/MRT/bus |
| `driving` | `driving` | Grab/出租车也归这里 |
| `boat` | `transit` + `transit_mode=ferry` | 湄南河 Chao Phraya Express |

### 3.3 输出转换

Google 返回的 `duration_in_traffic` 优先于 `duration`（更准）。`summary` 自己拼：
- `walking` → "步行 X 分钟（X 米）"
- `transit` → 取 `legs[0].steps` 里第一个非步行段，"BTS Silom · 4 stops"
- `driving` → "驾车 X 分钟"

---

## 4. 餐位 placeholder UI

### 4.1 时间轴里长这样

```
🛕 卧佛寺                            10:00 - 11:30
   └─🚶 步行 5 分钟（420m）

🍽️ 午餐位                            12:30 - 13:45    [+ 选餐厅]
   💡 卧佛寺出来推荐 Tha Tien 码头船面或 Krua Apsorn
   📍 老城区附近

🛕 大皇宫                            14:00 - 16:00
```

### 4.2 「+ 选餐厅」抽屉

抽屉从底部弹出，三个 tab：

| Tab | 数据源 | 用途 |
|---|---|---|
| 📍 附近 POI | `bangkok-pois.json` 中 `category === '美食'` 且距 `near_lat/lng` < 1km | 优先用我们策划过的 |
| 🔍 Google 搜索 | Google Places Nearby Search | 兜底覆盖率 |
| ✏️ 手动添加 | 用户填名字 + 地址 | 完全自由 |

用户选完 → 替换 `meal_placeholder` 为 `poi` block，自动重跑该天的交通时间（前一段 = 上个 POI 到餐厅，后一段 = 餐厅到下个 POI）。

---

## 5. Mapbox 地图模块

### 5.1 选型理由

- **底图**：Mapbox Studio 调一个暖色调街道图（参考小红书截图：浅黄底 + 浅绿绿地 + 浅蓝水系）
- **路线**：用 Step ② 拿到的 Google polyline 解码后画线
- **Marker**：自定义 React 组件，不用默认 pin
- 国内访问：Mapbox 国内有 CDN（`https://api.mapbox.com` → 实测可用）

### 5.2 每天卡片上的「当日地图」

```
┌──────────────────────────────────┐
│ 📆 Day 1 · 老城寺庙暴走 ☀️       │
├──────────────────────────────────┤
│                                  │
│  [Mapbox 280px 高，暖色底图]      │
│                                  │
│  ① 大皇宫                        │
│  └─贝塞尔曲线─🚶 5min            │
│  ② 卧佛寺                        │
│  └─贝塞尔曲线─🚇 12min           │
│  ③ 唐人街                        │
│                                  │
│  3 个景点 · 通勤 25 分钟 · 4.2km  │
└──────────────────────────────────┘
```

技术细节：
- Marker：圆形当天主题色 + 白色数字编号 + 下方 POI 名称气泡
- 连线：Mapbox `line-layer` 用 `line-curve` 效果（靠贝塞尔控制点偏移）
- 时长标签：`symbol-layer` 贴在线段中点
- 视口：`map.fitBounds(day.bbox, { padding: 40 })`
- 高度固定 280px（不抢时间轴风头）

### 5.3 「全行程总览图」（顶部 tab）

```
[ Day 1 | Day 2 | Day 3 |  📍 全行程总览  ]
                          ↑ 默认折叠，点击展开全屏
```

展开后：
- 全屏 Mapbox
- 所有天的 POI marker 都画上，按 day 给颜色（Day1 红 / Day2 黄 / Day3 粉，参考小红书截图）
- 每天用 polyline 连起来
- 右上角浮一个图例 `🔴 Day1  🟡 Day2  🟢 Day3`
- 右下角 `[💾 保存为图片]` 按钮

### 5.4 「保存为图片」

```js
import html2canvas from 'html2canvas';

async function saveItineraryAsImage() {
  // 1. 等 Mapbox 渲染完成（map.once('idle'))
  // 2. 取整个 itinerary DOM 节点
  // 3. html2canvas 渲染（注意 useCORS: true 给 Mapbox 瓦片）
  // 4. canvas.toBlob → 下载 / 分享
}
```

坑预警：
- Mapbox 瓦片需要 `preserveDrawingBuffer: true`（创建 map 时设）
- iOS Safari 下载 PNG 会被拦，得用 `share()` API 或弹窗让用户长按保存
- 中文字体要保证 woff2 已加载完才截图（`document.fonts.ready`）
- 长图建议宽度 750px（小红书原生宽），高度自适应

底部加水印：

```
SwipeGo · 滑卡定制曼谷 3 日游
swipego.app · 小红书 @SwipeGo
```

---

## 6. 实施顺序（建议分 5 个 PR）

| # | PR 标题 | 范围 | 风险 |
|---|---|---|---|
| 1 | 数据补 `open_hours_summary` | 改 `data/bangkok-pois.json` 80 个 POI | 低，纯数据 |
| 2 | CF Worker 加 distance-matrix 路由 + Google key | 改 `cf-worker/src/index.js` + wrangler.toml | 中，要申请 Google key + 设支出上限 |
| 3 | Prompt v2 + 拼装器（在 plan-debug 里跑通） | 新文件，不影响生产 | 低 |
| 4 | 前端切换到 v2（替换 aiBuildItinerary）+ 餐位抽屉 | 改 index.html | 高，主流程 |
| 5 | Mapbox 地图模块 + 「保存为图片」 | 改 index.html，新增 Mapbox 依赖 | 中 |

每个 PR 都能独立上线/回滚。Step 1-3 全做完才有意义切 Step 4。

---

## 7. 成本预估（每月）

| 项 | 单价 | 假设量 | 月费 |
|---|---|---|---|
| DeepSeek（v2 prompt 略长） | ~¥0.001/单 | 1000 单/月 | ¥1 |
| Google Distance Matrix | $0.005/次 × ~10次/单 | 1000 单 | $50（在 $200 免费额内） |
| Google Places（餐厅搜索） | $0.032/次 × 用户偶尔点 | ~500 次 | $16（免费额内） |
| Mapbox 地图加载 | 免费 5 万次/月 | 1000 单 × 5 次 = 5000 | $0 |
| Cloudflare Workers | 10 万次/天免费 | 远低于 | $0 |

**月成本约 ¥1**（DeepSeek）+ Google 免费额度兜底。

---

## 8. 待 Frankie 决策的开放问题

- [ ] Google Maps key 谁来申请？（要绑信用卡，但有 $200/月免费额度，建议你自己申请绑你的招行）
- [ ] Mapbox account 谁注册？（免费层 5 万次/月足够，不用绑卡）
- [ ] `open_hours_summary` 数据补全：让我帮你跑个脚本批量从 Google Places API 拉？（一次性成本 ~$2.4）
- [ ] 「保存为图片」加水印用哪个口号？现在写的是 `SwipeGo · 滑卡定制曼谷 3 日游`

---

## 9. 文件清单（这次产出）

```
swipego/scripts/plan-debug/
├── prompts/
│   ├── v1-current.md              ← 基线快照
│   ├── v2-no-time-with-meal.md    ← v2 草稿
│   └── CHANGELOG.md
├── DESIGN.md                       ← 本文件
├── prompt.mjs / run.mjs / ...     （之前已建）
```

实施时新增（参考路径，待开 PR 时定）：
```
swipego/scripts/plan-debug/
└── prompt-v2.mjs                   # v2 prompt 拼装器（与 v1 prompt.mjs 并存）

swipego/cf-worker/src/
└── index.js                        # 加 /v1/distance-matrix 路由

swipego/src/
├── timeline/fillRealTimeline.js    # 拼装器纯函数
├── map/DayMap.jsx                  # 当日 Mapbox 模块
├── map/OverviewMap.jsx             # 全行程总览
├── map/saveAsImage.js              # html2canvas 封装
└── meal/MealPicker.jsx             # 餐位选择抽屉
```
