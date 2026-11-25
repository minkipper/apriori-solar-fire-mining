(() => {
  "use strict";

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
      attribution: "&copy; 국토교통부 브이월드 위성·하이브리드",
    },
    voyager: {
      url: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
      attribution: "&copy; OpenStreetMap &copy; CARTO",
    },
    light: {
      url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
      attribution: "&copy; OpenStreetMap &copy; CARTO",
    },
    osm: {
      url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      attribution: "&copy; OpenStreetMap contributors",
    },
    dark: {
      url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
      attribution: "&copy; OpenStreetMap &copy; CARTO",
    },
    satellite: {
      url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      attribution: "&copy; Esri World Imagery",
    },
  };

  const RI_CENTERS = [
    ["원리", 36.6014, 127.2993],
    ["상리", 36.6020, 127.3023],
    ["명리", 36.6029, 127.3005],
    ["평리", 36.6051, 127.3012],
    ["교리", 36.6041, 127.2987],
    ["정리", 36.5998, 127.2996],
    ["남리", 36.5971, 127.2993],
    ["침산리", 36.6022, 127.2920],
    ["신흥리", 36.5959, 127.2912],
    ["죽림리", 36.5916, 127.2953],
    ["신안리", 36.6156, 127.2855],
    ["서창리", 36.6076, 127.2901],
    ["번암리", 36.5865, 127.2961],
    ["봉산리", 36.6038, 127.2825],
  ];

  const state = {
    rawBuildings: null,
    defaultBuildings: null,
    infraData: null,
    pcyData: null,
    mode: "risk",
    timeItem: "시간대:주간(06-18)",
    seasonItem: "계절:봄",
    humidity: 50,
    wind: 2.5,
    fillOpacity: 0.78,
    smartOpacity: true,
    search: "",
    ri: "ALL",
    grade: "ALL",
    usage: "ALL",
    highOnly: false,
    selectedId: null,
    hoveredLayer: null,
    lastZoomDetail: false,
    vworldLive: false,
    isDefaultDataset: true,
    layerById: new Map(),
    pcyCache: new Map(),
  };

  // DOM 참조
  const el = {
    vworldBadge: document.getElementById("vworld-badge"),
    vworldSearchInput: document.getElementById("vworld-search-input"),
    btnVworldSearch: document.getElementById("btn-vworld-search"),
    vworldSearchResults: document.getElementById("vworld-search-results"),
    toggleVworldLive: document.getElementById("toggle-vworld-live"),
    btnFetchViewport: document.getElementById("btn-fetch-viewport"),
    btnRestoreJochiwon: document.getElementById("btn-restore-jochiwon"),
    vworldLiveStatus: document.getElementById("vworld-live-status"),
    statTotal: document.getElementById("stat-total"),
    statAvg: document.getElementById("stat-avg"),
    statHigh: document.getElementById("stat-high"),
    statPcyMatched: document.getElementById("stat-pcy-matched"),
    envHumBadge: document.getElementById("env-hum-badge"),
    searchInput: document.getElementById("search-input"),
    filterRi: document.getElementById("filter-ri"),
    filterGrade: document.getElementById("filter-grade"),
    filterUsage: document.getElementById("filter-usage"),
    toggleHighOnly: document.getElementById("toggle-high-only"),
    btnResetFilters: document.getElementById("btn-reset-filters"),
    sliderHumidity: document.getElementById("slider-humidity"),
    sliderWind: document.getElementById("slider-wind"),
    valHumidity: document.getElementById("val-humidity"),
    valWind: document.getElementById("val-wind"),
    basemapSelect: document.getElementById("basemap-select"),
    sliderOpacity: document.getElementById("slider-opacity"),
    valOpacity: document.getElementById("val-opacity"),
    toggleSmartOpacity: document.getElementById("toggle-smart-opacity"),
    layerRiLabels: document.getElementById("layer-ri-labels"),
    layerStations: document.getElementById("layer-stations"),
    layerHydrants: document.getElementById("layer-hydrants"),
    layerBoundary: document.getElementById("layer-boundary"),
    legendTitle: document.getElementById("legend-title"),
    legendBody: document.getElementById("legend-body"),
    mapStage: document.querySelector(".map-stage"),
    hoverCard: document.getElementById("hover-card"),
    hcRi: document.getElementById("hc-ri"),
    hcName: document.getElementById("hc-name"),
    hcAddr: document.getElementById("hc-addr"),
    hcScoreBox: document.getElementById("hc-score-box"),
    hcScore: document.getElementById("hc-score"),
    hcGrade: document.getElementById("hc-grade"),
    hcSplit: document.getElementById("hc-split"),
    hcUsage: document.getElementById("hc-usage"),
    hcStructure: document.getElementById("hc-structure"),
    hcAge: document.getElementById("hc-age"),
    hcScale: document.getElementById("hc-scale"),
    hcSprinkler: document.getElementById("hc-sprinkler"),
    hcNeighbors: document.getElementById("hc-neighbors"),
    hcStation: document.getElementById("hc-station"),
    hcHydrant: document.getElementById("hc-hydrant"),
    hcPcyBox: document.getElementById("hc-pcy-box"),
    hcPcyTitle: document.getElementById("hc-pcy-title"),
    hcPcyLift: document.getElementById("hc-pcy-lift"),
    hcPcyRule: document.getElementById("hc-pcy-rule"),
    hcPcyMeta: document.getElementById("hc-pcy-meta"),
    hcFactors: document.getElementById("hc-factors"),
    detailDrawer: document.getElementById("detail-drawer"),
    btnCloseDrawer: document.getElementById("btn-close-drawer"),
    ddBadge: document.getElementById("dd-badge"),
    ddName: document.getElementById("dd-name"),
    ddAddress: document.getElementById("dd-address"),
    ddScore: document.getElementById("dd-score"),
    ddWeatherNote: document.getElementById("dd-weather-note"),
    ddHybridBars: document.getElementById("dd-hybrid-bars"),
    ddPcyRules: document.getElementById("dd-pcy-rules"),
    ddBars: document.getElementById("dd-bars"),
    ddAttrs: document.getElementById("dd-attrs"),
    ddStationName: document.getElementById("dd-station-name"),
    ddStationDist: document.getElementById("dd-station-dist"),
    ddHydrantDist: document.getElementById("dd-hydrant-dist"),
    ddRecommendations: document.getElementById("dd-recommendations"),
    pcyModal: document.getElementById("pcy-modal"),
    pcyModalBody: document.getElementById("pcy-modal-body"),
    btnOpenPcyModal: document.getElementById("btn-open-pcy-modal"),
    btnClosePcyModal: document.getElementById("btn-close-pcy-modal"),
    dataModal: document.getElementById("data-modal"),
    btnOpenModal: document.getElementById("btn-open-modal"),
    btnCloseModal: document.getElementById("btn-close-modal"),
    modalDatasetInfo: document.getElementById("modal-dataset-info"),
    fileUploadInput: document.getElementById("file-upload-input"),
    btnResetDataset: document.getElementById("btn-reset-dataset"),
    uploadStatus: document.getElementById("upload-status"),
  };

  // Leaflet 지도 초기화 (Canvas 렌더러)
  const canvasRenderer = L.canvas({ padding: 0.5 });
  const map = L.map("map", {
    center: [36.6015, 127.2945],
    zoom: 15,
    minZoom: 7,
    maxZoom: 19,
    preferCanvas: true,
    renderer: canvasRenderer,
  });

  let tileLayer = L.tileLayer(BASEMAPS.voyager.url, {
    attribution: BASEMAPS.voyager.attribution,
    maxZoom: 19,
  }).addTo(map);
  let tileOverlayLayer = null;

  const boundaryGroup = L.layerGroup().addTo(map);
  const buildingGroup = L.layerGroup().addTo(map);
  const routeGroup = L.layerGroup().addTo(map);
  const hydrantGroup = L.layerGroup();
  const stationGroup = L.layerGroup().addTo(map);
  const riLabelGroup = L.layerGroup().addTo(map);

  let buildingGeoJsonLayer = null;

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

    if (h < 45) {
      delta += (45 - h) * 0.14;
    } else if (h > 65) {
      delta -= (h - 65) * 0.12;
    }

    if (w > 4) {
      delta += (w - 4) * 0.75;
    }

    if (delta > 0) {
      let mult = 1.0;
      if ((props.neighbor_count_30m || 0) >= 4) mult += 0.15;
      if (
        props.structure === "일반목구조" ||
        props.structure === "경량철골조(샌드위치패널)"
      ) {
        mult += 0.15;
      }
      delta *= mult;
    }

    return Math.round(delta);
  }

  function evaluateBuilding(props) {
    // 1. 물리·공간 연속 점수 (The Discard 복원: 0 ~ 70점)
    const spatialBase = Math.round(Number(props.risk_score || 0) * 0.7);

    // 2. PCY 복합 패턴 시너지 점수 (소방청 115,237건 마이닝 결과: 0 ~ 30점)
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

    // 3. 연속 기상(건조·강풍) 보정
    const weatherDelta = computeWeatherDelta(props);
    const dynamicScore = clamp(spatialBase + pcyBonus + weatherDelta, 0, 100);
    const dynamicGrade = gradeFromScore(dynamicScore);

    return {
      dynamicScore,
      dynamicGrade,
      spatialBase,
      pcyBonus,
      weatherDelta,
      maxLift,
      matchedRules,
    };
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

  function getPolygonStyle(feature, isHighlighted = false) {
    const props = feature.properties;
    const evalRes = evaluateBuilding(props);
    let fillColor = GRADE_COLORS[evalRes.dynamicGrade] || "#64748b";

    if (state.mode === "pcy") {
      fillColor = pcyLiftColor(evalRes.maxLift);
    } else if (state.mode === "age") {
      fillColor = ageColor(Number(props.age || 0));
    } else if (state.mode === "structure") {
      fillColor = STRUCTURE_COLORS[props.structure] || "#94a3b8";
    } else if (state.mode === "usage") {
      fillColor = USAGE_COLORS[props.usage] || "#94a3b8";
    }

    const isSelected = state.selectedId === props.id;
    const isHighDimmed =
      state.highOnly &&
      evalRes.dynamicGrade !== "위험(A)" &&
      evalRes.dynamicGrade !== "경고(B)";

    if (isHighlighted || isSelected) {
      return {
        color: isSelected ? "#0284c7" : "#ffffff",
        weight: isSelected ? 3 : 2.3,
        opacity: 1,
        fillColor,
        fillOpacity: 0.94,
      };
    }

    let computedFillOpacity = state.fillOpacity;
    if (state.smartOpacity) {
      if (state.mode === "risk") {
        if (evalRes.dynamicGrade === "위험(A)" || evalRes.dynamicGrade === "경고(B)") {
          computedFillOpacity = clamp(state.fillOpacity + 0.14, 0.25, 0.95);
        } else if (evalRes.dynamicGrade === "주의(C)") {
          computedFillOpacity = clamp(state.fillOpacity * 0.85, 0.2, 0.95);
        } else {
          computedFillOpacity = clamp(state.fillOpacity * 0.54, 0.15, 0.75);
        }
      } else if (state.mode === "pcy") {
        if (evalRes.maxLift >= 3.0) {
          computedFillOpacity = clamp(state.fillOpacity + 0.14, 0.25, 0.95);
        } else if (evalRes.maxLift >= 2.0) {
          computedFillOpacity = clamp(state.fillOpacity * 0.85, 0.2, 0.95);
        } else {
          computedFillOpacity = clamp(state.fillOpacity * 0.54, 0.15, 0.75);
        }
      }
    }

    const isZoomedIn = map.getZoom() >= 16;
    return {
      color: "#1e293b",
      weight: isZoomedIn ? 1.05 : 0.4,
      opacity: isHighDimmed ? 0.18 : isZoomedIn ? 0.8 : 0.55,
      fillColor,
      fillOpacity: isHighDimmed ? 0.09 : computedFillOpacity,
    };
  }

  function formatDist(meters) {
    const m = Number(meters || 0);
    return m >= 1000 ? `${(m / 1000).toFixed(2)}km` : `${Math.round(m)}m`;
  }

  function matchesFilter(feature) {
    const p = feature.properties;
    const evalRes = evaluateBuilding(p);

    if (state.ri !== "ALL" && p.subdistrict !== state.ri) return false;
    if (state.grade !== "ALL" && evalRes.dynamicGrade !== state.grade) return false;
    if (state.usage !== "ALL" && p.usage !== state.usage) return false;

    if (state.search) {
      const q = state.search.toLowerCase();
      const hay = `${p.name || ""} ${p.address || ""} ${p.subdistrict || ""} ${p.usage || ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  }

  function positionHoverCard(clientX, clientY) {
    const rect = el.mapStage.getBoundingClientRect();
    const cardW = 340;
    const cardH = el.hoverCard.offsetHeight || 330;

    let left = clientX - rect.left + 16;
    let top = clientY - rect.top + 16;

    if (left + cardW > rect.width - 12) {
      left = clientX - rect.left - cardW - 16;
    }
    if (top + cardH > rect.height - 12) {
      top = clientY - rect.top - cardH - 16;
    }

    el.hoverCard.style.left = `${Math.max(10, left)}px`;
    el.hoverCard.style.top = `${Math.max(10, top)}px`;
  }

  function showHoverCard(feature, originalEvent) {
    const p = feature.properties;
    const {
      dynamicScore,
      dynamicGrade,
      spatialBase,
      pcyBonus,
      weatherDelta,
      matchedRules,
    } = evaluateBuilding(p);
    const gradeColor = GRADE_COLORS[dynamicGrade] || "#64748b";

    el.hcRi.textContent = p.subdistrict || "조치원읍";
    el.hcName.textContent = p.name || "건물";
    el.hcAddr.textContent = p.address || "-";

    el.hcScoreBox.style.background = gradeColor;
    el.hcScore.textContent = `${dynamicScore}`;
    el.hcGrade.textContent = dynamicGrade;

    const weatherPart =
      weatherDelta === 0
        ? ""
        : ` · 기상 ${weatherDelta > 0 ? "+" : ""}${weatherDelta}점`;
    el.hcSplit.textContent = `공간(Discard복원) ${spatialBase}점 + PCY패턴 +${pcyBonus}점${weatherPart}`;

    el.hcUsage.textContent = p.usage || "-";
    el.hcStructure.textContent = `${p.structure || "-"} / ${p.roof_type || "슬라브가"}`;
    el.hcAge.textContent = `${p.built_year}년 (${p.age}년)`;
    el.hcScale.textContent = `${p.floors}층 · ${Math.round(p.total_area_m2 || 0).toLocaleString()}㎡`;
    el.hcSprinkler.textContent = p.has_sprinkler ? "설치" : "미설치";
    el.hcNeighbors.textContent = `${p.neighbor_count_30m || 0}동 인접`;
    el.hcStation.textContent = `${p.nearest_fire_station || "소방서"} (${formatDist(p.dist_fire_station_m)})`;
    el.hcHydrant.textContent = `소화전 ${formatDist(p.dist_hydrant_m)}`;

    if (matchedRules.length > 0) {
      const topRule = matchedRules[0];
      el.hcPcyBox.classList.remove("neutral");
      el.hcPcyTitle.textContent = `🧮 PCY 복합 위험 (${matchedRules.length}건 발동)`;
      el.hcPcyLift.textContent = `${topRule.primary_target} ${topRule.max_ratio.toFixed(1)}배`;
      el.hcPcyRule.textContent = topRule.items.join(" + ");
      el.hcPcyMeta.textContent = `주요 발화: ${topRule.top_cause} · 연소확대: ${topRule.top_spread}`;
    } else {
      el.hcPcyBox.classList.add("neutral");
      el.hcPcyTitle.textContent = "🧮 PCY 복합 위험 패턴";
      el.hcPcyLift.textContent = "기준 이하 (1.0배)";
      el.hcPcyRule.textContent = "현재 시간·계절·습도에서 통계적 고위험 복합 조합 미발동";
      el.hcPcyMeta.textContent = "물리·공간 연속 지표 중심으로 평가 중";
    }

    const factors = Array.isArray(p.risk_factors) ? p.risk_factors : [];
    el.hcFactors.innerHTML = "";
    factors.forEach((txt) => {
      const span = document.createElement("span");
      span.className = txt.includes("양호") ? "factor-tag safe" : "factor-tag";
      span.textContent = txt;
      el.hcFactors.appendChild(span);
    });

    el.hoverCard.classList.remove("hidden");
    if (originalEvent) {
      positionHoverCard(originalEvent.clientX, originalEvent.clientY);
    }
  }

  function hideHoverCard() {
    el.hoverCard.classList.add("hidden");
  }

  function drawResponseLines(p) {
    routeGroup.clearLayers();
    if (!p.centroid_lat || !p.centroid_lon) return;

    const bLatLng = [p.centroid_lat, p.centroid_lon];

    if (p.nearest_station_lat && p.nearest_station_lon) {
      const stLatLng = [p.nearest_station_lat, p.nearest_station_lon];
      L.polyline([bLatLng, stLatLng], {
        color: "#ef4444",
        weight: 2.5,
        dashArray: "6, 6",
        opacity: 0.9,
      }).addTo(routeGroup);

      const midSt = [
        (bLatLng[0] + stLatLng[0]) / 2,
        (bLatLng[1] + stLatLng[1]) / 2,
      ];
      L.marker(midSt, {
        interactive: false,
        icon: L.divIcon({
          className: "dist-label",
          html: `🚒 ${formatDist(p.dist_fire_station_m)}`,
          iconSize: null,
        }),
      }).addTo(routeGroup);
    }

    if (p.nearest_hydrant_lat && p.nearest_hydrant_lon) {
      const hydLatLng = [p.nearest_hydrant_lat, p.nearest_hydrant_lon];
      L.polyline([bLatLng, hydLatLng], {
        color: "#06b6d4",
        weight: 2.2,
        dashArray: "4, 5",
        opacity: 0.95,
      }).addTo(routeGroup);

      const midHyd = [
        (bLatLng[0] + hydLatLng[0]) / 2,
        (bLatLng[1] + hydLatLng[1]) / 2,
      ];
      L.marker(midHyd, {
        interactive: false,
        icon: L.divIcon({
          className: "dist-label",
          html: `💧 ${formatDist(p.dist_hydrant_m)}`,
          iconSize: null,
        }),
      }).addTo(routeGroup);
    }
  }

  function buildRecommendations(p, dynamicScore) {
    const recs = [];
    if (!p.has_sprinkler && (p.floors >= 3 || p.usage === "전통시장/상점가" || p.usage === "제1·2종 근린생활시설")) {
      recs.push("간이스프링클러 및 자동화재탐지설비(속보설비) 보강 권고");
    }
    if ((p.age || 0) >= 25) {
      recs.push(`준공 ${p.age}년 경과 건물로 노후 전기배선·누전차단기·가스배관 정밀점검 필요`);
    }
    if (p.structure === "경량철골조(샌드위치패널)" || p.structure === "일반목구조") {
      recs.push(`${p.structure} 특성상 화염 확산이 빠르므로 방화구획 및 외벽 난연 보강 권장`);
    }
    if ((p.neighbor_count_30m || 0) >= 4) {
      recs.push(`주변 30m 내 인접 건물 ${p.neighbor_count_30m}동 밀집 — 골목길 비상소화장치 확보 및 소방차 진입로 유지 필요`);
    }
    if ((p.dist_hydrant_m || 0) > 120) {
      recs.push(`최근접 소화전이 ${Math.round(p.dist_hydrant_m)}m 떨어져 있어 건물 내 옥외·옥내 소화전 및 대형 소화기 비치 필수`);
    }
    if (dynamicScore < 30 && recs.length === 0) {
      recs.push("전반적인 내화·소방 여건이 양호하며, 분기별 정기 소방점검 유지를 권장합니다.");
    }
    return recs;
  }

  function selectBuilding(feature) {
    const p = feature.properties;
    const prevId = state.selectedId;
    state.selectedId = p.id;

    if (prevId !== null && state.layerById.has(prevId)) {
      const prevLayer = state.layerById.get(prevId);
      prevLayer.setStyle(getPolygonStyle(prevLayer.feature, false));
    }
    if (state.layerById.has(p.id)) {
      const currLayer = state.layerById.get(p.id);
      currLayer.setStyle(getPolygonStyle(currLayer.feature, true));
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

    el.ddBadge.textContent = dynamicGrade;
    el.ddBadge.style.background = gradeColor;
    el.ddName.textContent = p.name || "건물 상세";
    el.ddAddress.textContent = p.address || "-";
    el.ddScore.textContent = dynamicScore;
    el.ddScore.style.color = gradeColor;

    el.ddWeatherNote.textContent = `공간 ${spatialBase} + PCY +${pcyBonus} + 기상 ${weatherDelta >= 0 ? "+" : ""}${weatherDelta}`;

    // 1. 하이브리드 구성 비교 바
    const hybridBars = [
      {
        label: "물리·공간 연속 점수 (Discard 복원)",
        score: spatialBase,
        max: 70,
        color: "#38bdf8",
      },
      {
        label: "PCY 복합 패턴 시너지 (11.5만건 통계)",
        score: pcyBonus,
        max: 30,
        color: "#a855f7",
      },
    ];
    el.ddHybridBars.innerHTML = "";
    hybridBars.forEach((b) => {
      const pct = clamp((b.score / b.max) * 100, 0, 100);
      const row = document.createElement("div");
      row.className = "bar-row";
      row.innerHTML = `
        <div class="bar-meta">
          <span>${b.label}</span>
          <strong>${b.score} / ${b.max}점</strong>
        </div>
        <div class="bar-track">
          <div class="bar-fill" style="width:${pct}%; background:${b.color};"></div>
        </div>
      `;
      el.ddHybridBars.appendChild(row);
    });

    // 2. 발동된 PCY 복합 위험 규칙 Top 3
    el.ddPcyRules.innerHTML = "";
    if (matchedRules.length === 0) {
      el.ddPcyRules.innerHTML =
        '<p class="helper-note">현재 선택한 시간대·계절·습도 조건에서는 1.15배 이상 고위험 PCY 복합 패턴이 발동하지 않았습니다.</p>';
    } else {
      matchedRules.slice(0, 3).forEach((rule) => {
        const card = document.createElement("div");
        card.className = "pcy-rule-card";
        const tagsHtml = rule.items
          .map((item) => `<span class="pcy-tag">${item}</span>`)
          .join("");
        card.innerHTML = `
          <div class="pcy-rule-top">
            <span class="pcy-audit-badge">${rule.audit_label}</span>
            <span class="pcy-lift-badge">${rule.primary_target} ${rule.max_ratio.toFixed(1)}배</span>
          </div>
          <div class="pcy-tags">${tagsHtml}</div>
          <div class="pcy-stats-line">
            소방청 실제 화재 ${rule.total_fires.toLocaleString()}건 중 대형재산 ${rule.count_prop}건(<strong>${rule.ratio_prop}배</strong>) · 인명피해 ${rule.count_cas}건(<strong>${rule.ratio_cas}배</strong>)<br/>
            주요 발화원: <strong>${rule.top_cause}</strong> · 연소확대물: <strong>${rule.top_spread}</strong>
          </div>
          <div class="pcy-checklist">✓ ${rule.checklist}</div>
        `;
        el.ddPcyRules.appendChild(card);
      });
    }

    // 3. 물리·공간 5대 지표
    const bars = [
      { label: "건물 노후도", score: p.score_age || 0, max: 25, color: "#f97316" },
      { label: "구조 취약성", score: p.score_structure || 0, max: 25, color: "#ef4444" },
      { label: "용도·화기위험", score: p.score_usage || 0, max: 20, color: "#eab308" },
      { label: "밀집·연소확대", score: p.score_spread || 0, max: 15, color: "#a855f7" },
      { label: "소방접근 취약", score: p.score_access || 0, max: 15, color: "#38bdf8" },
    ];

    el.ddBars.innerHTML = "";
    bars.forEach((b) => {
      const pct = clamp((b.score / b.max) * 100, 0, 100);
      const row = document.createElement("div");
      row.className = "bar-row";
      row.innerHTML = `
        <div class="bar-meta">
          <span>${b.label}</span>
          <strong>${b.score} / ${b.max}점</strong>
        </div>
        <div class="bar-track">
          <div class="bar-fill" style="width:${pct}%; background:${b.color};"></div>
        </div>
      `;
      el.ddBars.appendChild(row);
    });

    // 4. 속성 상세
    const attrs = [
      ["법정리", p.subdistrict || "-"],
      ["주용도", p.usage || "-"],
      ["기둥벽 구조", p.structure || "-"],
      ["지붕 구조", p.roof_type || "슬라브가"],
      ["준공연도", `${p.built_year}년 (경과 ${p.age}년)`],
      ["규모(층수)", `지상 ${p.floors}층`],
      ["바닥 / 연면적", `${Math.round(p.footprint_area_m2 || 0)}㎡ / ${Math.round(p.total_area_m2 || 0)}㎡`],
      ["스프링클러", p.has_sprinkler ? "설치됨" : "미설치"],
      ["반경 30m 인접", `${p.neighbor_count_30m || 0}동`],
      ["데이터 출처", p.data_source || p.osm_building_tag || "브이월드 GIS"],
    ];

    el.ddAttrs.innerHTML = "";
    attrs.forEach(([k, v]) => {
      const dt = document.createElement("dt");
      dt.textContent = k;
      const dd = document.createElement("dd");
      dd.textContent = v;
      el.ddAttrs.append(dt, dd);
    });

    el.ddStationName.textContent = p.nearest_fire_station || "-";
    el.ddStationDist.textContent = `직선거리 ${formatDist(p.dist_fire_station_m)}`;
    el.ddHydrantDist.textContent = `직선거리 ${formatDist(p.dist_hydrant_m)}`;

    const recs = buildRecommendations(p, dynamicScore);
    el.ddRecommendations.innerHTML = "";
    recs.forEach((r) => {
      const li = document.createElement("li");
      li.textContent = r;
      el.ddRecommendations.appendChild(li);
    });

    drawResponseLines(p);
    const wasHidden = el.detailDrawer.classList.contains("hidden");
    el.detailDrawer.classList.remove("hidden");
    if (wasHidden) {
      setTimeout(() => map.invalidateSize(), 50);
    }
  }

  function updateLegend(features) {
    const counts = new Map();
    let items = [];

    if (state.mode === "risk") {
      el.legendTitle.textContent = "📊 범례 · 종합 하이브리드 위험도";
      items = [
        ["위험(A) 75점↑", GRADE_COLORS["위험(A)"], "위험(A)"],
        ["경고(B) 60~74점", GRADE_COLORS["경고(B)"], "경고(B)"],
        ["주의(C) 45~59점", GRADE_COLORS["주의(C)"], "주의(C)"],
        ["보통(D) 30~44점", GRADE_COLORS["보통(D)"], "보통(D)"],
        ["안전(E) 30점↓", GRADE_COLORS["안전(E)"], "안전(E)"],
      ];
      features.forEach((f) => {
        const g = evaluateBuilding(f.properties).dynamicGrade;
        counts.set(g, (counts.get(g) || 0) + 1);
      });
    } else if (state.mode === "pcy") {
      el.legendTitle.textContent = "📊 범례 · PCY 복합패턴 배수(Lift)";
      items = [
        ["초고위험 (6.0배↑)", "#ef4444", "6+"],
        ["고위험 (3.0~5.9배)", "#f97316", "3-5"],
        ["주의 (2.0~2.9배)", "#eab308", "2-3"],
        ["경미 (1.15~1.9배)", "#38bdf8", "1-2"],
        ["매칭 없음 (기준 이하)", "#22c55e", "none"],
      ];
      features.forEach((f) => {
        const lift = evaluateBuilding(f.properties).maxLift;
        const k = lift >= 6 ? "6+" : lift >= 3 ? "3-5" : lift >= 2 ? "2-3" : lift > 1 ? "1-2" : "none";
        counts.set(k, (counts.get(k) || 0) + 1);
      });
    } else if (state.mode === "age") {
      el.legendTitle.textContent = "📊 범례 · 건물 노후도 (연식)";
      items = [
        ["40년 이상 (1986년 이전)", "#ef4444", "40+"],
        ["30~39년 (1987~1996년)", "#f97316", "30-39"],
        ["20~29년 (1997~2006년)", "#eab308", "20-29"],
        ["10~19년 (2007~2016년)", "#38bdf8", "10-19"],
        ["10년 미만 (신축)", "#22c55e", "<10"],
      ];
      features.forEach((f) => {
        const a = Number(f.properties.age || 0);
        const k = a >= 40 ? "40+" : a >= 30 ? "30-39" : a >= 20 ? "20-29" : a >= 10 ? "10-19" : "<10";
        counts.set(k, (counts.get(k) || 0) + 1);
      });
    } else if (state.mode === "structure") {
      el.legendTitle.textContent = "📊 범례 · 건물 주구조";
      items = Object.entries(STRUCTURE_COLORS).map(([k, color]) => [k, color, k]);
      features.forEach((f) => {
        const s = f.properties.structure || "기타";
        counts.set(s, (counts.get(s) || 0) + 1);
      });
    } else {
      el.legendTitle.textContent = "📊 범례 · 건물 주용도";
      items = Object.entries(USAGE_COLORS).map(([k, color]) => [k, color, k]);
      features.forEach((f) => {
        const u = f.properties.usage || "기타";
        counts.set(u, (counts.get(u) || 0) + 1);
      });
    }

    el.legendBody.innerHTML = "";
    items.forEach(([label, color, key]) => {
      const row = document.createElement("div");
      row.className = "legend-item";
      row.innerHTML = `
        <div class="legend-left">
          <span class="legend-swatch" style="background:${color};"></span>
          <span>${label}</span>
        </div>
        <span class="legend-count">${(counts.get(key) || 0).toLocaleString()}동</span>
      `;
      el.legendBody.appendChild(row);
    });
  }

  function updateSummaryStats(features) {
    const total = features.length;
    if (total === 0) {
      el.statTotal.textContent = "0동";
      el.statAvg.textContent = "-";
      el.statHigh.textContent = "0동";
      el.statPcyMatched.textContent = "0동";
      return;
    }

    let sumScore = 0;
    let highCount = 0;
    let pcyHighCount = 0;
    features.forEach((f) => {
      const { dynamicScore, dynamicGrade, maxLift } = evaluateBuilding(f.properties);
      sumScore += dynamicScore;
      if (dynamicGrade === "위험(A)" || dynamicGrade === "경고(B)") {
        highCount += 1;
      }
      if (maxLift >= 2.0) {
        pcyHighCount += 1;
      }
    });

    const avg = (sumScore / total).toFixed(1);
    el.statTotal.textContent = `${total.toLocaleString()}동`;
    el.statAvg.textContent = `${avg}점`;
    el.statHigh.textContent = `${highCount.toLocaleString()}동`;
    el.statPcyMatched.textContent = `${pcyHighCount.toLocaleString()}동`;
  }

  function renderBuildings(zoomToMatch = false) {
    if (!state.rawBuildings) return;

    const filteredFeatures = state.rawBuildings.features.filter(matchesFilter);
    buildingGroup.clearLayers();
    state.layerById.clear();

    buildingGeoJsonLayer = L.geoJSON(
      { type: "FeatureCollection", features: filteredFeatures },
      {
        renderer: canvasRenderer,
        style: (feature) => getPolygonStyle(feature, false),
        onEachFeature: (feature, layer) => {
          const id = feature.properties.id;
          state.layerById.set(id, layer);

          layer.on({
            mouseover: (e) => {
              state.hoveredLayer = layer;
              layer.setStyle(getPolygonStyle(feature, true));
              showHoverCard(feature, e.originalEvent);
            },
            mousemove: (e) => {
              if (e.originalEvent) {
                positionHoverCard(e.originalEvent.clientX, e.originalEvent.clientY);
              }
            },
            mouseout: () => {
              if (state.hoveredLayer === layer) {
                state.hoveredLayer = null;
              }
              layer.setStyle(getPolygonStyle(feature, false));
              hideHoverCard();
            },
            click: () => {
              selectBuilding(feature);
            },
          });
        },
      }
    ).addTo(buildingGroup);

    updateSummaryStats(filteredFeatures);
    updateLegend(filteredFeatures);

    if (zoomToMatch && filteredFeatures.length > 0 && filteredFeatures.length <= 200) {
      map.fitBounds(buildingGeoJsonLayer.getBounds(), { padding: [40, 40], maxZoom: 18 });
    }

    if (state.selectedId !== null && state.layerById.has(state.selectedId)) {
      selectBuilding(state.layerById.get(state.selectedId).feature);
    }
  }

  function restyleBuildingsOnly() {
    if (!buildingGeoJsonLayer) return;
    const filteredFeatures = [];
    buildingGeoJsonLayer.eachLayer((layer) => {
      const isHovered = state.hoveredLayer === layer;
      layer.setStyle(getPolygonStyle(layer.feature, isHovered));
      filteredFeatures.push(layer.feature);
    });
    updateSummaryStats(filteredFeatures);
    updateLegend(filteredFeatures);

    if (state.selectedId !== null && state.layerById.has(state.selectedId)) {
      selectBuilding(state.layerById.get(state.selectedId).feature);
    }
  }

  function renderInfrastructure() {
    if (!state.infraData) return;
    boundaryGroup.clearLayers();
    stationGroup.clearLayers();
    hydrantGroup.clearLayers();

    state.infraData.features.forEach((feat) => {
      const kind = feat.properties.kind;
      if (kind === "boundary") {
        L.geoJSON(feat, {
          interactive: false,
          style: {
            color: "#38bdf8",
            weight: 2,
            dashArray: "7, 5",
            opacity: 0.7,
            fill: false,
          },
        }).addTo(boundaryGroup);
      } else if (kind === "fire_station") {
        const [lon, lat] = feat.geometry.coordinates;
        const marker = L.marker([lat, lon], {
          icon: L.divIcon({
            className: "station-marker",
            html: `🚒 ${feat.properties.name}`,
            iconSize: null,
          }),
        });
        marker.bindPopup(
          `<strong>${feat.properties.name}</strong><br/>구분: ${feat.properties.station_type}<br/>주소: ${feat.properties.address || "-"}`
        );
        marker.addTo(stationGroup);
      } else if (kind === "fire_hydrant") {
        const [lon, lat] = feat.geometry.coordinates;
        const circle = L.circleMarker([lat, lon], {
          radius: 5,
          color: "#ffffff",
          weight: 1.5,
          fillColor: "#06b6d4",
          fillOpacity: 0.95,
        });
        circle.bindPopup(
          `<strong>💧 ${feat.properties.name}</strong><br/>출처: ${feat.properties.source}`
        );
        circle.addTo(hydrantGroup);
      }
    });
    syncZoomClutter();
  }

  function renderRiLabels() {
    riLabelGroup.clearLayers();
    RI_CENTERS.forEach(([riName, lat, lon]) => {
      L.marker([lat, lon], {
        interactive: false,
        icon: L.divIcon({
          className: "ri-label",
          html: riName,
          iconSize: null,
        }),
      }).addTo(riLabelGroup);
    });
  }

  function syncZoomClutter() {
    const isZoomedIn = map.getZoom() >= 16;
    if (el.layerHydrants.checked && isZoomedIn) {
      if (!map.hasLayer(hydrantGroup)) hydrantGroup.addTo(map);
    } else {
      if (map.hasLayer(hydrantGroup)) map.removeLayer(hydrantGroup);
    }
    if (state.lastZoomDetail !== isZoomedIn) {
      state.lastZoomDetail = isZoomedIn;
      restyleBuildingsOnly();
    }
  }

  function renderPcyReportModal() {
    if (!state.pcyData) {
      el.pcyModalBody.innerHTML = "<p class='helper-note'>PCY 규칙 데이터를 불러오지 못했습니다.</p>";
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
        <strong>💡 PCY 단독 (k=2) + 공간 빅데이터 결합 원리:</strong><br/>
        <code>PCY</code> 알고리즘은 Pass 1에서 모든 2-항목 쌍을 <strong>${(pc.n_buckets || 32771).toLocaleString()}개 해시 버킷</strong>으로 압축해 비트맵을 만들고,
        Pass 2에서 빈발 버킷을 통과한 <code>k=2</code> 위험 쌍(<strong>L2</strong>)만 고속 추출합니다.
        여기에 장바구니 모델이 버린(<em>The Discard</em>) <strong>정확한 거리(m)·밀집도·연식 연속 수치(0~70점)</strong>를 지도 공간 연산으로 복원해 결합했습니다.
      </div>

      <h3>1. PCY 단독 (k=2) 해시·비트맵 실행 요약 (건축물 화재 ${meta.n_building_fires.toLocaleString()}건, min_support 1.0%)</h3>
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

  function populateSubdistrictOptions() {
    const ris = new Set();
    state.rawBuildings.features.forEach((f) => {
      if (f.properties.subdistrict) ris.add(f.properties.subdistrict);
    });
    const sorted = Array.from(ris).sort((a, b) => a.localeCompare(b, "ko"));
    const allLabel = state.isDefaultDataset ? "전체 (조치원읍)" : "전체 (현재 조회구역)";
    el.filterRi.innerHTML = `<option value="ALL">${allLabel}</option>`;
    sorted.forEach((ri) => {
      const opt = document.createElement("option");
      opt.value = ri;
      opt.textContent = ri;
      el.filterRi.appendChild(opt);
    });
  }

  let viewportAbortCtrl = null;
  let moveFetchTimer = null;

  function renderLiveStations(stations) {
    stationGroup.clearLayers();
    (stations || []).forEach((st) => {
      const marker = L.marker([st.lat, st.lon], {
        icon: L.divIcon({
          className: "station-marker",
          html: `🚒 ${st.name}`,
          iconSize: null,
        }),
      });
      marker.bindPopup(
        `<strong>${st.name}</strong><br/>구분: ${st.type || "소방거점"}<br/>주소: ${st.address || "-"}<br/>출처: ${st.source || "브이월드"}`
      );
      marker.addTo(stationGroup);
    });
  }

  async function fetchViewportBuildings(forceZoom = false) {
    if (map.getZoom() < 16) {
      if (forceZoom) {
        map.setZoom(16);
      } else {
        el.vworldLiveStatus.textContent = "건물 폴리곤 조회를 위해 지도를 조금 더 확대(줌 16 이상)해 주세요.";
        return;
      }
    }

    const b = map.getBounds();
    const bbox = [
      b.getWest().toFixed(5),
      b.getSouth().toFixed(5),
      b.getEast().toFixed(5),
      b.getNorth().toFixed(5),
    ].join(",");

    if (viewportAbortCtrl) {
      viewportAbortCtrl.abort();
    }
    viewportAbortCtrl = new AbortController();
    el.vworldLiveStatus.textContent = "📡 브이월드 공식 건물·소방거점 데이터 불러오는 중...";

    try {
      const resp = await fetch(`/api/vworld/buildings?bbox=${encodeURIComponent(bbox)}`, {
        signal: viewportAbortCtrl.signal,
      });
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.error || "브이월드 건물 조회 실패");
      }

      state.isDefaultDataset = false;
      state.ri = "ALL";
      state.selectedId = null;
      routeGroup.clearLayers();
      el.detailDrawer.classList.add("hidden");

      state.rawBuildings = data.buildings;
      state.pcyCache.clear();

      // 타 지역 조회 시 조치원 전용 경계·리 라벨 숨김
      if (map.hasLayer(riLabelGroup)) map.removeLayer(riLabelGroup);
      if (map.hasLayer(boundaryGroup)) map.removeLayer(boundaryGroup);
      renderLiveStations(data.stations);

      populateSubdistrictOptions();
      renderBuildings(false);

      const total = data.meta?.total_buildings || 0;
      const ledger = data.meta?.ledger_matched || 0;
      const sec = data.meta?.elapsed_sec ?? "-";
      el.vworldLiveStatus.textContent = `✅ 브이월드 ${total.toLocaleString()}동 로드 (대장실측 ${ledger.toLocaleString()}동 · ${sec}초)`;
      el.modalDatasetInfo.textContent = `브이월드 전국 실시간 조회 · ${total.toLocaleString()}동 (대장실측 ${ledger.toLocaleString()}동)`;
    } catch (err) {
      if (err.name === "AbortError") return;
      el.vworldLiveStatus.textContent = `⚠️ ${err.message}`;
    }
  }

  function restoreDefaultJochiwon(fly = true) {
    if (!state.defaultBuildings) return;
    state.vworldLive = false;
    state.isDefaultDataset = true;
    state.ri = "ALL";
    state.selectedId = null;
    el.toggleVworldLive.checked = false;
    routeGroup.clearLayers();
    el.detailDrawer.classList.add("hidden");

    state.rawBuildings = structuredClone(state.defaultBuildings);
    state.pcyCache.clear();
    populateSubdistrictOptions();
    renderInfrastructure();
    if (el.layerRiLabels.checked && !map.hasLayer(riLabelGroup)) riLabelGroup.addTo(map);
    if (el.layerBoundary.checked && !map.hasLayer(boundaryGroup)) boundaryGroup.addTo(map);
    renderBuildings(false);

    const cnt = state.defaultBuildings.features.length;
    el.vworldLiveStatus.textContent = `기본: 조치원읍 브이월드 공식 데이터 (${cnt.toLocaleString()}동)`;
    if (fly) {
      map.flyTo([36.6015, 127.2945], 15, { duration: 0.6 });
    }
  }

  async function runVWorldPlaceSearch() {
    const q = el.vworldSearchInput.value.trim();
    if (!q) return;
    el.vworldSearchResults.innerHTML = '<div class="vw-item muted">검색 중...</div>';
    el.vworldSearchResults.classList.remove("hidden");
    try {
      const resp = await fetch(`/api/vworld/search?q=${encodeURIComponent(q)}`);
      const data = await resp.json();
      const items = data.items || [];
      if (items.length === 0) {
        el.vworldSearchResults.innerHTML = '<div class="vw-item muted">검색 결과가 없습니다.</div>';
        return;
      }
      el.vworldSearchResults.innerHTML = "";
      items.forEach((it) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "vw-item";
        btn.innerHTML = `<strong>${it.title}</strong><span>${it.address || it.category || ""}</span>`;
        btn.addEventListener("click", () => {
          el.vworldSearchResults.classList.add("hidden");
          state.vworldLive = true;
          el.toggleVworldLive.checked = true;
          map.flyTo([it.lat, it.lon], 17, { duration: 0.7 });
        });
        el.vworldSearchResults.appendChild(btn);
      });
    } catch (err) {
      el.vworldSearchResults.innerHTML = `<div class="vw-item muted">검색 오류: ${err.message}</div>`;
    }
  }

  function parseCsv(text) {
    const lines = text
      .replace(/^\uFEFF/, "")
      .split(/\r?\n/)
      .filter((l) => l.trim().length > 0);
    if (lines.length < 2) return [];
    const headers = lines[0].split(",").map((h) => h.trim().replace(/^"|"$/g, ""));
    return lines.slice(1).map((line) => {
      const cols = line.split(",").map((c) => c.trim().replace(/^"|"$/g, ""));
      const obj = {};
      headers.forEach((h, i) => {
        obj[h] = cols[i] ?? "";
      });
      return obj;
    });
  }

  function normalizeUploadedGeoJson(geojson) {
    if (!geojson || !Array.isArray(geojson.features)) {
      throw new Error("유효한 GeoJSON FeatureCollection 형식이 아닙니다.");
    }
    const normalized = geojson.features
      .filter((f) => f.geometry && (f.geometry.type === "Polygon" || f.geometry.type === "MultiPolygon"))
      .map((f, idx) => {
        const p = f.properties || {};
        const builtYear = Number(p.built_year || 2005);
        const age = Number(p.age ?? 2026 - builtYear);
        const riskScore = Number(p.risk_score ?? 45);
        const props = {
          id: p.id ?? idx + 1,
          name: p.name || p.bld_nm || `업로드 건물 #${idx + 1}`,
          subdistrict: p.subdistrict || p.emd_nm || "조치원읍",
          address: p.address || p.rn_adr || "-",
          usage: p.usage || p.main_purps || "제1·2종 근린생활시설",
          structure: p.structure || p.strct_cd_nm || "철근콘크리트조",
          roof_type: p.roof_type || "슬라브가",
          built_year: builtYear,
          age,
          floors: Number(p.floors || p.grnd_flr_cnt || 2),
          footprint_area_m2: Number(p.footprint_area_m2 || p.arch_area || 120),
          total_area_m2: Number(p.total_area_m2 || p.tot_area || 240),
          has_sprinkler: Boolean(p.has_sprinkler),
          neighbor_count_30m: Number(p.neighbor_count_30m || 2),
          nearest_fire_station: p.nearest_fire_station || "세종북부소방서",
          dist_fire_station_m: Number(p.dist_fire_station_m || 800),
          dist_hydrant_m: Number(p.dist_hydrant_m || 90),
          risk_score: riskScore,
          risk_grade: p.risk_grade || gradeFromScore(riskScore),
          score_age: Number(p.score_age ?? Math.round(riskScore * 0.25)),
          score_structure: Number(p.score_structure ?? Math.round(riskScore * 0.25)),
          score_usage: Number(p.score_usage ?? Math.round(riskScore * 0.2)),
          score_spread: Number(p.score_spread ?? Math.round(riskScore * 0.15)),
          score_access: Number(p.score_access ?? Math.round(riskScore * 0.15)),
          risk_factors: Array.isArray(p.risk_factors) ? p.risk_factors : ["사용자 업로드 속성"],
          ...p,
        };
        if (!Array.isArray(props.static_basket) || props.static_basket.length === 0) {
          props.static_basket = synthesizeFallbackBasket(props);
        }
        return { ...f, properties: props };
      });
    return { type: "FeatureCollection", metadata: { source_mode: "사용자 GeoJSON 업로드" }, features: normalized };
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

  function applyEnvironmentChange() {
    updateEnvUiSync();
    if (state.grade !== "ALL") {
      renderBuildings(false);
    } else {
      restyleBuildingsOnly();
    }
  }

  function bindEvents() {
    // 주제도 탭 전환
    document.querySelectorAll(".mode-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".mode-tab").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.mode = btn.dataset.mode;
        restyleBuildingsOnly();
      });
    });

    // 시간대 / 계절 / 습도 / 풍속 장바구니 환경 컨트롤
    document.querySelectorAll("#time-seg .seg-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".preset-btn").forEach((b) => b.classList.remove("active"));
        state.timeItem = btn.dataset.time;
        applyEnvironmentChange();
      });
    });

    document.querySelectorAll("#season-seg .seg-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".preset-btn").forEach((b) => b.classList.remove("active"));
        state.seasonItem = btn.dataset.season;
        applyEnvironmentChange();
      });
    });

    el.sliderHumidity.addEventListener("input", () => {
      document.querySelectorAll(".preset-btn").forEach((b) => b.classList.remove("active"));
      state.humidity = Number(el.sliderHumidity.value);
      applyEnvironmentChange();
    });

    el.sliderWind.addEventListener("input", () => {
      document.querySelectorAll(".preset-btn").forEach((b) => b.classList.remove("active"));
      state.wind = Number(el.sliderWind.value);
      applyEnvironmentChange();
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
        applyEnvironmentChange();
      });
    });

    // 검색 및 필터
    let searchTimer = null;
    el.searchInput.addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        state.search = el.searchInput.value.trim();
        renderBuildings(false);
      }, 150);
    });

    el.searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        state.search = el.searchInput.value.trim();
        renderBuildings(true);
      }
    });

    el.filterRi.addEventListener("change", () => {
      state.ri = el.filterRi.value;
      renderBuildings(true);
    });

    el.filterGrade.addEventListener("change", () => {
      state.grade = el.filterGrade.value;
      renderBuildings(false);
    });

    el.filterUsage.addEventListener("change", () => {
      state.usage = el.filterUsage.value;
      renderBuildings(false);
    });

    el.toggleHighOnly.addEventListener("change", () => {
      state.highOnly = el.toggleHighOnly.checked;
      restyleBuildingsOnly();
    });

    el.btnResetFilters.addEventListener("click", () => {
      state.search = "";
      state.ri = "ALL";
      state.grade = "ALL";
      state.usage = "ALL";
      state.highOnly = false;
      el.searchInput.value = "";
      el.filterRi.value = "ALL";
      el.filterGrade.value = "ALL";
      el.filterUsage.value = "ALL";
      el.toggleHighOnly.checked = false;
      renderBuildings(false);
    });

    // 배경지도 & 가독성 레이어 토글
    el.basemapSelect.addEventListener("change", () => {
      const spec = BASEMAPS[el.basemapSelect.value] || BASEMAPS.voyager;
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

    // 브이월드 전국 실시간 탐색 이벤트
    el.btnVworldSearch.addEventListener("click", runVWorldPlaceSearch);
    el.vworldSearchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        runVWorldPlaceSearch();
      }
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".vworld-search-wrap")) {
        el.vworldSearchResults.classList.add("hidden");
      }
    });

    el.toggleVworldLive.addEventListener("change", () => {
      state.vworldLive = el.toggleVworldLive.checked;
      if (state.vworldLive) {
        fetchViewportBuildings(true);
      } else {
        el.vworldLiveStatus.textContent = "자동 로딩 일시 중지됨 ('현재 화면 불러오기' 또는 '조치원 기본' 선택)";
      }
    });

    el.btnFetchViewport.addEventListener("click", () => {
      fetchViewportBuildings(true);
    });

    el.btnRestoreJochiwon.addEventListener("click", () => {
      restoreDefaultJochiwon(true);
    });

    map.on("moveend", () => {
      if (!state.vworldLive) return;
      clearTimeout(moveFetchTimer);
      moveFetchTimer = setTimeout(() => {
        fetchViewportBuildings(false);
      }, 280);
    });

    el.sliderOpacity.addEventListener("input", () => {
      const pct = Number(el.sliderOpacity.value);
      state.fillOpacity = pct / 100;
      el.valOpacity.textContent = `${pct}%`;
      restyleBuildingsOnly();
    });

    el.toggleSmartOpacity.addEventListener("change", () => {
      state.smartOpacity = el.toggleSmartOpacity.checked;
      restyleBuildingsOnly();
    });

    el.layerRiLabels.addEventListener("change", () => {
      if (el.layerRiLabels.checked) riLabelGroup.addTo(map);
      else map.removeLayer(riLabelGroup);
    });

    el.layerStations.addEventListener("change", () => {
      if (el.layerStations.checked) stationGroup.addTo(map);
      else map.removeLayer(stationGroup);
    });

    el.layerHydrants.addEventListener("change", syncZoomClutter);

    el.layerBoundary.addEventListener("change", () => {
      if (el.layerBoundary.checked) boundaryGroup.addTo(map);
      else map.removeLayer(boundaryGroup);
    });

    map.on("zoomend", syncZoomClutter);

    // 빠른 이동
    document.querySelectorAll(".jump-chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (btn.dataset.restore === "1") {
          restoreDefaultJochiwon(true);
          return;
        }
        if (btn.dataset.live === "1") {
          state.vworldLive = true;
          el.toggleVworldLive.checked = true;
        } else if (!state.isDefaultDataset) {
          restoreDefaultJochiwon(false);
        }
        map.flyTo(
          [Number(btn.dataset.lat), Number(btn.dataset.lon)],
          Number(btn.dataset.zoom),
          { duration: 0.7 }
        );
      });
    });

    // 우측 드로어 닫기
    el.btnCloseDrawer.addEventListener("click", () => {
      const prevId = state.selectedId;
      state.selectedId = null;
      if (prevId !== null && state.layerById.has(prevId)) {
        const prevLayer = state.layerById.get(prevId);
        prevLayer.setStyle(getPolygonStyle(prevLayer.feature, false));
      }
      routeGroup.clearLayers();
      el.detailDrawer.classList.add("hidden");
      setTimeout(() => map.invalidateSize(), 50);
    });

    // 모달: PCY 리포트 & 데이터 업로드
    el.btnOpenPcyModal.addEventListener("click", () => {
      renderPcyReportModal();
      el.pcyModal.classList.remove("hidden");
    });
    el.btnClosePcyModal.addEventListener("click", () => el.pcyModal.classList.add("hidden"));
    el.pcyModal.addEventListener("click", (e) => {
      if (e.target === el.pcyModal) el.pcyModal.classList.add("hidden");
    });

    el.btnOpenModal.addEventListener("click", () => el.dataModal.classList.remove("hidden"));
    el.btnCloseModal.addEventListener("click", () => el.dataModal.classList.add("hidden"));
    el.dataModal.addEventListener("click", (e) => {
      if (e.target === el.dataModal) el.dataModal.classList.add("hidden");
    });

    // 파일 업로드 (GeoJSON / CSV)
    el.fileUploadInput.addEventListener("change", async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      try {
        const text = await file.text();
        if (file.name.toLowerCase().endsWith(".csv")) {
          const rows = parseCsv(text);
          const byKey = new Map();
          rows.forEach((r) => {
            if (r.id) byKey.set(String(r.id), r);
            if (r.name) byKey.set(String(r.name), r);
          });
          let merged = 0;
          state.rawBuildings.features.forEach((f) => {
            const p = f.properties;
            const match = byKey.get(String(p.id)) || byKey.get(String(p.name));
            if (match) {
              merged += 1;
              if (match.built_year) {
                p.built_year = Number(match.built_year);
                p.age = 2026 - p.built_year;
              }
              if (match.structure) p.structure = match.structure;
              if (match.usage) p.usage = match.usage;
              if (match.floors) p.floors = Number(match.floors);
              if (match.risk_score) {
                p.risk_score = Number(match.risk_score);
                p.risk_grade = gradeFromScore(p.risk_score);
              }
              p.static_basket = synthesizeFallbackBasket(p);
            }
          });
          state.pcyCache.clear();
          renderBuildings(false);
          el.uploadStatus.textContent = `CSV 병합 완료: ${merged}건의 건물 속성이 업데이트되었습니다.`;
        } else {
          const parsed = JSON.parse(text);
          state.rawBuildings = normalizeUploadedGeoJson(parsed);
          state.pcyCache.clear();
          populateSubdistrictOptions();
          renderBuildings(true);
          el.uploadStatus.textContent = `GeoJSON 로드 완료: 총 ${state.rawBuildings.features.length.toLocaleString()}개 폴리곤이 지도에 반영되었습니다.`;
        }
      } catch (err) {
        el.uploadStatus.textContent = `오류: ${err.message}`;
      }
    });

    el.btnResetDataset.addEventListener("click", () => {
      restoreDefaultJochiwon(true);
      el.uploadStatus.textContent = "기본 조치원읍 브이월드 데이터셋으로 복원되었습니다.";
    });
  }

  async function init() {
    bindEvents();
    updateEnvUiSync();
    try {
      const [bResp, iResp, pResp] = await Promise.all([
        fetch("data/jochiwon_buildings.geojson"),
        fetch("data/jochiwon_infra.geojson"),
        fetch("data/jochiwon_pcy_rules.json"),
      ]);
      if (!bResp.ok) throw new Error("건물 GeoJSON을 불러올 수 없습니다.");
      const buildings = await bResp.json();
      const infra = iResp.ok ? await iResp.json() : { type: "FeatureCollection", features: [] };
      const pcyJson = pResp.ok ? await pResp.json() : null;

      state.defaultBuildings = buildings;
      state.rawBuildings = structuredClone(buildings);
      state.infraData = infra;
      state.pcyData = pcyJson;
      state.pcyCache.clear();

      const meta = buildings.metadata || {};
      const pcyMeta = pcyJson?.metadata || {};
      el.modalDatasetInfo.textContent = `${meta.source_mode || "브이월드"} · ${buildings.features.length.toLocaleString()}동 + 소방청 ${(pcyMeta.n_total_fires || 0).toLocaleString()}건 기반 PCY (k=${pcyMeta.max_k || 2}) 규칙 ${pcyMeta.rule_count || 0}개 연동`;
      el.vworldLiveStatus.textContent = `기본: 조치원읍 ${meta.source_mode || "브이월드"} (${buildings.features.length.toLocaleString()}동)`;

      populateSubdistrictOptions();
      renderRiLabels();
      renderInfrastructure();
      renderBuildings(false);
    } catch (err) {
      el.modalDatasetInfo.textContent = `데이터 로딩 오류: ${err.message}`;
      alert(`데이터 로딩 중 오류가 발생했습니다.\npython server.py로 웹 서버를 실행했는지 확인해주세요.\n(${err.message})`);
    }
  }

  init();
})();
