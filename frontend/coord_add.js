// Manuel koordinat / KMZ-KML: kullanicinin KENDI haritasi + tarayicisinda (localStorage).
// KMZ yuklenince Google Earth 'Yerler' paneli gibi klasor agaci gosterilir; her oge/klasor
// yaninda kutu ile goster-gizle, poligonlarda alan (ha), tiklayinca oraya git.
// Sunucu veritabanina HIC yazilmaz.
(function () {
  const $ = (id) => document.getElementById(id);
  const LS_KEY = "manuel_koordinatlar_v1";
  const RENK = "#ea580c";
  let userLayer = null;
  const itemLayers = {};             // itemId -> { path -> L.featureGroup }

  function getItems() { try { return JSON.parse(localStorage.getItem(LS_KEY) || "[]"); } catch (e) { return []; } }
  function setItems(a) { localStorage.setItem(LS_KEY, JSON.stringify(a)); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

  // ---------- sekilden Leaflet katmani ----------
  function shapeLayers(s) {
    const out = [];
    if (s.kind === "polygon") {
      (s.rings || []).forEach((r) => {
        if (r.length >= 3) out.push(L.polygon(r, {
          color: s.stroke || RENK, weight: 2,
          fillColor: s.fill || s.stroke || RENK,
          fillOpacity: (s.fillOpacity != null ? s.fillOpacity : 0.25),
        }));
      });
    } else if (s.kind === "line") {
      if ((s.coords || []).length >= 2) out.push(L.polyline(s.coords, { color: s.stroke || RENK, weight: 3 }));
    } else if (s.kind === "point") {
      const mk = L.circleMarker(s.coord, { radius: 5, color: "#fff", weight: 2, fillColor: s.color || RENK, fillOpacity: 1 });
      if (s.label) mk.bindTooltip(s.label, { direction: "top", offset: [0, -4] });
      out.push(mk);
    }
    return out;
  }
  function groupFromShapes(shapes, label) {
    const layers = [];
    (shapes || []).forEach((s) => shapeLayers(s).forEach((l) => layers.push(l)));
    const g = L.featureGroup(layers);
    if (label) g.bindPopup(`<b>${esc(label)}</b>`);
    return g;
  }

  // agac dolas: her dugume (dugum, path) uygula
  function walkTree(nodes, prefix, cb) {
    (nodes || []).forEach((n, i) => {
      const path = prefix === "" ? "" + i : prefix + "." + i;
      cb(n, path);
      if (n.type === "folder") walkTree(n.children, path, cb);
    });
  }
  function ancestorHidden(hidden, path) {
    if (hidden.has(path)) return true;
    let p = path;
    while (p.indexOf(".") >= 0) { p = p.slice(0, p.lastIndexOf(".")); if (hidden.has(p)) return true; }
    return false;
  }

  // ---------- item -> harita ----------
  function drawItem(it) {
    if (!userLayer && typeof map !== "undefined") userLayer = L.layerGroup().addTo(map);
    itemLayers[it.id] = {};
    const hidden = new Set(it.hidden || []);
    if (it.tree) {
      walkTree(it.tree, "", (n, path) => {
        if (n.type === "placemark") {
          const g = groupFromShapes(n.shapes, n.name);
          itemLayers[it.id][path] = g;
          if (!ancestorHidden(hidden, path)) g.addTo(userLayer);
        }
      });
    } else {
      // manuel/eski: tek grup + merkez isareti
      const shapes = it.shapes || _legacyShapes(it);
      const g = groupFromShapes(shapes, it.tesis_adi);
      if (it.centroid) g.addLayer(L.marker(it.centroid, { icon: manualIcon() }).bindPopup(popupHtml(it)));
      itemLayers[it.id]["_"] = g;
      if (!hidden.has("_")) g.addTo(userLayer);
    }
  }
  function _legacyShapes(it) {
    const s = [];
    (it.polygon_wgs84 || []).forEach((r) => s.push({ kind: "polygon", rings: [r], stroke: RENK, fill: RENK, fillOpacity: 0.15 }));
    (it.turbine_points || []).forEach((t) => s.push({ kind: "point", coord: t, color: "#7c2d12" }));
    return s;
  }
  function manualIcon() {
    return L.divIcon({
      className: "fac-marker",
      html: `<span style="display:block;width:15px;height:15px;border-radius:50%;background:${RENK};border:2px solid #fff;box-shadow:0 0 3px rgba(0,0,0,.6)"></span>`,
      iconSize: [15, 15], iconAnchor: [7, 7], popupAnchor: [0, -8],
    });
  }
  function popupHtml(it) {
    return `<div style="min-width:180px;font-size:13px"><b>${esc(it.tesis_adi || "Manuel")}</b>
      <p style="font-size:11px;color:#64748b;margin:5px 0 4px">Yalnızca siz görüyorsunuz.</p>
      <button onclick="silManuelKoord('${it.id}')" style="background:#dc2626;color:#fff;border:none;border-radius:6px;padding:5px 10px;cursor:pointer;font-size:12px">🗑 Kaldır</button></div>`;
  }

  function applyVisibility(it) {
    const layers = itemLayers[it.id]; if (!layers) return;
    const hidden = new Set(it.hidden || []);
    Object.keys(layers).forEach((path) => {
      const g = layers[path];
      const vis = path === "_" ? !hidden.has("_") : !ancestorHidden(hidden, path);
      if (vis && !userLayer.hasLayer(g)) userLayer.addLayer(g);
      else if (!vis && userLayer.hasLayer(g)) userLayer.removeLayer(g);
    });
  }

  function removeItem(id) {
    setItems(getItems().filter((x) => String(x.id) !== String(id)));
    const layers = itemLayers[id];
    if (layers) { Object.values(layers).forEach((g) => userLayer.removeLayer(g)); delete itemLayers[id]; }
    updatePlacesPanel();
    if (typeof toast === "function") toast("Kaldırıldı.");
  }
  window.silManuelKoord = removeItem;

  // ---------- 'Yerler' paneli ----------
  window.ppToggle = function (itemId, path, checked) {
    const items = getItems();
    const it = items.find((x) => String(x.id) === String(itemId)); if (!it) return;
    const hidden = new Set(it.hidden || []);
    if (checked) hidden.delete(path); else hidden.add(path);
    it.hidden = [...hidden]; setItems(items);
    applyVisibility(it);
  };
  window.ppZoom = function (itemId, path) {
    const layers = itemLayers[itemId]; if (!layers) return;
    let b = null;
    Object.keys(layers).forEach((p) => {
      if (p === path || p.indexOf(path + ".") === 0 || path === "_") {
        try { const gb = layers[p].getBounds(); if (gb && gb.isValid()) b = b ? b.extend(gb) : L.latLngBounds(gb); } catch (e) {}
      }
    });
    if (b && b.isValid()) map.fitBounds(b, { maxZoom: 15, padding: [30, 30] });
  };

  function renderNodes(itemId, nodes, prefix, hidden) {
    let h = "";
    (nodes || []).forEach((n, i) => {
      const path = prefix === "" ? "" + i : prefix + "." + i;
      const chk = hidden.has(path) ? "" : "checked";
      if (n.type === "folder") {
        h += `<div class="pp-node"><label><input type="checkbox" ${chk} onchange="ppToggle('${itemId}','${path}',this.checked)"><span class="pp-fold">📁 ${esc(n.name)}</span></label></div>`;
        h += `<div class="pp-children">${renderNodes(itemId, n.children, path, hidden)}</div>`;
      } else {
        const area = n.area_ha ? `<span class="pp-area">${n.area_ha} ha</span>` : "";
        h += `<div class="pp-node"><label><input type="checkbox" ${chk} onchange="ppToggle('${itemId}','${path}',this.checked)"><span>${esc(n.name)}</span></label> ${area}<a class="pp-zoom" title="Git" onclick="ppZoom('${itemId}','${path}')">◎</a></div>`;
      }
    });
    return h;
  }
  function updatePlacesPanel() {
    const el = $("placesPanel"); if (!el) return;
    const items = getItems();
    if (!items.length) { el.style.display = "none"; el.innerHTML = ""; return; }
    let h = `<div class="pp-hd">📂 Yerler <span class="pp-sub">(sadece siz)</span></div>`;
    items.forEach((it) => {
      const hidden = new Set(it.hidden || []);
      h += `<div class="pp-item"><div class="pp-item-hd"><b>${esc(it.tesis_adi)}</b>`
        + `<span><a class="pp-zoom" title="Git" onclick="ppZoom('${it.id}','_')">◎</a>`
        + `<a class="pp-del" title="Kaldır" onclick="silManuelKoord('${it.id}')">🗑</a></span></div>`;
      if (it.tree) h += `<div class="pp-children">${renderNodes(it.id, it.tree, "", hidden)}</div>`;
      h += `</div>`;
    });
    el.innerHTML = h;
    el.style.display = "block";
  }

  function restoreAll() {
    if (!userLayer && typeof map !== "undefined") userLayer = L.layerGroup().addTo(map);
    getItems().forEach(drawItem);
    updatePlacesPanel();
  }

  // ---------- modal ----------
  function openModal() { $("coordModal").classList.add("open"); }
  function closeModal() { $("coordModal").classList.remove("open"); }
  function fmt() { const r = document.querySelector('input[name="ca_fmt"]:checked'); return r ? r.value : "wgs84"; }
  function syncFmt() { $("ca_dilimBox").style.display = fmt() === "tm" ? "" : "none"; }
  function parseLines(text) {
    const out = [];
    for (const raw of (text || "").split(/\r?\n/)) {
      const line = raw.trim(); if (!line) continue;
      let parts = line.includes("\t") ? line.split("\t") : line.split(/\s+/);
      parts = parts.map((s) => s.trim()).filter((s) => s !== "");
      if (parts.length >= 3) out.push({ label: parts[0], v1: parts[1], v2: parts[2] });
      else if (parts.length === 2) out.push({ label: "", v1: parts[0], v2: parts[1] });
    }
    return out;
  }
  function setMsg(t, ok) { const m = $("ca_msg"); m.textContent = t; m.style.color = ok ? "#16a34a" : "#dc2626"; }

  function commitItem(geom, nameFallback) {
    const ad = $("ca_ad").value.trim() || nameFallback || "Manuel";
    const item = {
      id: "m" + Date.now() + Math.floor(performance.now() % 1000),
      tesis_adi: ad, centroid: geom.centroid, durum: geom.durum, hidden: [],
    };
    if (geom.tree) item.tree = geom.tree;              // KMZ: klasor agaci
    else if (geom.shapes) item.shapes = geom.shapes;   // manuel: duz sekiller
    else { item.polygon_wgs84 = geom.polygon_wgs84; item.turbine_points = geom.turbine_points; }
    const items = getItems(); items.push(item); setItems(items);
    drawItem(item); updatePlacesPanel();
    if (typeof map !== "undefined" && item.centroid) map.setView(item.centroid, 13);
    if (typeof toast === "function") toast(`"${ad}" haritanıza eklendi (sadece siz görüyorsunuz).`);
    return item;
  }

  async function save() {
    const format = fmt();
    if (format === "tm" && !$("ca_dilim").value) { setMsg("TM/UTM için dilim seçin.", false); return; }
    const polygon = $("ca_polyOn").checked ? parseLines($("ca_poly").value) : [];
    const turbine = $("ca_turbOn").checked ? parseLines($("ca_turb").value) : [];
    if (!polygon.length && !turbine.length) { setMsg("En az bir poligon/türbin yapıştırın (ya da KMZ yükleyin).", false); return; }
    const btn = $("ca_save"); btn.disabled = true; setMsg("İşleniyor…", true);
    try {
      const r = await fetch(API + "/api/facilities/convert", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ coord_type: format, dilim: format === "tm" ? $("ca_dilim").value : null, polygon, turbine }),
      });
      const d = await r.json();
      if (!r.ok) { setMsg("Hata: " + (d.detail || r.status), false); return; }
      commitItem(d, null);
      setMsg("Eklendi ✓", true);
      $("ca_poly").value = ""; $("ca_turb").value = "";
      setTimeout(closeModal, 900);
    } catch (e) { setMsg("Bağlantı hatası: " + e.message, false); }
    finally { btn.disabled = false; }
  }

  async function uploadKmz() {
    const f = $("ca_kmz").files && $("ca_kmz").files[0];
    if (!f) { setMsg("Önce bir KMZ/KML dosyası seçin.", false); return; }
    const btn = $("ca_kmzBtn"); btn.disabled = true; setMsg("Dosya işleniyor…", true);
    try {
      const fd = new FormData(); fd.append("file", f);
      const r = await fetch(API + "/api/facilities/import-kmz", { method: "POST", body: fd });
      const d = await r.json();
      if (!r.ok) { setMsg("Hata: " + (d.detail || r.status), false); return; }
      commitItem(d, d.name || f.name.replace(/\.(kmz|kml)$/i, ""));
      setMsg("KMZ eklendi ✓ — sol-altta 'Yerler' panelinde", true);
      $("ca_kmz").value = "";
      setTimeout(closeModal, 1200);
    } catch (e) { setMsg("Yükleme hatası: " + e.message, false); }
    finally { btn.disabled = false; }
  }

  function init() {
    const btn = $("coordAddBtn");
    if (btn) { btn.style.display = ""; btn.onclick = openModal; }
    $("coordModalX").onclick = closeModal;
    $("coordModal").addEventListener("click", (e) => { if (e.target.id === "coordModal") closeModal(); });
    document.querySelectorAll('input[name="ca_fmt"]').forEach((r) => (r.onchange = syncFmt));
    $("ca_polyOn").onchange = () => ($("ca_polyBox").style.display = $("ca_polyOn").checked ? "" : "none");
    $("ca_turbOn").onchange = () => ($("ca_turbBox").style.display = $("ca_turbOn").checked ? "" : "none");
    $("ca_save").onclick = save;
    $("ca_kmzBtn").onclick = uploadKmz;
    syncFmt();
    restoreAll();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
