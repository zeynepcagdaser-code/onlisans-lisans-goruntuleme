// Google Earth mantigi: yer isareti / poligon / yol / dikdortgen ciz (Leaflet-Geoman),
// duzenle/sil, tarayicida sakla (localStorage). Cizimi KMZ/KML/GeoJSON/DXF indir.
// Hepsi KISISEL - sunucu veritabanina yazilmaz.
(function () {
  if (typeof map === "undefined" || !map.pm) { console.warn("Geoman yok"); return; }
  const DRAWN_KEY = "cizimlerim_v1";
  const drawn = new L.FeatureGroup().addTo(map);

  // --- Cizim araclari (sol-ust) ---
  map.pm.addControls({
    position: "topleft",
    drawMarker: true, drawPolygon: true, drawPolyline: true, drawRectangle: true,
    drawCircle: false, drawCircleMarker: false, drawText: false,
    editMode: true, dragMode: true, removalMode: true, cutPolygon: false, rotateMode: false,
  });
  map.pm.setGlobalOptions({ layerGroup: drawn });
  try {
    map.pm.setLang("tr");            // Geoman'da Turkce varsa
  } catch (e) {}

  function persist() {
    try { localStorage.setItem(DRAWN_KEY, JSON.stringify(drawn.toGeoJSON())); } catch (e) {}
  }
  function bindEdit(layer) {
    if (layer && layer.on) { layer.on("pm:edit", persist); layer.on("pm:dragend", persist); }
  }
  function restore() {
    let gj;
    try { gj = JSON.parse(localStorage.getItem(DRAWN_KEY) || "null"); } catch (e) { return; }
    if (!gj || !gj.features || !gj.features.length) return;
    const tmp = L.geoJSON(gj, { pointToLayer: (f, ll) => L.marker(ll) });
    tmp.eachLayer((l) => { drawn.addLayer(l); bindEdit(l); });
  }

  map.on("pm:create", (e) => { persist(); bindEdit(e.layer); });
  map.on("pm:remove", persist);
  map.on("pm:cut", persist);
  restore();

  // --- Indirme ---
  async function exportDrawn(fmt) {
    const gj = drawn.toGeoJSON();
    if (!gj.features.length) { if (typeof toast === "function") toast("Önce haritada bir şey çizin."); return; }
    try {
      const r = await fetch(API + "/api/facilities/export", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ format: fmt, name: "cizimlerim", geojson: gj }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        if (typeof toast === "function") toast("Hata: " + (d.detail || r.status));
        return;
      }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "cizimlerim." + fmt; document.body.appendChild(a); a.click();
      a.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000);
      if (typeof toast === "function") toast(fmt.toUpperCase() + " indirildi.");
    } catch (e) {
      if (typeof toast === "function") toast("İndirme hatası: " + e.message);
    }
  }
  window.exportDrawn = exportDrawn;

  function clearDrawn() {
    if (!drawn.getLayers().length) return;
    if (!confirm("Tüm çizimleriniz silinsin mi? (Sadece sizin ekranınızdan)")) return;
    drawn.clearLayers(); persist();
    if (typeof toast === "function") toast("Çizimler temizlendi.");
  }
  window.clearDrawn = clearDrawn;

  // export butonlarini bagla
  const btn = document.getElementById("expBtn");
  if (btn) btn.onclick = () => exportDrawn(document.getElementById("expFmt").value);
  const cb = document.getElementById("expClear");
  if (cb) cb.onclick = clearDrawn;
})();
