# Prompt 版本日记

> 每次往生产 push 新 prompt 都来这里加一条。模板在最下面。

---

## v1 — 2026-05-10 · 初版上线

- **当时状态**：commit 0e5205d，前端硬编码 sk- key，¥10 上限
- **设计**：单条 prompt 让 DeepSeek 一次性输出"POI + 时刻 + note"
- **已知问题**：
  - 交通时间靠 AI 拍脑袋
  - 吃饭只是规则约束，没有结构化餐位
  - 没用真实地图数据
- **快照**：[`v1-current.md`](./v1-current.md)

---

## v2 — 2026-05-10 · 设计中（未上线）

- **触发**：用户提出两个需求
  1. 交通方式 + 真实交通时间应该走 Google Maps，不让 AI 编
  2. 没餐厅选时给用户空一个时段坑位，让用户手动加
- **设计**：拆成"AI 排顺序 → Google Maps 算时间 → 后端拼时间轴"两步法
- **新增字段**：`slot` / `duration_min` / `preferred_transport_to_next` / `meal_slots[]`
- **配套**：Mapbox 地图模块 + 「保存为图片」分享功能（详见 `../DESIGN.md`）
- **草稿**：[`v2-no-time-with-meal.md`](./v2-no-time-with-meal.md)
- **前置依赖**（按顺序）：
  1. POI 数据补 `open_hours_summary`
  2. CF Worker 加地图代理路由
  3. 前端 `fillRealTimeline()` 拼装器
  4. 餐位选择抽屉 UI
  5. Mapbox 地图组件 + 「保存为图片」
- **状态**：待上述依赖就位后实施

---

## 模板（复制此段开新 entry）

```md
## v?-? — YYYY-MM-DD · ${标题}

- **触发**：${为什么改}
- **改了什么**：${diff vs 上一版}
- **测试结果**：${用 plan-debug --dry / 真跑的对比}
- **回归风险**：${会不会让某些场景变差}
- **快照**：[`v?-${slug}.md`](./v?-${slug}.md)
```
