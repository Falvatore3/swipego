/**
 * fillTimeline — 把 AI v2 输出的 items[] + meal_slots[] 合并成按时刻排序的 timeline
 *
 * Input:  AIPlan（来自 prompt-v2 输出）+ poiMap（id → 完整 POI）
 * Output: FinalDay[]，每天一个 timeline 数组，混合 poi / meal_placeholder 两种 block
 *
 * 这是纯函数，无副作用，浏览器 / Node 都能跑。
 */

/** "HH:MM" → 分钟数（用于排序） */
function parseTime(hhmm) {
  if (!hhmm || typeof hhmm !== 'string') return -1;
  const m = /^(\d{1,2}):(\d{2})$/.exec(hhmm.trim());
  if (!m) return -1;
  return parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
}

/** 校验时刻字符串合法性 */
function isValidTime(s) {
  return parseTime(s) >= 0;
}

/**
 * @param {AIPlan} plan       DeepSeek 返回的 parsed JSON
 * @param {Object<string,POI>} poiMap   id → 完整 POI（来自 liked + maybe）
 * @returns {FinalDay[]}
 */
export function fillTimeline(plan, poiMap) {
  if (!plan || !Array.isArray(plan.days)) {
    console.warn('[fillTimeline] plan.days 不是数组', plan);
    return [];
  }

  return plan.days.map((day, idx) => {
    const blocks = [];

    // 1. items → poi blocks
    for (const it of day.items || []) {
      const poi = poiMap[it.poi_id];
      if (!poi) {
        console.warn(`[fillTimeline] day ${day.day} 找不到 poi_id=${it.poi_id}，丢弃`);
        continue;
      }
      if (!isValidTime(it.start) || !isValidTime(it.end)) {
        console.warn(`[fillTimeline] day ${day.day} poi=${it.poi_id} 时刻非法 ${it.start}-${it.end}，丢弃`);
        continue;
      }
      blocks.push({
        type: 'poi',
        poi,
        start: it.start,
        end: it.end,
        note: it.note || '',
      });
    }

    // 2. meal_slots → meal_placeholder blocks
    for (const m of day.meal_slots || []) {
      if (!isValidTime(m.start) || !isValidTime(m.end)) {
        console.warn(`[fillTimeline] day ${day.day} meal 时刻非法 ${m.start}-${m.end}，丢弃`);
        continue;
      }
      const afterPoi = poiMap[m.after_poi_id]; // 允许找不到，作为软依赖
      blocks.push({
        type: 'meal_placeholder',
        meal_type: m.type || 'lunch',
        start: m.start,
        end: m.end,
        near_district: m.near_district || (afterPoi?.district_zh || afterPoi?.district || ''),
        near_lat: afterPoi?.lat ?? null,
        near_lng: afterPoi?.lng ?? null,
        ai_hint: m.ai_hint || '',
        after_poi_id: m.after_poi_id || null,
        user_chosen_poi: null, // 用户选了之后填进来
      });
    }

    // 3. 按 start 排序
    blocks.sort((a, b) => parseTime(a.start) - parseTime(b.start));

    return {
      day: day.day || idx + 1,
      theme: day.theme || `Day ${idx + 1}`,
      timeline: blocks,
    };
  });
}

/**
 * 用户在前端选了餐厅后，替换某个 meal_placeholder 的 user_chosen_poi
 * 返回新的 finalDays（不可变更新）
 */
export function setMealChoice(finalDays, dayIdx, blockIdx, chosenPoi) {
  return finalDays.map((d, i) => {
    if (i !== dayIdx) return d;
    return {
      ...d,
      timeline: d.timeline.map((b, j) => {
        if (j !== blockIdx) return b;
        if (b.type !== 'meal_placeholder') return b;
        return { ...b, user_chosen_poi: chosenPoi };
      }),
    };
  });
}

/**
 * 给餐位抽屉用：在 POI 数据库里找"附近的美食类 POI"
 * @param {POI[]} allPois        bangkok-pois.json 里的 pois 数组
 * @param {{lat:number,lng:number}} center
 * @param {number} radiusKm
 */
export function findNearbyFoodPois(allPois, center, radiusKm = 1.5) {
  if (!center || center.lat == null || center.lng == null) {
    // 没坐标就直接返回所有美食 POI
    return allPois.filter(isFoodPoi).slice(0, 20);
  }
  return allPois
    .filter(isFoodPoi)
    .map(p => ({ poi: p, dist: haversineKm(center, p) }))
    .filter(x => x.dist <= radiusKm)
    .sort((a, b) => a.dist - b.dist)
    .slice(0, 20)
    .map(x => x.poi);
}

function isFoodPoi(p) {
  const cat = (p.category || '').toLowerCase();
  const label = p.category_label || '';
  return cat === 'food' || cat === 'restaurant' || /美食|餐厅|餐|小吃|夜市/.test(label);
}

/** 简易 haversine 距离（km） */
function haversineKm(a, b) {
  const R = 6371;
  const dLat = (b.lat - a.lat) * Math.PI / 180;
  const dLng = (b.lng - a.lng) * Math.PI / 180;
  const lat1 = a.lat * Math.PI / 180;
  const lat2 = b.lat * Math.PI / 180;
  const x = Math.sin(dLat / 2) ** 2 + Math.sin(dLng / 2) ** 2 * Math.cos(lat1) * Math.cos(lat2);
  return 2 * R * Math.asin(Math.sqrt(x));
}
