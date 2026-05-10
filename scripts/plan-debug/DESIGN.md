# SwipeGo · 行程规划 v2 架构设计（精简版）

> **状态**：📐 v2 设计稿，准备开工
> **作者**：与 Frankie 在 2026-05-10 对谈定稿，2026-05-10 23:54 范围缩减
> **关键决策**：交通时间和真实地图集成 **挪到 v3**；v2 让 DeepSeek 自己估时刻（含打车通勤时长）
>
> v3 Backlog（被砍出 v2 的内容）见文末第 9 节，key 已存待用

---

## 0. v2 全景图（缩减版）

```
┌────────────────────────────────────────────────────────────────────┐
│                     用户在 SwipeGo 玩了一遍                          │
│           StepIntake → StepSwipe → 拿到 liked + maybe + intake      │
└────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│  Step ①  AI 一次性出完整行程（DeepSeek，prompt v2）                 │
│  Input :  liked + maybe + intake                                   │
│  Output:  每天 POI + HH:MM 时刻 + 打车通勤时长 + meal_slots         │
│           + note + day_theme + overall_tip                         │
│  约束 :  note 必须含数字/动作；首末日机场约束；雨季避开 14-17       │
└────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│  Step ②  时间轴拼装（前端纯函数 fillTimeline）                      │
│  把 AI 给的 items[] 和 meal_slots[] 按 HH:MM 顺序合并成 timeline    │
│  - poi block       (来自 items)                                    │
│  - meal block      (来自 meal_slots，等用户手动选餐厅)              │
│  注：没有 transit block，通勤时间已含在相邻 POI 的时刻 gap 里        │
└────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│  Step ③  渲染                                                       │
│  时间轴混合 POI 卡 + 餐位坑                                          │
│  餐位坑显示「+ 选餐厅」按钮 → 抽屉                                   │
└────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│  Step ④  分享                                                       │
│  「💾 保存为图片」→ html2canvas 出长图，含水印 + 二维码              │
│  二维码扫了直接进 SwipeGo（带 utm 追踪），自传播闭环                 │
└────────────────────────────────────────────────────────────────────┘
```

---

## 1. Prompt 层变化（v1 → v2）

详细 diff 见 `prompts/v2.1-meal-only.md`。架构上的关键变化：

| 维度 | v1 | v2 |
|---|---|---|
| AI 决策范围 | 顺序 + 时刻 + 通勤估值 + note | 顺序 + 时刻 + **打车通勤估值** + note + **餐位** |
| 时刻精度 | AI 给 HH:MM | AI 给 HH:MM（**继续相信 AI**，v3 再用真实地图） |
| 通勤方式 | 含糊"通勤" | 显式说"按打车时长估" |
| 吃饭 | 规则约束 | 结构化 `meal_slots[]` 数组 |
| note 质量 | 容易写废话 | 强约束：必须含数字或具体动作 |
| 首末日 | 没区分 | 显式约束机场抵达/离开时间 |
| 季节 | 没考虑 | 5-10 月雨季提示避开 14-17 点 |

---

## 2. 接口契约

```ts
// AI 输出（plan-debug 里 mock 时也按这个 schema）
interface AIPlan {
  days: AIDay[];
  overall_tip: string;
}
interface AIDay {
  day: number;
  theme: string;                       // ≤12 字 + emoji
  items: AIItem[];                     // 含吃饭之外的所有时段
  meal_slots: AIMealSlot[];           // 结构化餐位
}
interface AIItem {
  poi_id: string;
  start: string;                       // "HH:MM"，AI 给的（含通勤 gap）
  end:   string;
  note:  string;                       // 必须含数字或具体动作
}
interface AIMealSlot {
  after_poi_id: string;                // 插在哪个 POI 之后
  type: 'breakfast' | 'lunch' | 'dinner' | 'snack';
  start: string;                       // "HH:MM"，AI 给的
  end:   string;
  near_district: string;               // 给用户挑餐厅时缩小范围
  ai_hint: string;                     // 一句话："卧佛寺出来推荐 Tha Tien 码头船面"
}

// 拼装后的最终 timeline（纯前端拼）
interface FinalDay {
  day: number;
  theme: string;
  timeline: TimelineBlock[];           // poi + meal_placeholder 混合，按 start 排序
  overall_tip: string;
}
type TimelineBlock = PoiBlock | MealBlock;
interface PoiBlock {
  type: 'poi';
  poi: POI;                            // 完整 POI 对象（已用 poiMap 还原）
  start: string; end: string;
  note: string;
}
interface MealBlock {
  type: 'meal_placeholder';
  meal_type: AIMealSlot['type'];
  start: string; end: string;
  near_district: string;
  near_lat: number; near_lng: number;  // 取自 after_poi 的 lat/lng
  ai_hint: string;
  user_chosen_poi: POI | null;         // 用户选完餐厅填这里
}
```

## 3. 拼装器：`fillTimeline()`

伪代码：

```js
function fillTimeline(plan, poiMap) {
  return plan.days.map(day => {
    // 1. 合并 items + meal_slots，统一加 type 字段
    const blocks = [
      ...day.items.map(it => ({
        type: 'poi',
        poi: poiMap[it.poi_id],
        start: it.start, end: it.end, note: it.note,
      })),
      ...day.meal_slots.map(m => {
        const afterPoi = poiMap[m.after_poi_id];
        return {
          type: 'meal_placeholder',
          meal_type: m.type,
          start: m.start, end: m.end,
          near_district: m.near_district,
          near_lat: afterPoi?.lat, near_lng: afterPoi?.lng,
          ai_hint: m.ai_hint,
          user_chosen_poi: null,
        };
      }),
    ];

    // 2. 过滤 AI 编出的非法 poi_id
    const valid = blocks.filter(b => b.type === 'meal_placeholder' || b.poi);

    // 3. 按 start 排序
    valid.sort((a, b) => parseTime(a.start) - parseTime(b.start));

    return {
      day: day.day,
      theme: day.theme,
      timeline: valid,
    };
  });
}
```

**容错**：
- AI 给的 `after_poi_id` 找不到 → meal_block 的 lat/lng 留空，前端 UI 退化为"附近"二字
- AI 给的 `start/end` 格式错 → console.warn 并丢弃该 block
- AI 漏给 meal_slots → 不报错，按现状渲染（无餐位）

## 4. 餐位 placeholder UI

### 4.1 时间轴渲染

```
🛕 卧佛寺                   10:00 - 11:30
   💡 08:30 开门即到，门票 300 铢

🍽️ 午餐位                   12:30 - 13:45    [+ 选餐厅]
   💡 卧佛寺出来推荐 Tha Tien 码头船面或 Krua Apsorn
   📍 老城区附近

🛕 大皇宫                   14:00 - 16:00
   💡 ...
```

### 4.2 「+ 选餐厅」抽屉（v2 简化版）

底部弹出，**两个 tab**（Google Places 暂缓到 v3）：

| Tab | 数据源 | 用途 |
|---|---|---|
| 📍 附近 POI | `bangkok-pois.json` 里 `category === '美食'` 且距 `near_lat/lng` < 1.5km | 优先用我们策划过的 |
| ✏️ 手动添加 | 用户填名字 + 可选地址 | 完全自由 |

用户选完 → 替换该 `meal_placeholder` block 的 `user_chosen_poi` 字段为选中的 POI（不重排时间）。

UI 上：
- 卡片头从虚线框 + dashed 改成实线 + 用户选的餐厅图片/名称
- 右上角小 ✏️ 图标可重新选

## 5. 「保存为图片」+ 二维码

### 5.1 触发位置

行程页（StepItinerary）顶部右上角加个按钮 `💾 保存为图片`，点击后：
1. 弹 loading mask
2. 生成长图
3. 下载（桌面）或弹 modal 让用户长按保存（移动端）

### 5.2 实现

```js
import html2canvas from 'html2canvas';
import QRCode from 'qrcode';

async function saveItineraryAsImage(itineraryNode, intake) {
  // 1. 等中文字体加载完
  await document.fonts.ready;

  // 2. 在 itineraryNode 底部 append 一个分享底栏
  const footer = renderShareFooter(intake);   // React renderToString → DOM
  itineraryNode.appendChild(footer);

  try {
    const canvas = await html2canvas(itineraryNode, {
      useCORS: true,
      backgroundColor: '#FAF8F2',
      scale: 2,                                // retina
      width: 750,                              // 小红书原生宽
    });
    const blob = await new Promise(r => canvas.toBlob(r, 'image/png'));
    await downloadOrShare(blob, 'swipego-bangkok-itinerary.png');
  } finally {
    footer.remove();
  }
}

async function renderShareFooter(intake) {
  const url = `https://falvatore3.github.io/swipego/?utm_source=share_image&utm_medium=xhs&utm_campaign=v2`;
  const qrDataUrl = await QRCode.toDataURL(url, {
    margin: 1, width: 240,
    color: { dark: '#0F3D2E', light: '#FFFFFF' },
    errorCorrectionLevel: 'M',
  });
  // 返回一个 DOM 节点，含水印文案 + 二维码 + 引导语
  // ...
}
```

### 5.3 分享底栏视觉

```
┌──────────────────────────────────────────┐
│  ✨ SwipeGo · 滑卡定制曼谷 3 日游         │
│  3 天 · 8 个景点 · 2 个餐位待你选         │
│                              ┌────────┐  │
│  扫码定制你的专属行程 →        │  二维码 │  │
│                              │ 120×120│  │
│  swipego (小红书 / GitHub)    └────────┘  │
└──────────────────────────────────────────┘
```

### 5.4 坑预警

- iOS Safari 直接下载 PNG 会被拦 → 移动端弹 modal 显示 `<img src="data:..." >` 让用户长按
- 中文字体必须等 `document.fonts.ready` 才截图，否则乱码
- html2canvas 不支持某些 CSS（filter/blend-mode），渲染前先检查
- 二维码 `errorCorrectionLevel: 'M'` 平衡密度 vs 容错（被压缩仍可扫）
- 长图宽度 750px（小红书原生宽，避免压缩失真）

---

## 6. 实施顺序（3 个 PR 即可）

| # | PR 标题 | 范围 | 风险 |
|---|---|---|---|
| 1 | v2 prompt + 拼装器（plan-debug 跑通） | 新文件，不动生产 | 低 |
| 2 | 前端切 v2 + 餐位抽屉 | 改 `index.html`，加 `MealPicker` | 中 |
| 3 | 「保存为图片」+ 二维码 | 加 `qrcode` + `html2canvas`，新增按钮 | 中 |

每个 PR 都能独立上线/回滚。

---

## 7. 成本预估（每月）

| 项 | 单价 | 假设量 | 月费 |
|---|---|---|---|
| DeepSeek（v2 prompt 略长） | ~¥0.001/单 | 1000 单/月 | ¥1 |
| qrcode npm | 0 | - | ¥0 |
| html2canvas npm | 0 | - | ¥0 |
| Cloudflare Workers | 10 万次/天免费 | 远低于 | ¥0 |

**月成本约 ¥1**。v3 接 Google Maps 后会上升到约 $5-10/月（在 $200 免费额内）。

---

## 8. 待 Frankie 决策的开放问题

- [ ] 二维码指向的 URL：当前 `https://falvatore3.github.io/swipego/?utm_source=share_image&utm_medium=xhs&utm_campaign=v2`，后续上 `swipego.app` 域名后要换
- [ ] 「保存为图片」分享底栏的中文文案：`✨ SwipeGo · 滑卡定制曼谷 3 日游` 是否需要换
- [ ] 餐位抽屉的"附近"半径：当前 1.5km，是否合适

---

## 9. v3 Backlog（被砍出 v2 的内容）

> 这部分原本在 v2 计划里，2026-05-10 23:54 决定挪到 v3。资源已就位（Google key 已存在 `~/.workbuddy/secrets/keys.env`），等 v2 跑稳后再做。

### 9.1 真实交通时间（Google Distance Matrix）

- 现状：v2 让 DeepSeek 估打车时间，可能差 30 分钟
- v3 方案：DeepSeek 只决定顺序 + 大致时段，前端用 Google Distance Matrix 算每段真实交通时间，再拼时间轴
- 依赖：CF Worker 加 `/v1/distance-matrix` 路由，藏 `GOOGLE_MAPS_KEY`
- mode 映射：walk / transit / driving / boat → Google API 参数

### 9.2 Mapbox 地图模块

- 每天卡片上方放一个 280px 高的小地图，POI marker + 路线连线（参考小红书曼谷 3 日攻略图）
- 顶部 tab 加「全行程总览图」，所有天合并按颜色分（Day1 红 / Day2 黄 / Day3 粉），可全屏
- 暖色 Studio 底图风格
- 「保存为图片」会包含地图

依赖：
- Mapbox 账号（用户注册，邮箱验证无法代办）
- 真实路线数据（来自 9.1）

### 9.3 POI 营业时间数据 `open_hours_summary`

- 现状：80 个 POI 完全没有营业时间字段，AI 排程可能踩闭馆
- v3 方案：用 Google Places API New 一次性批量拉，~$2.4 一次性成本
- 数据格式：`"Daily 08:30-15:30"` / `"Tue-Sun 10:00-20:00, Mon closed"`

### 9.4 餐位抽屉加 Google Places 搜索 tab

- v2 只有"附近 POI + 手动添加"两个 tab
- v3 加第三个 tab：实时调 Google Places Nearby Search 拿曼谷餐厅候选

### 9.5 Prompt v3 字段

- 加回 `slot` / `duration_min` / `preferred_transport_to_next`
- `meal_slots` 去掉 `start/end`，只给 `earliest_slot` 和 `duration_min`
- 时间由前端拼装

---

## 10. 文件清单（v2 产出）

```
swipego/scripts/plan-debug/
├── prompts/
│   ├── v1-current.md              ← 基线快照
│   ├── v2.1-meal-only.md          ← v2 草稿（本次范围）
│   └── CHANGELOG.md
├── DESIGN.md                       ← 本文件
├── prompt-v2.mjs                   ← v2 prompt 拼装器（新增）
├── fillTimeline.mjs                ← 时间轴拼装纯函数（新增）
├── prompt.mjs / run.mjs / ...     （v1 已有）
```

实施时新增（待开 PR）：
```
swipego/index.html                  # aiBuildItinerary 切 v2 + 加 MealPicker + 加 SaveAsImage
```
