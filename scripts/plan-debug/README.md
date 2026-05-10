# Plan-Debug —— SwipeGo 行程生成 Prompt 调试器

> 不开浏览器、不走完整滑卡流程，直接喂 POI ID + 天数，拿到 DeepSeek 排出来的行程 JSON。
> 用来快速迭代 `prompt.mjs` 里的提示词。

## 目录结构

```
plan-debug/
├── prompt.mjs            # ★ Prompt 单一来源（v1，当前生产中）
├── run.mjs               # CLI 入口
├── fixtures/             # 预置场景
│   └── sample-3day.json
├── out/                  # 每次调用的完整请求/响应（自动生成）
├── prompts/              # ★ Prompt 版本归档（人类可读）
│   ├── v1-current.md     #   当前生产版基线快照
│   ├── v2-no-time-with-meal.md  # v2 草稿：去硬时间 + 餐位 + 交通偏好
│   └── CHANGELOG.md
├── DESIGN.md             # ★ v2 完整架构设计（两步法 + Google Maps + Mapbox）
└── README.md
```

## 文档索引（怎么读这堆 markdown）

| 想做什么 | 看哪份 |
|---|---|
| 改当前生产 prompt（小修小补） | `prompt.mjs`，改完手动同步 `index.html` |
| 看当前 prompt 完整长啥样 | `prompts/v1-current.md` |
| 看下一版 prompt 设计 | `prompts/v2-no-time-with-meal.md` |
| 看整体架构（地图、餐位、保存图片等） | `DESIGN.md` |
| 看每版 prompt 改了啥 | `prompts/CHANGELOG.md` |

`prompt.mjs` 是 prompt 的唯一来源。改完跑通后，再把 `SYSTEM_PROMPT` 和 `buildUserPrompt()` 里的内容回填到 `swipego/index.html` 中 `aiBuildItinerary()` 函数（搜 `// ---------- AI 行程生成`）。

## 快速开始

### 1) 直连 DeepSeek（最简单，要 key）

```bash
cd /Users/frankie/WorkBuddy/2026-05-08-task-2/swipego
export DEEPSEEK_KEY=sk-xxxxxx
node scripts/plan-debug/run.mjs
```

默认会用 `fixtures/sample-3day.json`。

### 2) 走 Cloudflare Worker 代理（不需要 key，但要 origin 在白名单里）

```bash
node scripts/plan-debug/run.mjs \
  --proxy https://swipego-deepseek-proxy.xxx.workers.dev/v1/chat/completions \
  --origin https://falvatore3.github.io
```

### 3) Dry-run（只拼 prompt 不调 API，零成本）

```bash
node scripts/plan-debug/run.mjs --dry
```

输出 `out/dry-run.json`，里面是会发给 DeepSeek 的完整请求体。

## 常用参数

| 参数 | 说明 | 示例 |
|---|---|---|
| `--fixture` | 用 fixture 文件作为输入 | `--fixture fixtures/sample-3day.json` |
| `--liked` | 右滑想去的 POI ID（逗号分隔，覆盖 fixture） | `--liked bkk-001,bkk-002,bkk-005` |
| `--maybe` | 下滑待定的 POI ID | `--maybe bkk-030,bkk-031` |
| `--days` | 行程天数 | `--days 5` |
| `--wake` | 起床时间 | `--wake 08:30` |
| `--pace` | 节奏 `chill` / `standard` / `intense` | `--pace intense` |
| `--temp` | DeepSeek temperature | `--temp 0.4` |
| `--model` | 模型名 | `--model deepseek-reasoner` |
| `--proxy` | 代理 URL | 见上文 |
| `--origin` | 代理模式下伪造 origin | `--origin https://falvatore3.github.io` |
| `--key` | 直连模式下传 key（也可用环境变量） | `--key sk-xxx` |
| `--dry` | 只拼 prompt 不调 API | `--dry` |

## 输出

- 终端：列出每天的小时级排程 + AI 整体贴士
- 磁盘：`out/<timestamp>.json` 存完整请求/响应（含 token usage），方便事后 diff prompt 版本

## 工作流：怎么用它迭代 prompt

1. 改 `prompt.mjs` 里的 `SYSTEM_PROMPT` 或 `buildUserPrompt()`
2. `node scripts/plan-debug/run.mjs --dry` 看下 prompt 长啥样
3. `node scripts/plan-debug/run.mjs` 真跑一次，看输出是否符合预期
4. 不满意？改 prompt → 重跑（同一个 fixture，输出可对比）
5. 满意 → 把改动同步回 `swipego/index.html` 里的 `aiBuildItinerary()`

> **TODO**: 后面可以把前端 `aiBuildItinerary()` 也改成 `import` 这个 `prompt.mjs`，
> 单一来源就真单一了。目前因为 index.html 是单文件 + esm.sh CDN，需要改成 `<script type="module">`，
> 留待后续重构。

## 写一个新 fixture

复制 `fixtures/sample-3day.json` 改个名，调整 `liked_ids` / `maybe_ids` / `intake.days`，
跑：

```bash
node scripts/plan-debug/run.mjs --fixture fixtures/my-case.json
```

POI ID 在 `swipego/data/bangkok-pois.json` 里查（80 个，bkk-001 到 bkk-080）。
