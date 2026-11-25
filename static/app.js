(() => {
  "use strict";

  const DEFAULT_CENTER = [37.5665, 126.9780]; // 전국 중립 기본 위치 (서울 시청·광화문 일대)
  const MAX_CACHE_SIZE = 40;

  const GRADE_COLORS = {
    "위험(A)": "#ef4444",
    "경고(B)": "#f97316",
    "주의(C)": "#eab308",
    "보통(D)": "#38bdf8",
    "안전(E)": "#22c55e",
  };

  const STRUCTURE_COLORS = {
    "일반목구조": "#ef4444",
    "경량철골조(샌드위치패널)": "#f97316",
    "벽돌조": "#eab308",
    "일반철골조": "#38bdf8",
    "철근콘크리트조": "#22c55e",
  };

  const USAGE_COLORS = {
    "전통시장/상점가": "#ef4444",
    "창고/공장시설": "#f97316",
    "제1·2종 근린생활시설": "#eab308",
    "단독주택": "#60a5fa",
    "공동주택": "#22c55e",
    "교육연구시설": "#a855f7",
    "업무/공공시설": "#14b8a6",
  };

  const BASEMAPS = {
    vworld_base: {
      url: "/api/vworld/wmts/Base/{z}/{y}/{x}",
      attribution: "&copy; 국토교통부 브이월드(V-World)",
    },
    vworld_hybrid: {
      url: "/api/vworld/wmts/Satellite/{z}/{y}/{x}",
      overlayUrl: "/api/vworld/wmts/Hybrid/{z}/{y}/{x}",
      attribution: "&copy; 국토교통부 브이월드 위성",
    },
  };

  const state = {
    pcyData: null,
    currentBuildings: null,
    currentMeta: null,
    colorMode: "risk",
    timeItem: "시간대:주간(06-18)",
    seasonItem: "계절:봄",
    humidity: 50,
    wind: 2.5,
    showStations: true,
    selectedId: null,
    layerById: new Map(),
    pcyCache: new Map(),
    viewportCache: new Map(),
  };

  const el = {
    searchInput: document.getElementById("search-input"),
    btnSearch: document.getElementById("btn-search"),
    searchResults: document.getElementById("search-results"),
    statusText: document.getElementById("status-text"),
    btnToggleEnv: document.getElementById("btn-toggle-env"),
    envPanel: document.getElementById("env-panel"),
    envHumBadge: document.getElementById("env-hum-badge"),
    sliderHumidity: document.getElementById("slider-humidity"),
    sliderWind: document.getElementById("slider-wind"),
    valHumidity: document.getElementById("val-humidity"),
    valWind: document.getElementById("val-wind"),
    btnOpenPcyModal: document.getElementById("btn-open-pcy-modal"),
    btnToggleStations: document.getElementById("btn-toggle-stations"),
    zoomHint: document.getElementById("zoom-hint"),
    infoCard: document.getElementById("info-card"),
    btnCloseInfo: document.getElementById("btn-close-info"),
    icSub: document.getElementById("ic-sub"),
    icGrade: document.getElementById("ic-grade"),
    icName: document.getElementById("ic-name"),
    icAddr: document.getElementById("ic-addr"),
    icScoreBox: document.getElementById("ic-score-box"),
    icScore: document.getElementById("ic-score"),
    icSplit: document.getElementById("ic-split"),
    icPoiSection: document.getElementById("ic-poi-section"),
    icPoiBox: document.getElementById("ic-poi-box"),
    icPcyRules: document.getElementById("ic-pcy-rules"),
    icList: document.getElementById("ic-list"),
    pcyModal: document.getElementById("pcy-modal"),
    pcyModalBody: document.getElementById("pcy-modal-body"),
    btnClosePcyModal: document.getElementById("btn-close-pcy-modal"),
  };

  const canvasRenderer = L.canvas({ padding: 0.5 });
  const map = L.map("map", {
    center: DEFAULT_CENTER,
    zoom: 16,
    minZoom: 7,
    maxZoom: 19,
    preferCanvas: true,
    renderer: canvasRenderer,
  });

  let tileLayer = L.tileLayer(BASEMAPS.vworld_base.url, {
    attribution: BASEMAPS.vworld_base.attribution,
    maxZoom: 19,
  }).addTo(map);
  let tileOverlayLayer = null;

  const buildingGroup = L.layerGroup().addTo(map);
  const stationGroup = L.layerGroup().addTo(map);
  const routeGroup = L.layerGroup().addTo(map);

  let buildingLayer = null;
  let abortCtrl = null;
  let moveTimer = null;

  function clamp(val, min, max) {
    return Math.max(min, Math.min(max, val));
  }

  function gradeFromScore(score) {
    if (score >= 75) return "위험(A)";
    if (score >= 60) return "경고(B)";
    if (score >= 45) return "주의(C)";
    if (score >= 30) return "보통(D)";
    return "안전(E)";
  }

  function getHumidityBasketItem() {
    if (state.humidity < 30) return "습도:건조(<30)";
    if (state.humidity < 60) return "습도:보통(30-60)";
    return "습도:습함(60+)";
  }

  function synthesizeFallbackBasket(props) {
    const usage = props.usage || "제1·2종 근린생활시설";
    const usageMap = {
      "전통시장/상점가": ["장소대:판매,업무시설", "장소중:판매시설"],
      "제1·2종 근린생활시설": ["장소대:생활서비스", "장소중:음식점"],
      "단독주택": ["장소대:주거", "장소중:단독주택"],
      "공동주택": ["장소대:주거", "장소중:공동주택"],
      "창고/공장시설": ["장소대:산업시설", "장소중:공장시설"],
      "교육연구시설": ["장소대:교육시설", "장소중:교육시설"],
      "업무/공공시설": ["장소대:판매,업무시설", "장소중:일반업무"],
    };
    const wallMap = {
      "철근콘크리트조": "구조(기둥벽):철근콘크리트조",
      "벽돌조": "구조(기둥벽):벽돌조",
      "일반철골조": "구조(기둥벽):철골조",
      "경량철골조(샌드위치패널)": "구조(기둥벽):샌드위치패널조",
      "일반목구조": "구조(기둥벽):목조",
    };
    const floors = Number(props.floors || 2);
    const scale = floors <= 2 ? "건물규모:저층(1~2)" : floors <= 5 ? "건물규모:중층(3~5)" : "건물규모:고층(6+)";
    const dispatch = Number(props.dist_fire_station_m || 700) >= 1100 ? "출동도착:7분이상" : "출동도착:7분미만";
    return [
      ...(usageMap[usage] || ["장소대:생활서비스", "장소중:음식점"]),
      wallMap[props.structure] || "구조(기둥벽):철근콘크리트조",
      `구조(지붕):${props.roof_type || "슬라브가"}`,
      scale,
      dispatch,
    ];
  }

  function matchBuildingPcy(props) {
    const rules = state.pcyData?.rules;
    if (!rules || rules.length === 0) return [];

    const staticItems = Array.isArray(props.static_basket) && props.static_basket.length > 0
      ? props.static_basket
      : synthesizeFallbackBasket(props);
    const humItem = getHumidityBasketItem();
    const cacheKey = `${staticItems.join("|")}#${state.timeItem}#${state.seasonItem}#${humItem}`;

    if (state.pcyCache.has(cacheKey)) {
      return state.pcyCache.get(cacheKey);
    }

    const basketSet = new Set([...staticItems, state.timeItem, state.seasonItem, humItem]);
    const matched = [];
    for (let i = 0; i < rules.length; i++) {
      const rule = rules[i];
      let ok = true;
      for (let j = 0; j < rule.items.length; j++) {
        if (!basketSet.has(rule.items[j])) {
          ok = false;
          break;
        }
      }
      if (ok) matched.push(rule);
    }
    matched.sort((a, b) => b.max_ratio - a.max_ratio || b.total_fires - a.total_fires);
    state.pcyCache.set(cacheKey, matched);
    return matched;
  }

  function computeWeatherDelta(props) {
    const h = state.humidity;
    const w = state.wind;
    let delta = 0;

    if (h < 45) delta += (45 - h) * 0.14;
    else if (h > 65) delta -= (h - 65) * 0.12;
    if (w > 4) delta += (w - 4) * 0.75;

    if (delta > 0) {
      let mult = 1.0;
      if ((props.neighbor_count_30m || 0) >= 4) mult += 0.15;
      if (props.structure === "일반목구조" || props.structure === "경량철골조(샌드위치패널)") {
        mult += 0.15;
      }
      delta *= mult;
    }
    return Math.round(delta);
  }

  function evaluateBuilding(props) {
    const spatialBase = Math.round(Number(props.risk_score || 0) * 0.7);
    const matchedRules = matchBuildingPcy(props);
    const maxLift = matchedRules.length > 0 ? matchedRules[0].max_ratio : 1.0;
    let pcyBonus = 0;
    if (maxLift > 1.0) {
      pcyBonus = clamp(
        Math.round(Math.log2(maxLift) * 8.5 + (matchedRules.length >= 3 ? 2 : 0)),
        0,
        30
      );
    }
    const weatherDelta = computeWeatherDelta(props);
    const dynamicScore = clamp(spatialBase + pcyBonus + weatherDelta, 0, 100);
    const dynamicGrade = gradeFromScore(dynamicScore);
    return { dynamicScore, dynamicGrade, spatialBase, pcyBonus, weatherDelta, maxLift, matchedRules };
  }

  function pcyLiftColor(lift) {
    if (lift >= 6.0) return "#ef4444";
    if (lift >= 3.0) return "#f97316";
    if (lift >= 2.0) return "#eab308";
    if (lift > 1.0) return "#38bdf8";
    return "#22c55e";
  }

  function ageColor(age) {
    if (age >= 40) return "#ef4444";
    if (age >= 30) return "#f97316";
    if (age >= 20) return "#eab308";
    if (age >= 10) return "#38bdf8";
    return "#22c55e";
  }

  function styleBuilding(feature, highlight = false) {
    const props = feature.properties;
    const evalRes = evaluateBuilding(props);
    let fillColor = GRADE_COLORS[evalRes.dynamicGrade] || "#64748b";

    if (state.colorMode === "pcy") fillColor = pcyLiftColor(evalRes.maxLift);
    else if (state.colorMode === "usage") fillColor = USAGE_COLORS[props.usage] || "#94a3b8";
    else if (state.colorMode === "structure") fillColor = STRUCTURE_COLORS[props.structure] || "#94a3b8";
    else if (state.colorMode === "age") fillColor = ageColor(Number(props.age || 0));

    const selected = state.selectedId === props.id;
    if (highlight || selected) {
      return {
        color: selected ? "#1d4ed8" : "#0f172a",
        weight: selected ? 2.6 : 1.8,
        opacity: 1,
        fillColor,
        fillOpacity: 0.85,
      };
    }

    let fillOpacity = 0.65;
    if (state.colorMode === "risk") {
      if (evalRes.dynamicGrade === "위험(A)" || evalRes.dynamicGrade === "경고(B)") fillOpacity = 0.82;
      else if (evalRes.dynamicGrade === "주의(C)") fillOpacity = 0.64;
      else fillOpacity = 0.42;
    } else if (state.colorMode === "pcy") {
      fillOpacity = evalRes.maxLift >= 3.0 ? 0.82 : evalRes.maxLift >= 2.0 ? 0.64 : 0.42;
    }

    const zoomedIn = map.getZoom() >= 16;
    return {
      color: "#1e293b",
      weight: zoomedIn ? 0.9 : 0.4,
      opacity: zoomedIn ? 0.62 : 0.4,
      fillColor,
      fillOpacity,
    };
  }

  function formatDist(m) {
    const v = Number(m || 0);
    return v >= 1000 ? `${(v / 1000).toFixed(2)}km` : `${Math.round(v)}m`;
  }

  function updateSummaryStatus(fromCache = false) {
    const features = state.currentBuildings?.features || [];
    const total = features.length;
    if (total === 0) {
      el.statusText.textContent = "표시된 건물 없음";
      return;
    }
    let sum = 0;
    let high = 0;
    features.forEach((f) => {
      const r = evaluateBuilding(f.properties);
      sum += r.dynamicScore;
      if (r.dynamicGrade === "위험(A)" || r.dynamicGrade === "경고(B)") high += 1;
    });
    const avg = (sum / total).toFixed(1);
    const secLabel = fromCache ? "캐시" : `${state.currentMeta?.elapsed_sec ?? "-"}초`;
    const poiCnt = state.currentMeta?.fire_poi_total || 0;
    const poiPart = poiCnt > 0 ? ` · 화기업소 ${poiCnt.toLocaleString()}곳` : "";
    el.statusText.textContent = `현재 화면 ${total.toLocaleString()}동 (${secLabel}) · 평균 ${avg}점 · 위험·경고 ${high.toLocaleString()}동${poiPart}`;
  }

  function showInfoCard(feature) {
    const p = feature.properties;
    const prevId = state.selectedId;
    state.selectedId = p.id;

    if (prevId !== null && state.layerById.has(prevId)) {
      const prev = state.layerById.get(prevId);
      prev.setStyle(styleBuilding(prev.feature, false));
    }
    if (state.layerById.has(p.id)) {
      const curr = state.layerById.get(p.id);
      curr.setStyle(styleBuilding(curr.feature, true));
    }

    const {
      dynamicScore,
      dynamicGrade,
      spatialBase,
      pcyBonus,
      weatherDelta,
      matchedRules,
    } = evaluateBuilding(p);
    const gradeColor = GRADE_COLORS[dynamicGrade] || "#64748b";

    el.icSub.textContent = p.subdistrict || "-";
    el.icGrade.textContent = dynamicGrade;
    el.icGrade.style.background = gradeColor;
    el.icName.textContent = p.name || "건물";
    el.icAddr.textContent = p.address || "-";
    el.icScore.textContent = `${dynamicScore}`;
    el.icScore.style.color = gradeColor;
    el.icScoreBox.style.borderColor = gradeColor;

    const wText = weatherDelta === 0 ? "" : ` · 기상 ${weatherDelta > 0 ? "+" : ""}${weatherDelta}점`;
    const poiScore = Number(p.score_poi || p.fire_poi_score || 0);
    const poiPart = poiScore > 0 ? ` (화기업소 +${poiScore}점 포함)` : "";
    el.icSplit.textContent = `물리·공간 ${spatialBase}점${poiPart} + PCY(k=2) +${pcyBonus}점${wText}`;

    const poiCnt = Number(p.fire_poi_count || 0);
    if (poiCnt > 0) {
      const typesHtml = (p.fire_poi_types || [])
        .map((t) => `<span class="poi-tag">${t}</span>`)
        .join("");
      const namesStr = (p.fire_poi_names || []).join(", ");
      el.icPoiBox.innerHTML = `
        <div class="poi-head">
          <span>발견된 화기 취급 업소 ${poiCnt}곳</span>
          <span>발화 가중 +${poiScore}점</span>
        </div>
        <div class="poi-type-tags">${typesHtml}</div>
        ${namesStr ? `<div class="poi-names">입점 예시: ${namesStr}</div>` : ""}
      `;
      el.icPoiSection.classList.remove("hidden");
    } else {
      el.icPoiSection.classList.add("hidden");
    }

    el.icPcyRules.innerHTML = "";
    if (matchedRules.length === 0) {
      el.icPcyRules.innerHTML = '<p class="muted-note">현재 조건에서 고위험 PCY(k=2) 복합 패턴 미발동</p>';
    } else {
      matchedRules.slice(0, 3).forEach((rule) => {
        const card = document.createElement("div");
        card.className = "pcy-rule-card";
        const tagsHtml = rule.items.map((item) => `<span class="pcy-tag">${item}</span>`).join("");
        card.innerHTML = `
          <div class="pcy-rule-top">
            <span class="pcy-audit-badge">${rule.audit_label}</span>
            <span class="pcy-lift-badge">${rule.primary_target} ${rule.max_ratio.toFixed(1)}배</span>
          </div>
          <div class="pcy-tags">${tagsHtml}</div>
          <div class="pcy-stats-line">
            소방청 ${rule.total_fires.toLocaleString()}건 중 대형재산 ${rule.count_prop}건(<strong>${rule.ratio_prop}배</strong>) · 인명피해 ${rule.count_cas}건(<strong>${rule.ratio_cas}배</strong>)<br/>
            발화: <strong>${rule.top_cause}</strong> · 확산: <strong>${rule.top_spread}</strong>
          </div>
          <div class="pcy-checklist">✓ ${rule.checklist}</div>
        `;
        el.icPcyRules.appendChild(card);
      });
    }

    const rows = [
      ["주용도", p.usage || "-"],
      ["주구조", p.structure || "-"],
      ["지붕구조", p.roof_type || "-"],
      ["준공연도", p.built_year ? `${p.built_year}년 (${p.age}년)` : "-"],
      ["지상층수", p.floors ? `${p.floors}층` : "-"],
      ["바닥 / 연면적", `${Math.round(p.footprint_area_m2 || 0).toLocaleString()}㎡ / ${Math.round(p.total_area_m2 || 0).toLocaleString()}㎡`],
      ["화기 취급 업소", p.fire_poi_count > 0 ? `${p.fire_poi_count}곳 (${(p.fire_poi_types || []).join(", ")})` : "확인된 업소 없음"],
      ["최근접 소방서", p.nearest_fire_station ? `${p.nearest_fire_station} (${formatDist(p.dist_fire_station_m)})` : "-"],
      ["데이터 출처", p.data_source || "브이월드 GIS"],
    ];

    el.icList.innerHTML = "";
    rows.forEach(([k, v]) => {
      const dt = document.createElement("dt");
      dt.textContent = k;
      const dd = document.createElement("dd");
      dd.textContent = v;
      el.icList.append(dt, dd);
    });

    routeGroup.clearLayers();
    if (p.centroid_lat && p.centroid_lon && p.nearest_station_lat && p.nearest_station_lon) {
      L.polyline(
        [
          [p.centroid_lat, p.centroid_lon],
          [p.nearest_station_lat, p.nearest_station_lon],
        ],
        { color: "#dc2626", weight: 2, dashArray: "5, 5", opacity: 0.85 }
      ).addTo(routeGroup);
    }

    el.infoCard.classList.remove("hidden");
  }

  function closeInfoCard() {
    if (state.selectedId !== null && state.layerById.has(state.selectedId)) {
      const prev = state.layerById.get(state.selectedId);
      prev.setStyle(styleBuilding(prev.feature, false));
    }
    state.selectedId = null;
    routeGroup.clearLayers();
    el.infoCard.classList.add("hidden");
  }

  function renderBuildings(geojson) {
    state.currentBuildings = geojson;
    buildingGroup.clearLayers();
    state.layerById.clear();
    buildingLayer = null;

    if (!geojson || !Array.isArray(geojson.features)) return;

    buildingLayer = L.geoJSON(geojson, {
      renderer: canvasRenderer,
      style: (f) => styleBuilding(f, false),
      onEachFeature: (feature, layer) => {
        const p = feature.properties;
        state.layerById.set(p.id, layer);

        const ev = evaluateBuilding(p);
        const pcyStr = ev.maxLift > 1.0 ? ` · PCY ${ev.maxLift.toFixed(1)}배` : "";
        const poiTip = p.fire_poi_count > 0 ? `<br/>🔥 화기업소 ${p.fire_poi_count}곳 (${(p.fire_poi_types || []).slice(0, 2).join(", ")})` : "";
        const tip = `<strong>${p.name || "건물"}</strong><br/>위험도 ${ev.dynamicScore}점 (${ev.dynamicGrade})${pcyStr}<br/>${p.usage || "-"} · ${p.floors || "-"}층 · ${p.built_year || "-"}년${poiTip}`;
        layer.bindTooltip(tip, { sticky: true, direction: "top", className: "bldg-tooltip", offset: [0, -6] });

        layer.on({
          mouseover: () => layer.setStyle(styleBuilding(feature, true)),
          mouseout: () => layer.setStyle(styleBuilding(feature, false)),
          click: () => showInfoCard(feature),
        });
      },
    }).addTo(buildingGroup);
  }

  function restyleAll() {
    if (!buildingLayer) return;
    buildingLayer.eachLayer((layer) => {
      const feature = layer.feature;
      const p = feature.properties;
      layer.setStyle(styleBuilding(feature, false));
      const ev = evaluateBuilding(p);
      const pcyStr = ev.maxLift > 1.0 ? ` · PCY ${ev.maxLift.toFixed(1)}배` : "";
      const poiTip = p.fire_poi_count > 0 ? `<br/>🔥 화기업소 ${p.fire_poi_count}곳 (${(p.fire_poi_types || []).slice(0, 2).join(", ")})` : "";
      layer.setTooltipContent(
        `<strong>${p.name || "건물"}</strong><br/>위험도 ${ev.dynamicScore}점 (${ev.dynamicGrade})${pcyStr}<br/>${p.usage || "-"} · ${p.floors || "-"}층 · ${p.built_year || "-"}년${poiTip}`
      );
    });
    updateSummaryStatus(true);
    if (state.selectedId !== null && state.layerById.has(state.selectedId)) {
      showInfoCard(state.layerById.get(state.selectedId).feature);
    }
  }

  function renderStations(stations) {
    stationGroup.clearLayers();
    (stations || []).forEach((st) => {
      const marker = L.marker([st.lat, st.lon], {
        icon: L.divIcon({
          className: "station-pin",
          html: `🚒 ${st.name}`,
          iconSize: null,
        }),
      });
      marker.bindPopup(`<strong>${st.name}</strong><br/>${st.address || ""}`);
      marker.addTo(stationGroup);
    });
    if (state.showStations && !map.hasLayer(stationGroup)) stationGroup.addTo(map);
    if (!state.showStations && map.hasLayer(stationGroup)) map.removeLayer(stationGroup);
  }

  function setCache(key, data) {
    if (state.viewportCache.has(key)) state.viewportCache.delete(key);
    state.viewportCache.set(key, data);
    if (state.viewportCache.size > MAX_CACHE_SIZE) {
      const oldest = state.viewportCache.keys().next().value;
      state.viewportCache.delete(oldest);
    }
  }

  function applyViewportData(data, fromCache = false) {
    closeInfoCard();
    state.currentMeta = data.meta || {};
    renderBuildings(data.buildings);
    renderStations(data.stations);
    updateSummaryStatus(fromCache);
  }

  async function fetchViewportBuildings() {
    const zoom = map.getZoom();
    if (zoom < 16) {
      if (abortCtrl) abortCtrl.abort();
      closeInfoCard();
      state.currentBuildings = null;
      buildingGroup.clearLayers();
      stationGroup.clearLayers();
      state.layerById.clear();
      buildingLayer = null;
      el.zoomHint.classList.remove("hidden");
      el.statusText.textContent = "줌 16 이상 확대 시 현재 화면 건물 조회";
      return;
    }

    el.zoomHint.classList.add("hidden");
    const b = map.getBounds();
    const bbox = [
      b.getWest().toFixed(4),
      b.getSouth().toFixed(4),
      b.getEast().toFixed(4),
      b.getNorth().toFixed(4),
    ].join(",");

    if (state.viewportCache.has(bbox)) {
      applyViewportData(state.viewportCache.get(bbox), true);
      return;
    }

    if (abortCtrl) abortCtrl.abort();
    abortCtrl = new AbortController();
    el.statusText.textContent = "현재 화면 건물 · PCY 위험도 불러오는 중...";

    try {
      const resp = await fetch(`/api/vworld/buildings?bbox=${encodeURIComponent(bbox)}`, {
        signal: abortCtrl.signal,
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || "조회 실패");

      setCache(bbox, data);
      applyViewportData(data, false);
    } catch (err) {
      if (err.name === "AbortError") return;
      el.statusText.textContent = `오류: ${err.message}`;
    }
  }

  async function runSearch() {
    const q = el.searchInput.value.trim();
    if (!q) return;
    el.searchResults.innerHTML = '<div class="sr-item muted">검색 중...</div>';
    el.searchResults.classList.remove("hidden");

    try {
      const resp = await fetch(`/api/vworld/search?q=${encodeURIComponent(q)}`);
      const data = await resp.json();
      const items = data.items || [];
      if (items.length === 0) {
        el.searchResults.innerHTML = '<div class="sr-item muted">검색 결과가 없습니다.</div>';
        return;
      }
      el.searchResults.innerHTML = "";
      items.forEach((it) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "sr-item";
        btn.innerHTML = `<strong>${it.title}</strong><span>${it.address || it.category || ""}</span>`;
        btn.addEventListener("click", () => {
          el.searchResults.classList.add("hidden");
          map.flyTo([it.lat, it.lon], 17, { duration: 0.7 });
        });
        el.searchResults.appendChild(btn);
      });
    } catch (err) {
      el.searchResults.innerHTML = `<div class="sr-item muted">검색 오류: ${err.message}</div>`;
    }
  }

  function renderPcyReportModal() {
    if (!state.pcyData) {
      el.pcyModalBody.innerHTML = "<p class='muted-note'>PCY 규칙 데이터를 불러오지 못했습니다.</p>";
      return;
    }
    const meta = state.pcyData.metadata;
    const bench = meta.benchmark || {};
    const pc = bench.pcy || {};
    const topRules = (state.pcyData.rules || []).slice(0, 12);

    const rowsHtml = topRules
      .map(
        (r, i) => `
        <tr>
          <td>${i + 1}</td>
          <td>${r.items.join(" + ")}</td>
          <td><strong>${r.max_ratio.toFixed(1)}배</strong> (${r.primary_target})</td>
          <td>${r.top_cause}</td>
          <td>${r.top_spread}</td>
        </tr>
      `
      )
      .join("");

    el.pcyModalBody.innerHTML = `
      <div class="bench-grid">
        <div class="bench-kpi"><span>원본 소방청 데이터</span><strong>${meta.n_total_fires.toLocaleString()}건</strong></div>
        <div class="bench-kpi"><span>건축물 화재 분석</span><strong>${meta.n_building_fires.toLocaleString()}건</strong></div>
        <div class="bench-kpi"><span>PCY C2 후보 절감률</span><strong>${((bench.c2_reduction || 0) * 100).toFixed(1)}%</strong></div>
        <div class="bench-kpi"><span>추출 규칙 (k=2 쌍)</span><strong>${meta.rule_count}개</strong></div>
      </div>

      <div class="discard-box">
        <strong>💡 PCY 단독 (k=2) + 브이월드 공간정보 결합 원리:</strong><br/>
        <code>PCY</code> 알고리즘은 Pass 1에서 모든 2-항목 쌍을 <strong>${(pc.n_buckets || 32771).toLocaleString()}개 해시 버킷</strong>으로 압축해 비트맵을 만들고,
        Pass 2에서 빈발 버킷을 통과한 <code>k=2</code> 위험 쌍(<strong>L2</strong>)만 고속 추출합니다.
        여기에 브이월드의 실제 건축물대장 수치(연식·구조·층수·소방거리)를 복원해 결합했습니다.
      </div>

      <h3>1. PCY 단독 (k=2) 실행 요약</h3>
      <table class="bench-table">
        <thead>
          <tr><th>알고리즘 / 차수</th><th>L1 빈발 아이템</th><th>전체 가능 쌍</th><th>비트맵 통과 C2 후보</th><th>확정 L2 빈발 쌍</th><th>소요 시간</th></tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>PCY 단독 (k=${meta.max_k || 2})</strong></td>
            <td>${pc.l1_frequent_items || "-"}개</td>
            <td>${(pc.naive_c2_pairs || bench.naive_c2_pairs || 0).toLocaleString()}쌍</td>
            <td><strong>${(pc.c2_candidates || 0).toLocaleString()}쌍</strong> (${((bench.c2_reduction || 0) * 100).toFixed(1)}% 절감)</td>
            <td>${(pc.l2_frequent_pairs || 0).toLocaleString()}쌍</td>
            <td>${pc.seconds || "-"}초</td>
          </tr>
        </tbody>
      </table>

      <h3>2. 주요 발굴 k=2 복합 화재 위험 쌍 (상위 12개)</h3>
      <table class="bench-table">
        <thead>
          <tr><th>#</th><th>k=2 조건 쌍</th><th>위험 배수(Lift)</th><th>주요 발화요인</th><th>주요 연소확대물</th></tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    `;
  }

  function updateEnvUiSync() {
    el.valHumidity.textContent = `${state.humidity}%`;
    el.valWind.textContent = `${state.wind} m/s`;
    el.envHumBadge.textContent = getHumidityBasketItem();
    document.querySelectorAll("#time-seg .seg-btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.time === state.timeItem);
    });
    document.querySelectorAll("#season-seg .seg-btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.season === state.seasonItem);
    });
  }

  function bindEvents() {
    el.btnSearch.addEventListener("click", runSearch);
    el.searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        runSearch();
      }
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest("#search-box")) {
        el.searchResults.classList.add("hidden");
      }
    });

    el.btnToggleEnv.addEventListener("click", () => {
      const hidden = el.envPanel.classList.toggle("hidden");
      el.btnToggleEnv.classList.toggle("active", !hidden);
    });

    document.querySelectorAll("#time-seg .seg-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".preset-btn").forEach((b) => b.classList.remove("active"));
        state.timeItem = btn.dataset.time;
        updateEnvUiSync();
        restyleAll();
      });
    });

    document.querySelectorAll("#season-seg .seg-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".preset-btn").forEach((b) => b.classList.remove("active"));
        state.seasonItem = btn.dataset.season;
        updateEnvUiSync();
        restyleAll();
      });
    });

    el.sliderHumidity.addEventListener("input", () => {
      document.querySelectorAll(".preset-btn").forEach((b) => b.classList.remove("active"));
      state.humidity = Number(el.sliderHumidity.value);
      updateEnvUiSync();
      restyleAll();
    });

    el.sliderWind.addEventListener("input", () => {
      document.querySelectorAll(".preset-btn").forEach((b) => b.classList.remove("active"));
      state.wind = Number(el.sliderWind.value);
      updateEnvUiSync();
      restyleAll();
    });

    document.querySelectorAll(".preset-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".preset-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.timeItem = btn.dataset.time;
        state.seasonItem = btn.dataset.season;
        state.humidity = Number(btn.dataset.humidity);
        state.wind = Number(btn.dataset.wind);
        el.sliderHumidity.value = state.humidity;
        el.sliderWind.value = state.wind;
        updateEnvUiSync();
        restyleAll();
      });
    });

    document.querySelectorAll("[data-basemap]").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll("[data-basemap]").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        const spec = BASEMAPS[btn.dataset.basemap] || BASEMAPS.vworld_base;
        map.removeLayer(tileLayer);
        if (tileOverlayLayer) {
          map.removeLayer(tileOverlayLayer);
          tileOverlayLayer = null;
        }
        tileLayer = L.tileLayer(spec.url, { attribution: spec.attribution, maxZoom: 19 }).addTo(map);
        tileLayer.bringToBack();
        if (spec.overlayUrl) {
          tileOverlayLayer = L.tileLayer(spec.overlayUrl, { maxZoom: 19, pane: "tilePane" }).addTo(map);
        }
      });
    });

    document.querySelectorAll("[data-color]").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll("[data-color]").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.colorMode = btn.dataset.color;
        restyleAll();
      });
    });

    el.btnToggleStations.addEventListener("click", () => {
      state.showStations = !state.showStations;
      el.btnToggleStations.classList.toggle("active", state.showStations);
      if (state.showStations) stationGroup.addTo(map);
      else map.removeLayer(stationGroup);
    });

    el.btnCloseInfo.addEventListener("click", closeInfoCard);

    el.btnOpenPcyModal.addEventListener("click", () => {
      renderPcyReportModal();
      el.pcyModal.classList.remove("hidden");
    });
    el.btnClosePcyModal.addEventListener("click", () => el.pcyModal.classList.add("hidden"));
    el.pcyModal.addEventListener("click", (e) => {
      if (e.target === el.pcyModal) el.pcyModal.classList.add("hidden");
    });

    map.on("moveend", () => {
      clearTimeout(moveTimer);
      moveTimer = setTimeout(fetchViewportBuildings, 200);
    });
    map.on("zoomend", restyleAll);
  }

  async function init() {
    bindEvents();
    updateEnvUiSync();
    try {
      const pResp = await fetch("data/jochiwon_pcy_rules.json");
      state.pcyData = pResp.ok ? await pResp.json() : null;
    } catch {
      state.pcyData = null;
    }
    await fetchViewportBuildings();
  }

  init();
})();
