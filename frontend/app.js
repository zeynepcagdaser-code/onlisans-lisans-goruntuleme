// Tablo sayfasi: filtre + sunucu-tarafi sayfalama + siralama + CSV export.
const COLS = [
  { key: "lisans_no", label: "Lisans No" },
  { key: "unvan", label: "Unvan" },
  { key: "tesis_adi", label: "Tesis Adı" },
  { key: "il", label: "İl" },
  { key: "ilce", label: "İlçe" },
  { key: "tesis_turu", label: "Tesis Türü" },
  { key: "kaynak_turu", label: "Kaynak Türü" },
  { key: "kurulu_guc_mwm", label: "Kurulu (MWm)" },
  { key: "kurulu_guc_mwe", label: "Kurulu (MWe)" },
  { key: "lisans_durumu", label: "Durum" },
  { key: "baslangic_tarihi", label: "Başlangıç" },
  { key: "bitis_tarihi", label: "Bitiş" },
  { key: "koordinat_durumu", label: "Koordinat" },
];
const state = { page: 1, page_size: 50, sort_by: "tesis_adi", sort_dir: "asc" };

function q() {
  const p = new URLSearchParams({
    page: state.page, page_size: state.page_size,
    sort_by: state.sort_by, sort_dir: state.sort_dir,
  });
  const map = { search: "f_search", il: "f_il", ilce: "f_ilce", kaynak_turu: "f_kaynak",
    tesis_turu: "f_tesis", lisans_durumu: "f_durum" };
  for (const [k, id] of Object.entries(map)) {
    const v = document.getElementById(id).value;
    if (v) p.set(k, v);
  }
  if (document.getElementById("f_coords").checked) p.set("only_with_coords", "true");
  p.set("lisans_tipi", getLT());
  return p.toString();
}

function renderHead() {
  const head = document.getElementById("head");
  head.innerHTML = COLS.map(c => {
    const arrow = state.sort_by === c.key ? (state.sort_dir === "asc" ? "▲" : "▼") : "";
    return `<th data-key="${c.key}">${c.label} <span class="arrow">${arrow}</span></th>`;
  }).join("");
  head.querySelectorAll("th").forEach(th => th.onclick = () => {
    const k = th.dataset.key;
    if (state.sort_by === k) state.sort_dir = state.sort_dir === "asc" ? "desc" : "asc";
    else { state.sort_by = k; state.sort_dir = "asc"; }
    state.page = 1; load();
  });
}

function cell(r, key) {
  if (key === "kaynak_turu") {
    return `<span class="dot" style="background:${colorFor(r.kaynak_turu)}"></span>${r.kaynak_turu || ""}`;
  }
  if (key === "koordinat_durumu") {
    const d = r.koordinat_durumu || "beklemede";
    return `<span class="pill ${d}">${d}</span>`;
  }
  if (key === "tesis_adi") {
    return `<a class="link" onclick="showDetail(${r.id})">${r.tesis_adi || ""}</a>`;
  }
  const v = r[key];
  return v === null || v === undefined ? "" : String(v);
}

async function load() {
  renderHead();
  const data = await getJSON(API + "/api/facilities?" + q());
  const body = document.getElementById("body");
  body.innerHTML = data.items.map(r =>
    "<tr>" + COLS.map(c => `<td>${cell(r, c.key)}</td>`).join("") + "</tr>").join("")
    || `<tr><td colspan="${COLS.length}" class="muted" style="padding:20px;text-align:center">Kayıt yok. "Senkronize Et" ile veri çekin.</td></tr>`;
  const from = (data.page - 1) * data.page_size + (data.total ? 1 : 0);
  const to = Math.min(data.page * data.page_size, data.total);
  document.getElementById("pageInfo").textContent = `${from}-${to} / ${data.total}`;
  document.getElementById("prev").disabled = data.page <= 1;
  document.getElementById("next").disabled = data.page * data.page_size >= data.total;
}

async function loadFilters() {
  const f = await getJSON(API + "/api/facilities/filters");
  const fill = (id, arr) => {
    const el = document.getElementById(id);
    el.innerHTML = `<option value="">Hepsi</option>` + arr.map(v => `<option>${v}</option>`).join("");
  };
  fill("f_il", f.il); fill("f_ilce", f.ilce); fill("f_kaynak", f.kaynak_turu);
  fill("f_tesis", f.tesis_turu); fill("f_durum", f.lisans_durumu);
}

async function loadStats() {
  try {
    const s = await getJSON(API + "/api/sync/stats?" + ltParam());
    const bt = s.by_tipi || {};
    document.getElementById("statRow").innerHTML = `
      <div class="stat"><div class="n">${s.licenses}</div><div class="l">Lisans (${LT_LABEL[getLT()]})</div></div>
      <div class="stat"><div class="n">${s.facilities}</div><div class="l">Tesis</div></div>
      <div class="stat"><div class="n">${s.with_coords}</div><div class="l">Koordinatlı</div></div>
      <div class="stat muted2"><div class="n">${bt.onlisan||0}/${bt.uretim||0}</div><div class="l">Önlisans/Lisans</div></div>`;
  } catch (e) {}
}

async function showDetail(id) {
  const d = await getJSON(API + "/api/facilities/" + id);
  const n = d.polygon_wgs84 ? d.polygon_wgs84.length : 0;
  alert(`${d.tesis_adi}\n\nLisans: ${d.lisans_no}\nUnvan: ${d.unvan}\n` +
    `${d.il} / ${d.ilce} — ${d.kaynak_turu}\nKurulu Güç: ${d.kurulu_guc_mwm} MWm / ${d.kurulu_guc_mwe} MWe\n` +
    `Merkez: ${d.centroid_lat}, ${d.centroid_lng}\nDilim: ${d.dilim_meridyeni} — ${n} poligon noktası\n` +
    `Durum: ${d.koordinat_durumu}`);
}

function debounce(fn, ms) { let t; return () => { clearTimeout(t); t = setTimeout(fn, ms); }; }

function init() {
  initSyncBox();
  initLTToggle(() => { state.page = 1; loadStats(); load(); });
  loadFilters(); loadStats(); load();
  ["f_il", "f_ilce", "f_kaynak", "f_tesis", "f_durum", "f_coords"].forEach(id =>
    document.getElementById(id).onchange = () => { state.page = 1; load(); });
  document.getElementById("f_search").oninput = debounce(() => { state.page = 1; load(); }, 350);
  document.getElementById("pageSize").onchange = e => { state.page_size = +e.target.value; state.page = 1; load(); };
  document.getElementById("prev").onclick = () => { if (state.page > 1) { state.page--; load(); } };
  document.getElementById("next").onclick = () => { state.page++; load(); };
  document.getElementById("btnExport").onclick = () =>
    window.location = API + "/api/facilities/export.csv?" + q();
}
init();
