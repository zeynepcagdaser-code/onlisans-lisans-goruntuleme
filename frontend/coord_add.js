// Manuel Koordinat Ekle: modal + Excel-yapistir ayristirma + POST /api/facilities/manual.
// Buton YALNIZCA LOKALDE gorunur (bulutta yazma kalici olmaz -> /api/sync/status ile ayirt et).
(function () {
  const $ = (id) => document.getElementById(id);

  // --- butonu sadece lokalde goster ---
  async function initButton() {
    const btn = $("coordAddBtn");
    if (!btn) return;
    let local = false;
    try { local = (await fetch(API + "/api/sync/status")).ok; } catch (e) { local = false; }
    if (!local) { btn.style.display = "none"; return; }
    btn.style.display = "";
    btn.onclick = openModal;
  }

  function openModal() { $("coordModal").classList.add("open"); }
  function closeModal() { $("coordModal").classList.remove("open"); }

  // --- format (WGS84/TM) -> dilim kutusu ---
  function fmt() {
    const r = document.querySelector('input[name="ca_fmt"]:checked');
    return r ? r.value : "wgs84";
  }
  function syncFmt() {
    $("ca_dilimBox").style.display = fmt() === "tm" ? "" : "none";
  }

  // --- Excel yapistir -> [{label,v1,v2}] ---
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

  function setMsg(t, ok) {
    const m = $("ca_msg");
    m.textContent = t;
    m.style.color = ok ? "#16a34a" : "#dc2626";
  }

  async function save() {
    const ad = $("ca_ad").value.trim();
    if (!ad) { setMsg("Tesis adı gerekli.", false); return; }
    const format = fmt();
    if (format === "tm" && !$("ca_dilim").value) { setMsg("TM/UTM için dilim seçin.", false); return; }

    const polyOn = $("ca_polyOn").checked;
    const turbOn = $("ca_turbOn").checked;
    const polygon = polyOn ? parseLines($("ca_poly").value) : [];
    const turbine = turbOn ? parseLines($("ca_turb").value) : [];
    if (!polygon.length && !turbine.length) {
      setMsg("En az bir poligon ya da türbin noktası yapıştırın.", false); return;
    }

    const payload = {
      tesis_adi: ad, il: $("ca_il").value.trim(), ilce: $("ca_ilce").value.trim(),
      kaynak_turu: $("ca_kaynak").value, lisans_tipi: $("ca_lt").value,
      coord_type: format, dilim: format === "tm" ? $("ca_dilim").value : null,
      polygon, turbine,
    };

    const btn = $("ca_save");
    btn.disabled = true; setMsg("Kaydediliyor…", true);
    try {
      const r = await fetch(API + "/api/facilities/manual", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const d = await r.json();
      if (!r.ok) { setMsg("Hata: " + (d.detail || r.status), false); btn.disabled = false; return; }
      setMsg(`Eklendi: ${d.halka} halka, ${d.turbin} türbin (${d.durum}).`, true);
      if (typeof toast === "function") toast(`"${d.tesis_adi}" haritaya işlendi.`);
      // haritayi yenile + yeni tesise git
      if (typeof loadData === "function") await loadData();
      if (typeof map !== "undefined" && d.centroid) map.setView([d.centroid[0], d.centroid[1]], 13);
      setTimeout(closeModal, 900);
    } catch (e) {
      setMsg("Bağlantı hatası: " + e.message, false); btn.disabled = false;
    } finally {
      btn.disabled = false;
    }
  }

  function init() {
    initButton();
    $("coordModalX").onclick = closeModal;
    $("coordModal").addEventListener("click", (e) => { if (e.target.id === "coordModal") closeModal(); });
    document.querySelectorAll('input[name="ca_fmt"]').forEach((r) => (r.onchange = syncFmt));
    $("ca_polyOn").onchange = () => ($("ca_polyBox").style.display = $("ca_polyOn").checked ? "" : "none");
    $("ca_turbOn").onchange = () => ($("ca_turbBox").style.display = $("ca_turbOn").checked ? "" : "none");
    $("ca_save").onclick = save;
    syncFmt();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
