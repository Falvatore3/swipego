# Prompt v2 — 草稿（去硬编码时间 + 餐位 + 交通偏好）

> **状态**：📝 草稿，未上线
> **设计日期**：2026-05-10
> **核心思路**：DeepSeek 只决定"顺序 + 大致时段 + 交通偏好"，**不写具体时刻**；具体时刻由后端用 Google Maps Distance Matrix 真实交通时长拼出来。
> **配套架构**：见 `../DESIGN.md` 第 2 节"两步法 Pipeline"

---

## 调用参数

```js
{
  model: 'deepseek-chat',
  temperature: 0.5,    // 比 v1 低一点，因为不需要它发挥时间编排创意
  response_format: { type: 'json_object' }
}
```

## System Prompt

```
你是资深曼谷旅行规划师。

你的输出**只决定**：
- 每天访问哪些 POI、按什么顺序
- 每个 POI 大致在什么时段（morning / noon / afternoon / evening / night）
- 在每个 POI 的停留时长（分钟）
- 到下一个 POI 推荐用什么交通方式（walk / transit / driving / boat）
- 哪些位置该插入吃饭的"时段坑位"（用户会自己选餐厅）

你**不需要也不要**写：
- 具体几点几分（08:30 这种）
- 路上需要多少分钟
- 具体餐厅推荐

具体时刻和真实交通时长，由后续真实地图 API 计算后拼装。
你只负责**地理动线、节奏、餐饮节点**这三件事。
```

## User Prompt 模板

```
用户用 ${intake.days} 天玩曼谷，每天 ${intake.wake} 起床，${pace}强度。

行程位置参考（用于第一天/最后一天判断）：
- 首日抵达机场：${intake.arrive_airport || "未提供，按全天可用处理"}
- 末日离开机场：${intake.depart_airport || "未提供，按全天可用处理"}
- 旅行季节：${intake.season || "雨季（5-10 月）"}—— 雨季每日 14:00-17:00 易雷阵雨

他**右滑想去**了 ${likedSlim.length} 个 POI：
${JSON.stringify(likedSlim, null, 2)}

他还**下滑待定**了 ${maybeSlim.length} 个，可以补充使用：
${JSON.stringify(maybeSlim, null, 2)}

排程要求：
1. **就近聚类**：用 lat/lng 把同一天的 POI 控制在 ~3 公里半径内，避免横跨曼谷
2. **尊重 best_time**：morning POI 上午去、evening POI 傍晚去；afternoon 类的雨季尽量避开 14-17 点（建议挪到上午尾或傍晚开始）
3. **节奏密度**：${pace_density}
4. **第一天 / 最后一天特殊处理**：
   - 首日如果有 arrive_airport，第一项最早 slot 不早于 ${intake.wake}，且当天总时长不超过 6 小时
   - 末日如果有 depart_airport，最后一项必须在登机前 4 小时结束
5. **餐饮坑位 meal_slots**：每天必须给出 2-3 个 meal_slot（早餐可选、午餐必须、晚餐必须），插在合适的 POI 之间，**不指定餐厅**，只说大致位置和类型
6. **交通偏好 preferred_transport_to_next**：基于两个 POI 的距离和地形给建议
   - <800m 给 "walk"
   - 同 BTS/MRT 线路 4 站内给 "transit"
   - 跨河、跨远距离给 "driving"
   - 涉及湄南河沿岸的给 "boat"
7. **note 写实用信息**：必须包含数字（票价/排队时间/开门时间）或具体动作（"右手边台阶上去"），禁止"记得带相机""注意防晒"这类废话
8. **day_theme**：≤12 字，项目管理感（"老城寺庙暴走"、"购物祈福逛吃"），可加 emoji
9. POI 不重复

**严格输出 JSON**（不要 markdown）：

{
  "days": [
    {
      "day": 1,
      "theme": "老城寺庙暴走 ☀️",
      "items": [
        {
          "poi_id": "bkk-001",
          "slot": "morning",
          "duration_min": 150,
          "preferred_transport_to_next": "walk",
          "note": "08:30 开门即到，门票 500 铢含玉佛寺联票"
        }
      ],
      "meal_slots": [
        {
          "after_poi_id": "bkk-002",
          "type": "lunch",
          "earliest_slot": "noon",
          "duration_min": 75,
          "near_district": "老城区",
          "ai_hint": "卧佛寺出来推荐 Tha Tien 码头的船面或附近 Krua Apsorn"
        }
      ]
    }
  ],
  "overall_tip": "整体建议"
}
```

变量映射：
- `pace`：`chill` → "轻松"，`intense` → "高强度"，其他 → "标准"
- `pace_density`：
  - chill：每天 3-4 个 POI + 2 个餐位，总停留 ≤6h
  - standard：每天 4-6 个 POI + 2-3 个餐位，总停留 ≤8h
  - intense：每天 6-8 个 POI + 3 个餐位，总停留 ≤10h

## v2 喂给 AI 的 POI 字段

和 v1 一样的 slim 9 字段，**新增**一个：

```diff
{
  id, name, category, district,
  duration_hr, best_time,
  price_thb,
  lat, lng,
  tips: tips.slice(0, 2),
+ open_hours: p.open_hours_summary,   // 新增：让 AI 避开闭馆时段
}
```

> ⚠️ `open_hours_summary` 字段在 `data/bangkok-pois.json` 里目前**还没有**，需要在 v2 落地前补数据。先粗粒度："09:00-21:00 daily" 这种字符串足够。

## v2 输出 schema 要点

| 字段 | v1 | v2 | 为什么改 |
|---|---|---|---|
| `items[].start` / `end` | ✅ "HH:MM" | ❌ 删除 | 由后端拼装 |
| `items[].slot` | ❌ | ✅ "morning"/"noon"/... | AI 只决定时段 |
| `items[].duration_min` | ❌（隐含在 start/end 差值） | ✅ 显式分钟数 | 后端要它来算时刻 |
| `items[].preferred_transport_to_next` | ❌ | ✅ "walk"/"transit"/"driving"/"boat" | 喂给 Google Maps Distance Matrix 的 mode 参数 |
| `meal_slots[]` | ❌ | ✅ 餐位结构化 | 前端能渲染"+ 选餐厅"按钮 |

## 后端拼时间轴的伪代码

```js
function fillRealTimeline(plan, intake, googleMaps, poiMap) {
  for (const day of plan.days) {
    let cursor = parseTime(intake.wake);  // e.g. 09:00 → 540 min
    const timeline = [];

    for (let i = 0; i < day.items.length; i++) {
      const it = day.items[i];

      // POI 块
      timeline.push({
        type: 'poi',
        poi_id: it.poi_id,
        start: formatTime(cursor),
        end:   formatTime(cursor + it.duration_min),
        note:  it.note,
      });
      cursor += it.duration_min;

      // 餐位（如果这个 POI 后面挂着 meal_slot）
      const meal = day.meal_slots.find(m => m.after_poi_id === it.poi_id);
      if (meal) {
        timeline.push({
          type: 'meal_placeholder',
          meal_type: meal.type,
          start: formatTime(cursor),
          end:   formatTime(cursor + meal.duration_min),
          near_district: meal.near_district,
          near_lat: poiMap[it.poi_id].lat,
          near_lng: poiMap[it.poi_id].lng,
          ai_hint: meal.ai_hint,
          user_chosen_poi: null,        // 用户选了之后填
        });
        cursor += meal.duration_min;
      }

      // 真实交通块（到下一个 POI）
      if (i < day.items.length - 1) {
        const next = day.items[i + 1];
        const route = await googleMaps.distanceMatrix({
          origin: poiMap[it.poi_id],
          destination: poiMap[next.poi_id],
          mode: it.preferred_transport_to_next,
          departure_time: cursor,
        });
        timeline.push({
          type: 'transit',
          mode: route.mode,
          duration_min: route.duration_min,
          summary: route.summary,           // "BTS Silom Line, 4 stops"
          map_url: route.map_url,
          start: formatTime(cursor),
          end:   formatTime(cursor + route.duration_min),
        });
        cursor += route.duration_min;
      }
    }
    day.timeline = timeline;
  }
  return plan;
}
```

---

## v2 落地前置依赖

按依赖顺序：

1. ⏳ **数据补字段**：给 `bangkok-pois.json` 80 个 POI 加 `open_hours_summary` 字符串
2. ⏳ **Google Maps Distance Matrix 接入**：CF Worker 加 `/v1/distance-matrix` 路由 + 藏 key
3. ⏳ **前端拼装器**：实现 `fillRealTimeline()`
4. ⏳ **餐位选择 UI**：用户点 `+ 选餐厅` 弹抽屉
5. ✅ **prompt v2** 文本本身（即本文档）

详细步骤见 `../DESIGN.md`。
