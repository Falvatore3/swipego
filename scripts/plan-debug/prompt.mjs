/**
 * SwipeGo 行程生成 Prompt 模块（独立可调试版）
 *
 * 这是从 index.html 里 aiBuildItinerary() 抽出来的纯 prompt 拼装逻辑。
 * 改这里 = 改前端实际跑的 prompt（前端那份是镜像，发现好版本回填进 index.html）。
 *
 * 与前端唯一不同：这里 export buildMessages()/slimPoi()，方便 CLI 单独调用。
 */

/** 收缩 POI 信息只保留排程必需字段，省 tokens（与前端逻辑保持一致） */
export function slimPoi(p) {
  return {
    id: p.id,
    name: p.name_zh,
    category: p.category_label || p.category,
    district: p.district_zh || p.district,
    duration_hr: p.duration_hr,
    best_time: p.best_time,
    price_thb: p.price_thb,
    lat: p.lat,
    lng: p.lng,
    tips: (p.tips || []).slice(0, 2),
  };
}

/**
 * 系统提示词。这里集中改，方便 A/B。
 */
export const SYSTEM_PROMPT =
  "你是资深曼谷旅行规划师，擅长为 J 人型用户生成小时级精确行程。";

/**
 * 拼装 user prompt
 * @param {{days:number, wake?:string, pace?:string}} intake
 * @param {Array} likedSlim   已经过 slimPoi 的右滑 POI
 * @param {Array} maybeSlim   已经过 slimPoi 的下滑待定 POI
 */
export function buildUserPrompt(intake, likedSlim, maybeSlim) {
  return `用户想用 ${intake.days} 天玩曼谷，每天 ${intake.wake || "09:00"} 起床，${
    intake.pace === "chill" ? "轻松" : intake.pace === "intense" ? "高强度" : "标准"
  }强度（${
    intake.pace === "chill" ? "每天 3-4 项" : intake.pace === "intense" ? "每天 6-8 项" : "每天 5-6 项"
  }）。

他**右滑想去**了 ${likedSlim.length} 个 POI：
${JSON.stringify(likedSlim, null, 2)}

${
  maybeSlim.length > 0
    ? `他还**下滑待定**了 ${maybeSlim.length} 个，如果想去的不够填满天数可以补充使用：
${JSON.stringify(maybeSlim, null, 2)}`
    : ""
}

要求：
1. 按地理位置就近聚类（用 lat/lng），同一天尽量同区域
2. 尊重每个 POI 的 best_time（早上的去早上、傍晚的去傍晚）
3. 每个时段 24h 制起止时刻（如 "09:30"）
4. 中间留 60-90 分钟用餐（12:00-13:30 / 18:30-20:00 高峰）、20-30 分钟通勤
5. 每天起一个有"项目管理感、J 人爽点"的 day_theme（短促有力，<= 12 字，可加 emoji）
6. 每个安排写一句 AI 贴士 note（why this time / what to watch out for / 通勤建议）
7. 如果想去的 POI 不够填满 ${intake.days} 天，可以从待定清单里挑 1-2 个补充；仍然不够就让那一天为"留白日"，items 为空数组
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
}`;
}

/**
 * 一站式：拼好 messages 数组，直接喂给 chat/completions
 */
export function buildMessages(intake, likedRaw, maybeRaw) {
  const likedSlim = likedRaw.map(slimPoi);
  const maybeSlim = maybeRaw.map(slimPoi);
  return {
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      { role: "user", content: buildUserPrompt(intake, likedSlim, maybeSlim) },
    ],
    likedSlim,
    maybeSlim,
  };
}
