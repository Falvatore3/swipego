# Prompt v1 — 当前生产版（基线快照）

> **状态**：✅ 当前线上跑的版本（commit 0e5205d 之后）
> **冻结日期**：2026-05-10
> **对应代码**：
> - 前端：`swipego/index.html` 中 `aiBuildItinerary()` 函数（搜 `// ---------- AI 行程生成`）
> - 调试器：`swipego/scripts/plan-debug/prompt.mjs`
>
> 这份 markdown 是 **v1 的人类可读快照**，作为后续 prompt 迭代的对照基线。
> 修改 prompt 请去改 `prompt.mjs`，验证完再回填 `index.html`，**不要改这个 v1 文件**。
> 新版本另开 `v2-xxx.md`、`v3-xxx.md`。

---

## 调用参数

```js
{
  model: 'deepseek-chat',
  temperature: 0.6,
  response_format: { type: 'json_object' }
}
```

## System Prompt

```
你是资深曼谷旅行规划师，擅长为 J 人型用户生成小时级精确行程。
```

## User Prompt 模板

```
用户想用 ${intake.days} 天玩曼谷，每天 ${intake.wake} 起床，${pace}强度（每天 ${N} 项）。

他**右滑想去**了 ${likedSlim.length} 个 POI：
${JSON.stringify(likedSlim, null, 2)}

他还**下滑待定**了 ${maybeSlim.length} 个，如果想去的不够填满天数可以补充使用：
${JSON.stringify(maybeSlim, null, 2)}

要求：
1. 按地理位置就近聚类（用 lat/lng），同一天尽量同区域
2. 尊重每个 POI 的 best_time（早上的去早上、傍晚的去傍晚）
3. 每个时段 24h 制起止时刻（如 "09:30"）
4. 中间留 60-90 分钟用餐（12:00-13:30 / 18:30-20:00 高峰）、20-30 分钟通勤
5. 每天起一个有"项目管理感、J 人爽点"的 day_theme（短促有力，<= 12 字，可加 emoji）
6. 每个安排写一句 AI 贴士 note（why this time / what to watch out for / 通勤建议）
7. 如果想去的 POI 不够填满 ${intake.days} 天，可以从待定清单里挑 1-2 个补充；
   仍然不够就让那一天为"留白日"，items 为空数组
8. POI 不要重复出现

**严格输出 JSON**（不要 markdown 代码块）：
{
  "days": [
    {
      "day": 1,
      "theme": "老城寺庙暴走 ☀️",
      "items": [
        {"poi_id":"bkk-001","start":"08:30","end":"11:00","note":"开门即到，避开团客高峰"}
      ]
    }
  ],
  "overall_tip": "整体建议（雨季穿搭/打车/支付等）"
}
```

变量映射：
- `pace` 取自 `intake.pace`：`chill` → "轻松"、`intense` → "高强度"、其他 → "标准"
- `N` 同上对应：3-4 项 / 6-8 项 / 5-6 项

## 喂给 AI 的 POI 字段（slim 版）

每个 POI 只保留 9 个字段，砍掉 long_desc / cover_url / gallery / tags / xhs_keyword / address / price_level / color / icon。

```js
{
  id, name, category, district,
  duration_hr, best_time,
  price_thb,
  lat, lng,
  tips: tips.slice(0, 2),   // 只取前 2 条
}
```

## 输出 schema

```json
{
  "days": [
    {
      "day": 1,
      "theme": "短标题，<= 12 字，可加 emoji",
      "items": [
        {
          "poi_id": "bkk-001",
          "start": "08:30",
          "end":   "11:00",
          "note":  "AI 贴士一句话"
        }
      ]
    }
  ],
  "overall_tip": "整体建议"
}
```

前端拿到后用 `poiMap[poi_id]` 还原成完整 POI 对象。

---

## v1 已知问题（v2 要解决）

1. **交通时间是拍脑袋的**——规则 ④ 让 AI 估 20-30 分钟，曼谷实际通勤范围 5-90 分钟，差距巨大
2. **吃饭是规则约束而非数据结构**——AI 把"留 60-90 分钟"理解成"两个 POI 之间间隔"，前端拿不到结构化的"该吃饭了"信号，无法插入用户手动选餐厅入口
3. **没用真实地图能力**——所有地理决策只靠 lat/lng 数字推断
4. **note 容易写废话**（"记得带相机"、"注意防晒"）—— 没强约束 note 必须有数字或具体动作
5. **没区分第一天/最后一天**——刚下飞机精力差、最后一天要打包，AI 不知道
6. **没给天气/雨季信息**——5-10 月雨季下午经常雷阵雨，prompt 里没体现
