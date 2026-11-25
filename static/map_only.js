(() => {
  "use strict";

  const JOCHIWON_CENTER = [36.6015, 127.2945];
  const MAX_CACHE_SIZE = 40;

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
    voyager: {
      url: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
      attribution: "&copy; OpenStreetMap &copy; CARTO",
    },
  };

  const USAGE_COLORS = {
    "단독주택": "#60a5fa",
    "공동주택": "#22c55e",
    "제1·2종 근린생활시설": "#f59e0b",
    "전통시장/상점가": "#ef4444",
    "창고/공장시설": "#f97316",
    "교육연구시설": "#a855f7",
    "업무/공공시설": "#14b8a6",
  };

  const STRUCTURE_COLORS = {
    "철근콘크리트조": "#22c55e",
    "일반철골조": "#38bdf8",
    "벽돌조": "#eab308",
    "경량철골조(샌드위치패널)": "#f97316",
    "일반목구조": "#ef4444",
  };

  const state = {
    colorMode: "clean",
    showStations: true,
    selectedId: null,
    layerById: new Map(),
    viewportCache: new Map(),
  };

  const el = {
    searchInput: document.getElementById("search-input"),
    btnSearch: document.getElementById("btn-search"),
    searchResults: document.getElementById("search-results"),
    statusText: document.getElementById("status-text"),
    btnHome: document.getElementById("btn-home"),
    btnToggleStations: document.getElementById("btn-toggle-stations"),
    miniLegend: document.getElementById("mini-legend"),
    zoomHint: document.getElementById("zoom-hint"),
    infoCard: document.getElementById("info-card"),
    btnCloseInfo: document.getElementById("btn-close-info"),
    icSub: document.getElementById("ic-sub"),
    icName: document.getElementById("ic-name"),
    icAddr: document.getElementById("ic-addr"),
    icList: document.getElementById("ic-list"),
  };

  const canvasRenderer = L.canvas({ padding: 0.5 });
  const map = L.map("map", {
    center: JOCHIWON_CENTER,
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

  function ageColor(age) {
    if (age >= 40) return "#ef4444";
    if (age >= 30) return "#f97316";
    if (age >= 20) return "#eab308";
    if (age >= 10) return "#38bdf8";
    return "#22c55e";
  }

  function styleBuilding(feature, highlight = false) {
    const p = feature.properties;
    let fillColor = "#3b82f6";
    if (state.colorMode === "usage") fillColor = USAGE_COLORS[p.usage] || "#94a3b8";
    else if (state.colorMode === "structure") fillColor = STRUCTURE_COLORS[p.structure] || "#94a3b8";
    else if (state.colorMode === "age") fillColor = ageColor(Number(p.age || 0));

    const selected = state.selectedId === p.id;
    if (highlight || selected) {
      return {
        color: selected ? "#1d4ed8" : "#0f172a",
        weight: selected ? 2.6 : 1.8,
        opacity: 1,
        fillColor,
        fillOpacity: 0.78,
      };
    }

    const zoomedIn = map.getZoom() >= 16;
    return {
      color: "#1e3a8a",
      weight: zoomedIn ? 0.9 : 0.4,
      opacity: zoomedIn ? 0.65 : 0.4,
      fillColor,
      fillOpacity: state.colorMode === "clean" ? 0.36 : 0.62,
    };
  }

  function formatDist(m) {
    const v = Number(m || 0);
    return v >= 1000 ? `${(v / 1000).toFixed(2)}km` : `${Math.round(v)}m`;
  }

  function updateLegend() {
    let entries = [];
    if (state.colorMode === "usage") {
      entries = Object.entries(USAGE_COLORS);
    } else if (state.colorMode === "structure") {
      entries = Object.entries(STRUCTURE_COLORS);
    } else if (state.colorMode === "age") {
      entries = [
        ["40년 이상", "#ef4444"],
        ["30-39년", "#f97316"],
        ["20-29년", "#eab308"],
        ["10-19년", "#38bdf8"],
        ["10년 미만", "#22c55e"],
      ];
    }

    if (entries.length === 0) {
      el.miniLegend.classList.add("hidden");
      return;
    }

    el.miniLegend.innerHTML = entries
      .map(
        ([label, color]) =>
          `<div class="lg-row"><span class="lg-dot" style="background:${color}"></span><span>${label}</span></div>`
      )
      .join("");
    el.miniLegend.classList.remove("hidden");
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

    el.icSub.textContent = p.subdistrict || "-";
    el.icName.textContent = p.name || "건물";
    el.icAddr.textContent = p.address || "-";

    const rows = [
      ["주용도", p.usage || "-"],
      ["주구조", p.structure || "-"],
      ["준공연도", p.built_year ? `${p.built_year}년 (${p.age}년)` : "-"],
      ["지상층수", p.floors ? `${p.floors}층` : "-"],
      ["바닥면적", p.footprint_area_m2 ? `${Math.round(p.footprint_area_m2).toLocaleString()}㎡` : "-"],
      ["연면적", p.total_area_m2 ? `${Math.round(p.total_area_m2).toLocaleString()}㎡` : "-"],
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

        const tip = `<strong>${p.name || "건물"}</strong><br/>${p.usage || "-"} · ${p.floors || "-"}층 · ${p.built_year || "-"}년`;
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
      layer.setStyle(styleBuilding(layer.feature, false));
    });
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
    if (state.viewportCache.has(key)) {
      state.viewportCache.delete(key);
    }
    state.viewportCache.set(key, data);
    if (state.viewportCache.size > MAX_CACHE_SIZE) {
      const oldest = state.viewportCache.keys().next().value;
      state.viewportCache.delete(oldest);
    }
  }

  function applyViewportData(data, fromCache = false) {
    closeInfoCard();
    renderBuildings(data.buildings);
    renderStations(data.stations);

    const cnt = data.meta?.total_buildings || 0;
    const sec = data.meta?.elapsed_sec ?? "-";
    el.statusText.textContent = fromCache
      ? `현재 화면 ${cnt.toLocaleString()}동 (캐시)`
      : `현재 화면 ${cnt.toLocaleString()}동 (${sec}초)`;
  }

  async function fetchViewportBuildings() {
    const zoom = map.getZoom();
    if (zoom < 16) {
      if (abortCtrl) abortCtrl.abort();
      closeInfoCard();
      buildingGroup.clearLayers();
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
    el.statusText.textContent = "현재 화면 건물 불러오는 중...";

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

    el.btnHome.addEventListener("click", () => {
      map.flyTo(JOCHIWON_CENTER, 16, { duration: 0.7 });
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
        updateLegend();
      });
    });

    el.btnToggleStations.addEventListener("click", () => {
      state.showStations = !state.showStations;
      el.btnToggleStations.classList.toggle("active", state.showStations);
      if (state.showStations) stationGroup.addTo(map);
      else map.removeLayer(stationGroup);
    });

    el.btnCloseInfo.addEventListener("click", closeInfoCard);

    map.on("moveend", () => {
      clearTimeout(moveTimer);
      moveTimer = setTimeout(fetchViewportBuildings, 200);
    });
    map.on("zoomend", restyleAll);
  }

  function init() {
    bindEvents();
    fetchViewportBuildings();
  }

  init();
})();
