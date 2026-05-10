/**
 * SwipeGo 行程生成 Prompt v2.1（独立可调试版）
 *
 * 与 v1（./prompt.mjs）的区别：
 * - 新增 meal_slots 结构化餐位（午餐必须、晚餐必须、早餐可选）
 * - note 强约束：必须含数字或具体动作，禁止废话
 * - 显式说明打车通勤估算规则
 * - 首日/末日机场约束（intake.arrive_airport / depart_airport 时生效）
 * - 雨季 14-17 点提示
 *
 * 改这里 = 改 v2 上线后前端实际跑的 prompt（前端那份是镜像，发现好版本回填进 index.html）。
 *
 * 文档：./prompts/v2.1-meal-only.md
 */

/** 收缩 POI 信息只保留排程必需字段，省 tokens（与 v1 完全一致） */
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

export const SYSTEM_PROMPT_V2 = `你是资深曼谷旅行规划师，擅长为 J 人型用户生成小时级精确行程。
你输出的所有时刻已经把"打车通勤时间"计算在内（POI 之间的时刻 gap = 打车时长 + 缓冲）。
吃饭时段你只负责"留位置"，不要推荐具体餐厅（用户会自己选）。`;

function paceLabel(pace) {
  if (pace === 'chill') return '轻松';
  if (pace === 'intense') return '高强度';
  return '标准';
}
function paceCount(pace) {
  if (pace === 'chill') return '3-4';
  if (pace === 'intense') return '6-8';
  return '5-6';
}

export function buildUserPromptV2(intake, likedSlim, maybeSlim) {
  const isRainy = !intake.season || /雨季/.test(intake.season);
  const seasonLine = `旅行季节：${intake.season || '雨季（5-10 月）'}`;
  const rainyTip = isRainy ? '⚠️ 雨季每日 14:00-17:00 易雷阵雨，户外景点尽量避开此时段' : '';

  const arriveLine = intake.arrive_airport
    ? `首日抵达机场：${intake.arrive_airport}（约 ${intake.arrive_time || '13:00'}），首日只排半天行程`
    : '';
  const departLine = intake.depart_airport
    ? `末日离开机场：${intake.depart_airport}（约 ${intake.depart_time || '20:00'}），末日最后一项必须在登机前 4 小时结束`
    : '';

  const maybeBlock = maybeSlim.length > 0
    ? `他还**下滑待定**了 ${maybeSlim.length} 个，可以补充使用：
${JSON.stringify(maybeSlim, null, 2)}`
    : '';

  return `用户用 ${intake.days} 天玩曼谷，每天 ${intake.wake || '09:00'} 起床，${paceLabel(intake.pace)}强度（每天 ${paceCount(intake.pace)} 项）。

${seasonLine}
${rainyTip}

${arriveLine}
${departLine}

他**右滑想去**了 ${likedSlim.length} 个 POI：
${JSON.stringify(likedSlim, null, 2)}

${maybeBlock}

排程要求：
1. 按地理位置就近聚类（用 lat/lng），同一天尽量同区域，避免横跨曼谷
2. 尊重每个 POI 的 best_time（早上的去早上、傍晚的去傍晚）
3. 每个时段 24h 制起止时刻（如 "09:30"）
4. **打车通勤估算**（默认交通方式 = 打车）：
   - 同区域 5-15 分钟
   - 跨区 20-40 分钟
   - 早晚高峰（08-10 / 17-19）翻倍估
   - POI 之间留出"打车时间"作为 gap，不要让两个 POI 时刻紧贴
5. **吃饭坑位 meal_slots**（重要）：
   - 每天必须给 2-3 个 meal_slot：早餐可选、**午餐必须、晚餐必须**
   - 午餐建议 12:00-14:00 之间，时长 60-75 分钟
   - 晚餐建议 18:30-20:30 之间，时长 75-90 分钟
   - meal_slot 用 after_poi_id 挂在某个 POI 之后，表示"逛完 X 后吃饭"
   - 不要推荐具体餐厅，只给 near_district + ai_hint（一句话提示哪类美食/方向）
   - meal_slot 的 start/end 也要写好，和 POI items 共用一条时间线
6. 每天起一个有"项目管理感、J 人爽点"的 day_theme（短促有力，<= 12 字，可加 emoji）
7. **note 强约束**：每个 POI 的 note 必须包含至少一项：
   - 具体数字（票价/排队时间/开门时间/历史年份）
   - 具体动作（"右手边台阶上去"/"在 X 出口换乘"）
   ❌ 禁止"记得带相机"、"注意防晒"、"准备好心情"这类废话
8. 如果想去的 POI 不够填满 ${intake.days} 天，可以从待定清单里挑 1-2 个补充；
   仍然不够就让那一天为"留白日"，items 为空数组（meal_slots 也为空）
9. POI 不要重复出现

**严格输出 JSON**（不要 markdown 代码块）：
{
  "days": [
    {
      "day": 1,
      "theme": "老城寺庙暴走 ☀️",
      "items": [
        {
          "poi_id": "bkk-001",
          "start": "08:30",
          "end":   "11:00",
          "note":  "08:30 开门即到，门票 500 铢含玉佛寺，避开 10 点旅行团高峰"
        }
      ],
      "meal_slots": [
        {
          "after_poi_id": "bkk-002",
          "type": "lunch",
          "start": "12:30",
          "end":   "13:45",
          "near_district": "老城区",
          "ai_hint": "卧佛寺出来推荐 Tha Tien 码头船面或附近 Krua Apsorn"
        }
      ]
    }
  ],
  "overall_tip": "整体建议（雨季穿搭 / 打车支付 / SIM 卡等）"
}`;
}

/** 一站式：拼好 messages 数组 */
export function buildMessagesV2(intake, likedRaw, maybeRaw) {
  const likedSlim = likedRaw.map(slimPoi);
  const maybeSlim = maybeRaw.map(slimPoi);
  return {
    messages: [
      { role: 'system', content: SYSTEM_PROMPT_V2 },
      { role: 'user', content: buildUserPromptV2(intake, likedSlim, maybeSlim) },
    ],
    likedSlim,
    maybeSlim,
  };
}
