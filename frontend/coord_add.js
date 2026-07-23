// Manuel Koordinat Ekle: kullanici koordinat yapistirir -> WGS84'e cevrilir (backend
// /convert, KAYDETMEZ) -> YALNIZCA bu kullanicinin haritasinda + tarayicisinda (localStorage)
// gosterilir. Sunucu veritabanina yazilmaz; kimse baskasinin ekledigini gormez.
(function () {
  const $ = (id) => document.getElementById(id);
  const LS_KEY = "manuel_koordinatlar_v1";
  const RENK = "#ea580c";            // manuel = turuncu (onlisan gri / uretim yesil'den ayri)
  let userLayer = null;

  // ---------- localStorage ----------
  function getItems() {
    try { return JSON.parse(localStorage.getItem(LS_KEY) || "[]"); } catch (e) { return []; }
  }
  function setItems(a) { localStorage.setItem(LS_KEY, JSON.stringify(a)); }

  // ---------- harita cizimi ----------
  function manualIcon() {
    return L.divIcon({
      className: "fac-marker",
      html: `<span style="display:block;width:15px;height:15px;border-radius:50%;`
          + `background:${RENK};border:2px solid #fff;box-shadow:0 0 3px rgba(0,0,0,.6)"></span>`,
      iconSize: [15, 15], iconAnchor: [7, 7], popupAnchor: [0, -8],
    });
  }
  function counts(it) {
    if (it.shapes) return {
      poly: it.shapes.filter((s) => s.kind === "polygon").length,
      line: it.shapes.filter((s) => s.kind === "line").length,
      pt: it.shapes.filter((s) => s.kind === "point").length,
    };
    return { poly: it.polygon_wgs84 ? it.polygon_wgs84.length : 0, line: 0,
             pt: it.turbine_points ? it.turbine_points.length : 0 };
  }
  function popupHtml(it) {
    const c = counts(it);
    const icerik = `${c.poly} poligon` + (c.line ? `, ${c.line} çizgi` : "") + `, ${c.pt} nokta`;
    const row = (k, v) => v ? `<tr><td style="color:#64748b;padding:1px 5px">${k}</td><td>${v}</td></tr>` : "";
    return `<div style="min-width:200px;font-size:13px">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
        <b>${it.tesis_adi || "Manuel tesis"}</b>
        <span style="background:${RENK};color:#fff;font-size:10px;padding:1px 6px;border-radius:8px">MANUEL</span>
      </div>
      <table style="margin-top:4px">
        ${row("Kaynak", it.kaynak_turu)}
        ${row("İl / İlçe", (it.il || "") + (it.ilce ? " / " + it.ilce : ""))}
        ${row("İçerik", icerik)}
      </table>
      <p style="font-size:11px;color:#64748b;margin:5px 0 4px">Yalnızca siz görüyorsunuz (tarayıcınıza kayıtlı).</p>
      <button onclick="silManuelKoord('${it.id}')" style="background:#dc2626;color:#fff;border:none;border-radius:6px;padding:5px 10px;cursor:pointer;font-size:12px">🗑 Sil</button>
    </div>`;
  }
  // KMZ'den gelen sekil: KENDI rengiyle ciz (turuncuya cevirme).
  function drawShape(g, s) {
    if (s.kind === "polygon") {
      (s.rings || []).forEach((r) => {
        if (r.length >= 3) g.addLayer(L.polygon(r, {
          color: s.stroke || RENK, weight: 2,
          fillColor: s.fill || s.stroke || RENK,
          fillOpacity: (s.fillOpacity != null ? s.fillOpacity : 0.25),
        }));
      });
    } else if (s.kind === "line") {
      if ((s.coords || []).length >= 2)
        g.addLayer(L.polyline(s.coords, { color: s.stroke || RENK, weight: 3 }));
    } else if (s.kind === "point") {
      const mk = L.circleMarker(s.coord, { radius: 5, color: "#fff", weight: 2, fillColor: s.color || RENK, fillOpacity: 1 });
      if (s.label) mk.bindTooltip(s.label, { direction: "top", offset: [0, -4] });
      g.addLayer(mk);
    }
  }
  function drawItem(it) {
    const g = L.layerGroup();
    if (it.shapes) {
      it.shapes.forEach((s) => drawShape(g, s));
    } else {                                   // eski/manuel yapi (turuncu varsayilan)
      (it.polygon_wgs84 || []).forEach((ring) => {
        if (ring && ring.length >= 3)
          g.addLayer(L.polygon(ring, { color: RENK, weight: 2, fillOpacity: 0.15, dashArray: "5,4" }));
      });
      (it.turbine_points || []).forEach((t, i) => {
        g.addLayer(L.circleMarker(t, { radius: 5, color: "#7c2d12", weight: 2, fillColor: "#fed7aa", fillOpacity: 1 })
          .bindTooltip("T" + (i + 1), { direction: "top", offset: [0, -4] }));
      });
    }
    const m = L.marker(it.centroid, { icon: manualIcon() });
    m.bindPopup(popupHtml(it));
    g.addLayer(m);
    g._itemId = it.id;
    userLayer.addLayer(g);
  }
  function removeItem(id) {
    setItems(getItems().filter((x) => String(x.id) !== String(id)));
    userLayer.eachLayer((g) => { if (String(g._itemId) === String(id)) userLayer.removeLayer(g); });
    if (typeof toast === "function") toast("Manuel koordinat silindi.");
  }
  window.silManuelKoord = removeItem;

  function restoreAll() {
    if (!userLayer && typeof map !== "undefined") userLayer = L.layerGroup().addTo(map);
    getItems().forEach(drawItem);
  }

  // ---------- modal ----------
  function openModal() { $("coordModal").classList.add("open"); }
  function closeModal() { $("coordModal").classList.remove("open"); }
  function fmt() { const r = document.querySelector('input[name="ca_fmt"]:checked'); return r ? r.value : "wgs84"; }
  function syncFmt() { $("ca_dilimBox").style.display = fmt() === "tm" ? "" : "none"; }

  function parseLines(text) {
    const out = [];
    for (const raw of (text || "").split(/\r?\n/)) {
      const line = raw.trim();
      if (!line) continue;
      let parts = line.includes("\t") ? line.split("\t") : line.split(/\s+/);
      parts = parts.map((s) => s.trim()).filter((s) => s !== "");
      if (parts.length >= 3) out.push({ label: parts[0], v1: parts[1], v2: parts[2] });
      else if (parts.length === 2) out.push({ label: "", v1: parts[0], v2: parts[1] });
    }
    return out;
  }
  function setMsg(t, ok) { const m = $("ca_msg"); m.textContent = t; m.style.color = ok ? "#16a34a" : "#dc2626"; }

  // Cevrilmis geometriyi (manuel /convert ya da KMZ /import-kmz'den) kullaniciya ekle.
  function commitItem(geom, nameFallback) {
    const ad = $("ca_ad").value.trim() || nameFallback || "Manuel tesis";
    const item = {
      id: "m" + Date.now() + Math.floor(performance.now() % 1000),
      tesis_adi: ad, il: $("ca_il").value.trim(), ilce: $("ca_ilce").value.trim(),
      kaynak_turu: $("ca_kaynak").value, lisans_tipi: $("ca_lt").value,
      centroid: geom.centroid, durum: geom.durum,
    };
    if (geom.shapes) item.shapes = geom.shapes;                 // KMZ: renkli sekiller
    else { item.polygon_wgs84 = geom.polygon_wgs84; item.turbine_points = geom.turbine_points; }
    const items = getItems(); items.push(item); setItems(items);
    drawItem(item);
    if (typeof map !== "undefined") map.setView(item.centroid, 13);
    if (typeof toast === "function") toast(`"${ad}" haritanıza eklendi (sadece siz görüyorsunuz).`);
    return item;
  }

  async function save() {
    const format = fmt();
    if (format === "tm" && !$("ca_dilim").value) { setMsg("TM/UTM için dilim seçin.", false); return; }
    const polygon = $("ca_polyOn").checked ? parseLines($("ca_poly").value) : [];
    const turbine = $("ca_turbOn").checked ? parseLines($("ca_turb").value) : [];
    if (!polygon.length && !turbine.length) { setMsg("En az bir poligon ya da türbin noktası yapıştırın (ya da KMZ yükleyin).", false); return; }

    const btn = $("ca_save"); btn.disabled = true; setMsg("İşleniyor…", true);
    try {
      const r = await fetch(API + "/api/facilities/convert", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ coord_type: format, dilim: format === "tm" ? $("ca_dilim").value : null, polygon, turbine }),
      });
      const d = await r.json();
      if (!r.ok) { setMsg("Hata: " + (d.detail || r.status), false); return; }
      const it = commitItem(d, null);
      const c = counts(it);
      setMsg(`Eklendi ✓ (${c.poly} poligon, ${c.pt} nokta)`, true);
      $("ca_poly").value = ""; $("ca_turb").value = "";
      setTimeout(closeModal, 1100);
    } catch (e) {
      setMsg("Bağlantı hatası: " + e.message, false);
    } finally { btn.disabled = false; }
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
      const fallback = d.name || f.name.replace(/\.(kmz|kml)$/i, "");
      const it = commitItem(d, fallback);
      const c = counts(it);
      setMsg(`KMZ eklendi ✓ (${c.poly} poligon${c.line ? `, ${c.line} çizgi` : ""}, ${c.pt} nokta)`, true);
      $("ca_kmz").value = "";
      setTimeout(closeModal, 1200);
    } catch (e) {
      setMsg("Yükleme hatası: " + e.message, false);
    } finally { btn.disabled = false; }
  }

  function init() {
    // Buton HERKESE acik (DB'ye yazmadigi icin guvenli); eklenen sadece kullanicida kalir.
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
