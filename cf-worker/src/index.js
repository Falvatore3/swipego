/**
 * SwipeGo DeepSeek Proxy — Cloudflare Worker
 * ------------------------------------------
 * 作用：把前端发来的请求加上 Authorization header 后转发到 DeepSeek，
 *      避免在前端公开仓库里暴露 API key。
 *
 * 路由：
 *   POST   /v1/chat/completions   → 转发到 DeepSeek
 *   OPTIONS *                     → CORS 预检
 *   GET    /healthz               → 健康检查（返回 ok）
 *   其他                            → 404
 *
 * 安全 / 防滥用：
 *   - Origin 白名单（来自 wrangler.toml 的 ALLOWED_ORIGINS）
 *   - body 大小上限（默认 10KB，来自 MAX_BODY_BYTES）
 *   - 单 IP 简易限流（默认每分钟 20 次，来自 RATE_LIMIT_PER_MIN）
 *
 * 日志：
 *   只记录时间 / status / token usage，不记 key、不记用户输入内容。
 */

// ------------------------- 工具函数 -------------------------

/** 解析逗号分隔的字符串为数组，过滤空值 */
function parseList(str) {
  return (str || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

/** 判断 origin 是否在白名单内（支持 http://localhost:* 这种通配） */
function isOriginAllowed(origin, allowedList) {
  if (!origin) return false;
  for (const rule of allowedList) {
    if (rule === origin) return true;
    // 简单的端口通配：http://localhost:* 或 http://127.0.0.1:*
    if (rule.endsWith(":*")) {
      const prefix = rule.slice(0, -1); // 去掉末尾 *
      if (origin.startsWith(prefix)) return true;
    }
  }
  return false;
}

/** 生成 CORS 响应头 */
function corsHeaders(origin) {
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}

/** 标准化错误响应 */
function jsonError(status, message, origin) {
  const headers = {
    "Content-Type": "application/json; charset=utf-8",
  };
  if (origin) Object.assign(headers, corsHeaders(origin));
  return new Response(
    JSON.stringify({ error: { message, type: "proxy_error", code: status } }),
    { status, headers }
  );
}

// ------------------------- 简易内存级限流 -------------------------
// 注意：CF Worker 单实例的内存不会跨 region 共享，这只是兜底。
// 真要严格限流请用 Durable Objects 或 KV。这里的目的是挡掉脚本刷接口。
const rateBucket = new Map(); // key=ip, value={count, resetAt}

function checkRateLimit(ip, limitPerMin) {
  if (!ip) return { ok: true };
  const now = Date.now();
  const win = 60 * 1000;
  const item = rateBucket.get(ip);
  if (!item || now > item.resetAt) {
    rateBucket.set(ip, { count: 1, resetAt: now + win });
    return { ok: true, remaining: limitPerMin - 1 };
  }
  if (item.count >= limitPerMin) {
    return { ok: false, retryAfterSec: Math.ceil((item.resetAt - now) / 1000) };
  }
  item.count += 1;
  return { ok: true, remaining: limitPerMin - item.count };
}

// 简单清理过期 key，避免内存涨爆（每 100 次请求清一次）
let _gcCounter = 0;
function gcRateBucketIfNeeded() {
  _gcCounter += 1;
  if (_gcCounter < 100) return;
  _gcCounter = 0;
  const now = Date.now();
  for (const [k, v] of rateBucket) {
    if (now > v.resetAt) rateBucket.delete(k);
  }
}

// ------------------------- 主入口 -------------------------

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin") || "";
    const allowedOrigins = parseList(env.ALLOWED_ORIGINS);
    const upstream = env.DEEPSEEK_UPSTREAM || "https://api.deepseek.com/chat/completions";
    const maxBody = parseInt(env.MAX_BODY_BYTES || "10240", 10);
    const rateLimit = parseInt(env.RATE_LIMIT_PER_MIN || "20", 10);

    // 健康检查（GET /healthz）—— 不需要 origin，便于直接浏览器访问看是否部署成功
    if (request.method === "GET" && url.pathname === "/healthz") {
      return new Response("ok", {
        status: 200,
        headers: { "Content-Type": "text/plain; charset=utf-8" },
      });
    }

    // ==================== 调试日志 KV 路由 ====================
    // POST /log/upload  — 前端上传日志（Origin 白名单 + 限大小）
    // GET  /log/list    — 拉取最近日志（需 ?token=xxx 验证）
    // GET  /log/get?key=xxx — 拉取单条
    // ==========================================================

    // 上传日志：手机 🐞 浮窗调用
    if (request.method === "POST" && url.pathname === "/log/upload") {
      // CORS 预检上面已统一处理（这里如果是浏览器先发 OPTIONS 会走到下面）
      if (!isOriginAllowed(origin, allowedOrigins)) {
        return jsonError(403, "Origin not allowed", null);
      }
      if (!env.LOGS) {
        return jsonError(500, "KV not bound (set [[kv_namespaces]] in wrangler.toml)", origin);
      }
      let raw;
      try { raw = await request.text(); } catch { return jsonError(400, "read body failed", origin); }
      if (raw.length > 1024 * 200) return jsonError(413, "log too large (>200KB)", origin); // 单条 200KB 上限
      // 简单合法性检查
      try { JSON.parse(raw); } catch { return jsonError(400, "log must be JSON", origin); }
      // key = 时间戳_随机后缀；TTL 7 天后自动删
      const ts = new Date().toISOString().replace(/[:.]/g, "-");
      const key = `${ts}_${Math.random().toString(36).slice(2, 8)}`;
      try {
        await env.LOGS.put(key, raw, { expirationTtl: 60 * 60 * 24 * 7 });
      } catch (e) {
        return jsonError(500, "KV put failed: " + (e.message || e), origin);
      }
      return new Response(JSON.stringify({ ok: true, key, size: raw.length }), {
        status: 200,
        headers: { "Content-Type": "application/json", ...corsHeaders(origin) },
      });
    }

    // 列出日志（仅本人查看，token 校验）
    if (request.method === "GET" && url.pathname === "/log/list") {
      if (!env.LOGS) return new Response("KV not bound", { status: 500 });
      const token = url.searchParams.get("token") || "";
      if (!env.DEBUG_TOKEN || token !== env.DEBUG_TOKEN) {
        return new Response("forbidden (need ?token=xxx)", { status: 403 });
      }
      const limit = Math.min(parseInt(url.searchParams.get("limit") || "20", 10), 100);
      const list = await env.LOGS.list({ limit });
      // 默认 KV list 升序，反一下让最新在前
      const keys = list.keys.map(k => k.name).sort().reverse();
      return new Response(JSON.stringify({ count: keys.length, keys }, null, 2), {
        status: 200,
        headers: { "Content-Type": "application/json; charset=utf-8" },
      });
    }

    // 取单条
    if (request.method === "GET" && url.pathname === "/log/get") {
      if (!env.LOGS) return new Response("KV not bound", { status: 500 });
      const token = url.searchParams.get("token") || "";
      if (!env.DEBUG_TOKEN || token !== env.DEBUG_TOKEN) {
        return new Response("forbidden", { status: 403 });
      }
      const key = url.searchParams.get("key") || "";
      if (!key) return new Response("need ?key=xxx", { status: 400 });
      const v = await env.LOGS.get(key);
      if (!v) return new Response("not found", { status: 404 });
      return new Response(v, {
        status: 200,
        headers: { "Content-Type": "application/json; charset=utf-8" },
      });
    }
    // ==========================================================

    // CORS 预检
    if (request.method === "OPTIONS") {
      if (!isOriginAllowed(origin, allowedOrigins)) {
        return new Response(null, { status: 403 });
      }
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }

    // 只接受 POST /v1/chat/completions
    if (request.method !== "POST" || url.pathname !== "/v1/chat/completions") {
      return jsonError(404, "Not Found. Use POST /v1/chat/completions", origin);
    }

    // Origin 白名单
    if (!isOriginAllowed(origin, allowedOrigins)) {
      return jsonError(403, "Origin not allowed", null);
    }

    // 检查 secret 是否配好
    if (!env.DEEPSEEK_KEY) {
      return jsonError(500, "Server misconfigured: DEEPSEEK_KEY not set", origin);
    }

    // 限流（用 CF-Connecting-IP）
    const ip = request.headers.get("CF-Connecting-IP") || "";
    gcRateBucketIfNeeded();
    const rl = checkRateLimit(ip, rateLimit);
    if (!rl.ok) {
      return new Response(
        JSON.stringify({
          error: { message: "Too Many Requests", type: "rate_limit", code: 429 },
        }),
        {
          status: 429,
          headers: {
            "Content-Type": "application/json; charset=utf-8",
            "Retry-After": String(rl.retryAfterSec || 60),
            ...corsHeaders(origin),
          },
        }
      );
    }

    // 读 body 并校验大小
    let bodyText;
    try {
      bodyText = await request.text();
    } catch (e) {
      return jsonError(400, "Failed to read request body", origin);
    }
    if (bodyText.length > maxBody) {
      return jsonError(413, `Request body too large (>${maxBody} bytes)`, origin);
    }

    // 校验是合法 JSON
    let payload;
    try {
      payload = JSON.parse(bodyText);
    } catch (e) {
      return jsonError(400, "Invalid JSON body", origin);
    }
    if (!payload || typeof payload !== "object") {
      return jsonError(400, "Body must be a JSON object", origin);
    }

    // 转发到 DeepSeek
    const t0 = Date.now();
    let upstreamResp;
    try {
      upstreamResp = await fetch(upstream, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${env.DEEPSEEK_KEY}`,
          "Accept": request.headers.get("Accept") || "application/json",
        },
        body: bodyText,
      });
    } catch (e) {
      console.log(
        JSON.stringify({
          ts: new Date().toISOString(),
          event: "upstream_fetch_failed",
          msg: String(e && e.message ? e.message : e),
        })
      );
      return jsonError(502, "Upstream fetch failed", origin);
    }

    // 把 deepseek 响应原样透传（流式 / 非流式都支持）
    const isStream = (upstreamResp.headers.get("Content-Type") || "")
      .toLowerCase()
      .includes("text/event-stream");

    // 复制响应头，但 CORS 头由我们覆盖；同时去掉一些会冲突的 header
    const respHeaders = new Headers();
    upstreamResp.headers.forEach((value, key) => {
      const k = key.toLowerCase();
      if (
        k === "access-control-allow-origin" ||
        k === "access-control-allow-methods" ||
        k === "access-control-allow-headers" ||
        k === "vary" ||
        k === "content-encoding" || // 让 Workers 自己处理压缩
        k === "transfer-encoding"
      ) {
        return;
      }
      respHeaders.set(key, value);
    });
    Object.entries(corsHeaders(origin)).forEach(([k, v]) => respHeaders.set(k, v));

    // 流式响应：直接 pipe through
    if (isStream) {
      console.log(
        JSON.stringify({
          ts: new Date().toISOString(),
          event: "proxy",
          mode: "stream",
          status: upstreamResp.status,
          dur_ms: Date.now() - t0,
        })
      );
      return new Response(upstreamResp.body, {
        status: upstreamResp.status,
        statusText: upstreamResp.statusText,
        headers: respHeaders,
      });
    }

    // 非流式：读完 body，记录 token usage 后返回
    const respText = await upstreamResp.text();
    let usage = null;
    try {
      const parsed = JSON.parse(respText);
      if (parsed && parsed.usage) usage = parsed.usage;
    } catch (_) {
      // 非 JSON（比如 deepseek 报错时返回 HTML/纯文本），忽略
    }
    console.log(
      JSON.stringify({
        ts: new Date().toISOString(),
        event: "proxy",
        mode: "json",
        status: upstreamResp.status,
        dur_ms: Date.now() - t0,
        usage, // 只记 usage，不记 prompt/response 内容
      })
    );

    return new Response(respText, {
      status: upstreamResp.status,
      statusText: upstreamResp.statusText,
      headers: respHeaders,
    });
  },
};
