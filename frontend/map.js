// Harita: Leaflet + markercluster, kaynak turune gore renk, lejant toggle,
// poligon katmani, kebab menulu tesis karti (koordinat/KMZ indirme).
const map = L.map("map").setView([39.0, 35.0], 6);

// Renkli daire ikon (markerCluster L.marker'i destekler; circleMarker'da popup sorunlu)
const _iconCache = {};
function coloredIcon(color) {
  if (!_iconCache[color]) {
    _iconCache[color] = L.divIcon({
      className: "fac-marker",
      html: `<span style="display:block;width:14px;height:14px;border-radius:50%;`
          + `background:${color};border:2px solid #fff;box-shadow:0 0 3px rgba(0,0,0,.5)"></span>`,
      iconSize: [14, 14], iconAnchor: [7, 7], popupAnchor: [0, -8],
    });
  }
  return _iconCache[color];
}
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19, attribution: "© OpenStreetMap"
}).addTo(map);

const cluster = L.markerClusterGroup({ chunkedLoading: true, maxClusterRadius: 45 });
const polyLayer = L.layerGroup();
map.addLayer(cluster);

let allFeatures = [];
let disabledKaynak = new Set();

function popupHtml(p) {
  const row = (k, v) => v === null || v === undefined || v === "" ? "" :
    `<tr><td class="k">${k}</td><td>${v}</td></tr>`;
  return `<div class="card">
    <div class="hd">
      <h3>${p.tesis_adi || "Tesis"}</h3>
      <div class="kebab">
        <button class="dots" onclick="toggleMenu(this)">⋮</button>
        <div class="menu">
          <a onclick="dl('/api/facilities/${p.id}/coordinates')">📄 Koordinat Bilgilerini İndir (CSV)</a>
          <a onclick="dl('/api/facilities/${p.id}/kmz')">🌍 KMZ Olarak İndir</a>
        </div>
      </div>
    </div>
    <table>
      ${row("Unvan", p.unvan)}
      ${row("Lisans No", p.lisans_no)}
      ${row("İl / İlçe", (p.il || "") + " / " + (p.ilce || ""))}
      ${row("Tesis Türü", p.tesis_turu)}
      ${row("Kaynak", `<span class="dot" style="background:${colorFor(p.kaynak_turu)}"></span>${p.kaynak_turu || ""}`)}
      ${row("Kurulu Güç", `${p.kurulu_guc_mwm ?? "-"} MWm / ${p.kurulu_guc_mwe ?? "-"} MWe`)}
      ${row("Başlangıç / Bitiş", (p.baslangic_tarihi || "") + " – " + (p.bitis_tarihi || ""))}
      ${row("Merkez", `${p.centroid_lat?.toFixed?.(5)}, ${p.centroid_lng?.toFixed?.(5)}`)}
    </table>
  </div>`;
}
function toggleMenu(btn) {
  const m = btn.nextElementSibling;
  document.querySelectorAll(".kebab .menu.open").forEach(x => { if (x !== m) x.classList.remove("open"); });
  m.classList.toggle("open");
}
function dl(url) { window.location = API + url; }

function render() {
  cluster.clearLayers(); polyLayer.clearLayers();
  let shown = 0;
  for (const feat of allFeatures) {
    const p = feat.properties;
    if (feat.geometry.type === "Point") {
      if (disabledKaynak.has(trUpper(p.kaynak_turu))) continue;
      const [lng, lat] = feat.geometry.coordinates;
      if (p._is_turbine) {
        // TURBIN noktasi: poligon DEGIL, cluster DEGIL; ayri belirgin isaret
        // (beyaz dolgu + mavi kenar -> tesis marker'i ve cluster'dan ayrilir).
        const t = L.circleMarker([lat, lng], {
          radius: 5, color: "#0057b7", weight: 2,
          fillColor: "#ffffff", fillOpacity: 1,
        });
        t.bindTooltip(`T${p.turbin_no || ""}`, { direction: "top", offset: [0, -4] });
        t.bindPopup(`<b>${p.tesis_adi}</b><br>Türbin ${p.turbin_no || ""}`);
        polyLayer.addLayer(t);
        continue;
      }
      const m = L.marker([lat, lng], { icon: coloredIcon(colorFor(p.kaynak_turu)) });
      m.bindPopup(popupHtml(p), { maxWidth: 340 });
      m.on("click", () => m.openPopup());
      cluster.addLayer(m);
      shown++;
    } else if (feat.geometry.type === "Polygon") {
      if (disabledKaynak.has(trUpper(p.kaynak_turu))) continue;
      const ring = feat.geometry.coordinates[0].map(([lng, lat]) => [lat, lng]);
      polyLayer.addLayer(L.polygon(ring, {
        color: colorFor(p.kaynak_turu), weight: 2, fillOpacity: 0.15,
      }));
    }
  }
  document.getElementById("countPill").textContent = shown + " tesis";
}

function buildLegend() {
  const kinds = [...new Set(allFeatures
    .filter(f => f.geometry.type === "Point")
    .map(f => f.properties.kaynak_turu).filter(Boolean))].sort();
  const el = document.getElementById("legend");
  el.innerHTML = "<h4>Kaynak Türü</h4>" + kinds.map(k => {
    const off = disabledKaynak.has(trUpper(k)) ? "off" : "";
    return `<div class="row ${off}" data-k="${k}">
      <span class="sw" style="background:${colorFor(k)}"></span>${k}</div>`;
  }).join("") + `<div class="row" data-all="1" style="margin-top:6px;border-top:1px solid var(--line);padding-top:6px">↺ Tümünü göster</div>`;
  el.querySelectorAll(".row").forEach(r => r.onclick = () => {
    if (r.dataset.all) { disabledKaynak.clear(); }
    else {
      const key = trUpper(r.dataset.k);
      if (disabledKaynak.has(key)) disabledKaynak.delete(key); else disabledKaynak.add(key);
    }
    buildLegend(); render();
  });
}

function query() {
  const p = new URLSearchParams();
  const s = document.getElementById("m_search").value; if (s) p.set("search", s);
  const il = document.getElementById("m_il").value; if (il) p.set("il", il);
  const tt = document.getElementById("m_tesis").value; if (tt) p.set("tesis_turu", tt);
  if (document.getElementById("m_poly").checked) p.set("include_polygons", "true");
  p.set("lisans_tipi", getLT());
  return p.toString();
}

async function loadData() {
  document.getElementById("countPill").textContent = "yükleniyor…";
  const gj = await getJSON(API + "/api/facilities/geojson?" + query());
  allFeatures = gj.features || [];
  buildLegend(); render();
  if (document.getElementById("m_poly").checked) map.addLayer(polyLayer);
  else map.removeLayer(polyLayer);
}

async function loadFilters() {
  const f = await getJSON(API + "/api/facilities/filters");
  const fill = (id, arr, lbl) => {
    document.getElementById(id).innerHTML =
      `<option value="">${lbl}</option>` + arr.map(v => `<option>${v}</option>`).join("");
  };
  fill("m_il", f.il, "İl: Hepsi");
  fill("m_tesis", f.tesis_turu, "Tesis Türü: Hepsi");
}

function debounce(fn, ms) { let t; return () => { clearTimeout(t); t = setTimeout(fn, ms); }; }

function init() {
  initSyncBox();
  initLTToggle(() => loadData());
  loadFilters(); loadData();
  document.getElementById("m_il").onchange = loadData;
  document.getElementById("m_tesis").onchange = loadData;
  document.getElementById("m_poly").onchange = loadData;
  document.getElementById("m_search").oninput = debounce(loadData, 400);
  document.addEventListener("click", e => {
    if (!e.target.closest(".kebab")) document.querySelectorAll(".kebab .menu.open").forEach(m => m.classList.remove("open"));
  });
}
init();
