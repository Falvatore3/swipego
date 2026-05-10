#!/usr/bin/env node
/**
 * SwipeGo 行程生成 — 命令行调试器
 *
 * 用途：不开浏览器、不走完整滑卡流程，直接喂 POI ID 列表 + 天数，
 *       拿到 DeepSeek 排出来的行程 JSON。方便快速迭代 prompt.mjs 里的提示词。
 *
 * 用法（在仓库根 swipego/ 目录下执行）：
 *   # 1) 用预置 fixture 跑一次（默认）
 *   node scripts/plan-debug/run.mjs
 *
 *   # 2) 指定参数
 *   node scripts/plan-debug/run.mjs \
 *     --liked bkk-001,bkk-002,bkk-005,bkk-010,bkk-020 \
 *     --maybe bkk-030,bkk-031 \
 *     --days 3 \
 *     --pace standard \
 *     --temp 0.6 \
 *     --model deepseek-chat
 *
 *   # 3) 用 fixture 文件
 *   node scripts/plan-debug/run.mjs --fixture fixtures/sample-3day.json
 *
 *   # 4) 只打印 prompt 不调 API（dry-run，零成本）
 *   node scripts/plan-debug/run.mjs --dry
 *
 *   # 5) 用代理而不是直连 DeepSeek（推荐，避免暴露 key）
 *   node scripts/plan-debug/run.mjs \
 *     --proxy https://swipego-deepseek-proxy.xxx.workers.dev/v1/chat/completions \
 *     --origin https://falvatore3.github.io
 *
 * 需要的环境变量（直连模式才需要）：
 *   DEEPSEEK_KEY=sk-xxxx   # 或者用 --key 传
 *
 * 输出：
 *   - 终端打印 prompt 预览 + 生成结果
 *   - 完整请求/响应写入 ./out/<timestamp>.json，方便 diff
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { buildMessages, slimPoi, SYSTEM_PROMPT } from "./prompt.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, "..", ".."); // swipego/

// ------------------------- 简易 argv 解析 -------------------------

function parseArgs(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith("--")) continue;
    const k = a.slice(2);
    const next = argv[i + 1];
    if (!next || next.startsWith("--")) {
      out[k] = true;
    } else {
      out[k] = next;
      i++;
    }
  }
  return out;
}

const args = parseArgs(process.argv);

// ------------------------- 加载 POI 数据 -------------------------

function loadPois() {
  const p = path.join(REPO_ROOT, "data", "bangkok-pois.json");
  const raw = fs.readFileSync(p, "utf-8");
  return JSON.parse(raw);
}

// ------------------------- 解析 fixture / argv -------------------------

function loadFixture(rel) {
  const p = path.isAbsolute(rel) ? rel : path.join(__dirname, rel);
  return JSON.parse(fs.readFileSync(p, "utf-8"));
}

function resolveInput() {
  // 默认 fixture
  let fixture = {
    intake: { days: 3, wake: "09:00", pace: "standard" },
    liked_ids: ["bkk-001", "bkk-002", "bkk-005", "bkk-010", "bkk-020", "bkk-030", "bkk-040", "bkk-050"],
    maybe_ids: ["bkk-008", "bkk-015"],
  };

  if (args.fixture) {
    fixture = loadFixture(args.fixture);
  }

  // 命令行参数覆盖
  if (args.liked) fixture.liked_ids = String(args.liked).split(",").map((s) => s.trim()).filter(Boolean);
  if (args.maybe) fixture.maybe_ids = String(args.maybe).split(",").map((s) => s.trim()).filter(Boolean);
  if (args.days) fixture.intake.days = parseInt(args.days, 10);
  if (args.wake) fixture.intake.wake = String(args.wake);
  if (args.pace) fixture.intake.pace = String(args.pace);

  return fixture;
}

// ------------------------- 主流程 -------------------------

async function main() {
  const data = loadPois();
  const poiMap = new Map(data.pois.map((p) => [p.id, p]));
  const fx = resolveInput();

  // 把 id 还原成完整 POI 对象
  const liked = fx.liked_ids.map((id) => poiMap.get(id)).filter(Boolean);
  const maybe = (fx.maybe_ids || []).map((id) => poiMap.get(id)).filter(Boolean);
  const missingLiked = fx.liked_ids.filter((id) => !poiMap.has(id));
  const missingMaybe = (fx.maybe_ids || []).filter((id) => !poiMap.has(id));

  if (missingLiked.length || missingMaybe.length) {
    console.warn(
      "⚠️  下列 POI ID 在 data/bangkok-pois.json 里找不到，已忽略：",
      [...missingLiked, ...missingMaybe].join(", ")
    );
  }

  const { messages, likedSlim, maybeSlim } = buildMessages(fx.intake, liked, maybe);

  // ---- 终端预览 ----
  console.log("─".repeat(60));
  console.log("📋  Intake:", fx.intake);
  console.log(
    `📥  Liked: ${likedSlim.length} 个 → ${likedSlim.map((p) => p.name).join(", ")}`
  );
  console.log(
    `📥  Maybe: ${maybeSlim.length} 个 → ${maybeSlim.map((p) => p.name).join(", ") || "(无)"}`
  );
  console.log("─".repeat(60));
  console.log("🧾  System prompt:\n" + SYSTEM_PROMPT);
  console.log("─".repeat(60));
  console.log("🧾  User prompt 预览（前 800 字）:\n" + messages[1].content.slice(0, 800) + "...\n");
  console.log("─".repeat(60));

  // ---- 准备请求体 ----
  const model = args.model || "deepseek-chat";
  const temperature = args.temp != null ? parseFloat(args.temp) : 0.6;
  const reqBody = {
    model,
    messages,
    temperature,
    response_format: { type: "json_object" },
  };

  if (args.dry) {
    console.log("🚧  --dry 模式：跳过 API 调用。");
    console.log("📦  完整请求体已写入 out/dry-run.json");
    fs.mkdirSync(path.join(__dirname, "out"), { recursive: true });
    fs.writeFileSync(
      path.join(__dirname, "out", "dry-run.json"),
      JSON.stringify(reqBody, null, 2)
    );
    return;
  }

  // ---- 决定走代理还是直连 ----
  const proxyUrl = args.proxy || process.env.SWIPEGO_PROXY_URL || "";
  const directUrl = "https://api.deepseek.com/chat/completions";
  const apiUrl = proxyUrl || directUrl;
  const directKey = args.key || process.env.DEEPSEEK_KEY || "";

  if (!proxyUrl && !directKey) {
    console.error(
      "❌  既没有 --proxy 也没有 DEEPSEEK_KEY。请二选一：\n" +
        "    A) 直连：export DEEPSEEK_KEY=sk-xxxx 或 --key sk-xxxx\n" +
        "    B) 代理：--proxy https://xxx.workers.dev/v1/chat/completions  --origin https://falvatore3.github.io"
    );
    process.exit(1);
  }

  const headers = { "Content-Type": "application/json" };
  if (!proxyUrl && directKey) headers["Authorization"] = `Bearer ${directKey}`;
  if (proxyUrl && args.origin) headers["Origin"] = String(args.origin);

  console.log(
    `🚀  调用 ${proxyUrl ? "代理" : "DeepSeek 直连"}: ${apiUrl}  · model=${model} · temp=${temperature}`
  );

  const t0 = Date.now();
  let resp;
  try {
    resp = await fetch(apiUrl, {
      method: "POST",
      headers,
      body: JSON.stringify(reqBody),
    });
  } catch (e) {
    console.error("❌  网络错误：", e.message || e);
    process.exit(1);
  }
  const dur = Date.now() - t0;
  const respText = await resp.text();

  // ---- 写日志 ----
  const ts = new Date().toISOString().replace(/[:.]/g, "-");
  const outDir = path.join(__dirname, "out");
  fs.mkdirSync(outDir, { recursive: true });
  const logPath = path.join(outDir, `${ts}.json`);
  fs.writeFileSync(
    logPath,
    JSON.stringify(
      {
        meta: {
          ts,
          dur_ms: dur,
          api_url: apiUrl,
          mode: proxyUrl ? "proxy" : "direct",
          model,
          temperature,
          intake: fx.intake,
          liked_ids: liked.map((p) => p.id),
          maybe_ids: maybe.map((p) => p.id),
        },
        request: reqBody,
        response_status: resp.status,
        response_body: safeParse(respText),
      },
      null,
      2
    )
  );

  if (!resp.ok) {
    console.error(`❌  HTTP ${resp.status}：`, respText.slice(0, 400));
    console.error(`📁  完整日志：${logPath}`);
    process.exit(1);
  }

  // ---- 解析结果 ----
  const data2 = JSON.parse(respText);
  const content = data2?.choices?.[0]?.message?.content;
  if (!content) {
    console.error("❌  AI 没有返回 content。完整响应：", respText.slice(0, 400));
    process.exit(1);
  }

  let plan;
  try {
    plan = JSON.parse(content);
  } catch (e) {
    console.error("❌  AI 返回的不是合法 JSON，前 200 字：", content.slice(0, 200));
    process.exit(1);
  }

  // ---- 漂亮打印 ----
  console.log(`✅  ${dur}ms · 用量:`, data2.usage || "(未返回 usage)");
  console.log("─".repeat(60));
  for (const day of plan.days || []) {
    console.log(`\n📆  Day ${day.day} · ${day.theme || ""}`);
    if (!day.items || day.items.length === 0) {
      console.log("   （留白日）");
      continue;
    }
    for (const it of day.items) {
      const poi = poiMap.get(it.poi_id);
      const name = poi ? poi.name_zh : `[未知 POI: ${it.poi_id}]`;
      console.log(`   ${it.start}-${it.end}  ${name}`);
      if (it.note) console.log(`              💡 ${it.note}`);
    }
  }
  if (plan.overall_tip) {
    console.log("\n💡  整体建议:", plan.overall_tip);
  }
  console.log("\n─".repeat(60));
  console.log(`📁  完整日志：${logPath}`);
}

function safeParse(s) {
  try {
    return JSON.parse(s);
  } catch {
    return s;
  }
}

main().catch((e) => {
  console.error("💥  未捕获错误：", e);
  process.exit(1);
});
