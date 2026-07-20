// Ortak: renk paleti, senkron kutusu, toast, yardimcilar.
const API = "";

// --- Lisans tipi (onlisan | uretim | hepsi) - tum sayfalarda paylasilir ---
// 'hepsi' = onlisan + uretim birlikte (lisans_tipi filtresi gonderilmez).
function getLT() { return localStorage.getItem("lisans_tipi") || "onlisan"; }
function setLT(t) {
  const v = (t === "uretim" || t === "hepsi") ? t : "onlisan";
  localStorage.setItem("lisans_tipi", v);
}
// 'hepsi' modunda backend'e lisans_tipi GONDERME -> her iki tip doner.
function ltParam() { const t = getLT(); return t === "hepsi" ? "" : "lisans_tipi=" + t; }
const LT_LABEL = { onlisan: "Önlisans", uretim: "Lisans", hepsi: "Önlisans + Lisans" };

// Basliğa/araca yerlestirilecek gecis dugmeleri. onChange -> veriyi yeniden yukle.
function initLTToggle(onChange) {
  const el = document.getElementById("ltToggle");
  if (!el) return;
  function render() {
    const cur = getLT();
    el.innerHTML = ["onlisan", "uretim", "hepsi"].map(t =>
      `<button class="lt-btn${t === cur ? " active" : ""}" data-t="${t}">${LT_LABEL[t]}</button>`
    ).join("");
    el.querySelectorAll(".lt-btn").forEach(b => b.onclick = () => {
      if (getLT() === b.dataset.t) return;
      setLT(b.dataset.t); render();
      if (onChange) onChange(getLT());
    });
  }
  render();
}

// --- Captcha uyari (oturum dusunce) ---
let _flashTimer = null, _origTitle = document.title;
function startTitleFlash() {
  if (_flashTimer) return;
  _flashTimer = setInterval(() => {
    document.title = document.title.startsWith("⚠") ? _origTitle : "⚠ CAPTCHA GEREKLİ";
  }, 800);
}
function stopTitleFlash() {
  if (_flashTimer) { clearInterval(_flashTimer); _flashTimer = null; document.title = _origTitle; }
}

// TEK ses motoru; ilk kullanici hareketinde kilidi acilir (autoplay engelini asar).
let _audio = null, _audioReady = false;
function unlockAudio() {
  try {
    if (!_audio) _audio = new (window.AudioContext || window.webkitAudioContext)();
    if (_audio.state === "suspended") _audio.resume();
    _audioReady = true;
  } catch (e) {}
}
document.addEventListener("click", unlockAudio);   // her tiklamada garanti kilit acma
document.addEventListener("keydown", unlockAudio);

function playAlarm() {
  try {
    if (!_audio) unlockAudio();
    const a = _audio;
    if (!a) return;
    if (a.state === "suspended") a.resume();
    const beeps = 10, dur = 0.4, gap = 0.7;    // ~7 sn
    const VOL = 0.12;                          // dusuk ses seviyesi
    const t0 = a.currentTime + 0.05;
    for (let i = 0; i < beeps; i++) {
      const o = a.createOscillator(), g = a.createGain();
      o.connect(g); g.connect(a.destination);
      o.type = "sine";                         // yumusak ton
      o.frequency.value = i % 2 === 0 ? 880 : 660;
      const s = t0 + i * gap;
      g.gain.setValueAtTime(0.0001, s);
      g.gain.exponentialRampToValueAtTime(VOL, s + 0.04);
      g.gain.setValueAtTime(VOL, s + dur - 0.06);
      g.gain.exponentialRampToValueAtTime(0.0001, s + dur);
      o.start(s); o.stop(s + dur);
    }
  } catch (e) {}
}

// Captcha beklerken COZULENE KADAR her 15 sn'de bir tekrar calar.
let _alarmTimer = null;
function startCaptchaAlert() {
  if (_alarmTimer) return;
  playAlarm();
  _alarmTimer = setInterval(playAlarm, 15000);
  if (window.Notification && Notification.permission === "granted")
    new Notification("⚠ EPDK çekimi — CAPTCHA GEREKLİ",
      { body: "Oturum düştü. Açılan pencerede captcha'yı çöz + Sorgula'ya bas.", requireInteraction: true });
}
function stopCaptchaAlert() {
  if (_alarmTimer) { clearInterval(_alarmTimer); _alarmTimer = null; }
}
function alertCaptcha() { startCaptchaAlert(); }  // geriye donuk uyum
try { if (window.Notification && Notification.permission === "default") Notification.requestPermission(); } catch (e) {}

const KAYNAK_RENK = {
  "HIDROELEKTRIK": "#2563eb", "RUZGAR": "#06b6d4", "GUNES": "#f59e0b",
  "JEOTERMAL": "#dc2626", "BIYOKUTLE": "#16a34a", "TERMIK": "#374151",
  "NUKLEER": "#7c3aed", "AKINTI": "#1e3a8a", "DALGA": "#1e3a8a", "GELGIT": "#1e3a8a",
};
function trUpper(s) {
  return (s || "").toLocaleUpperCase("tr-TR")
    .replace(/İ/g, "I").replace(/Ş/g, "S").replace(/Ğ/g, "G")
    .replace(/Ü/g, "U").replace(/Ö/g, "O").replace(/Ç/g, "C").replace(/[^A-Z]/g, "");
}
function colorFor(kaynak) {
  return KAYNAK_RENK[trUpper(kaynak)] || "#9ca3af";
}

function toast(msg) {
  let t = document.getElementById("toast");
  if (!t) { t = document.createElement("div"); t.id = "toast"; document.body.appendChild(t); }
  t.textContent = msg; t.classList.add("show");
  clearTimeout(t._t); t._t = setTimeout(() => t.classList.remove("show"), 2600);
}

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}

// --- Senkron kontrol kutusu (her sayfada) ---
function initSyncBox() {
  const box = document.getElementById("syncBox");
  if (!box) return;
  box.innerHTML = `
    <span id="syncBadge" class="badge idle">—</span>
    <span id="syncMsg" class="muted" style="color:#e0f2fe;font-size:12px;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"></span>
    <label class="sync-opt" title="Koordinat çekmeden sadece listeyi tamamla (hızlı, WAF'ı tetiklemez)"><input type="checkbox" id="syncListOnly"> Sadece liste</label>
    <button class="btn" id="syncStart">Senkronize Et</button>`;
  const badge = box.querySelector("#syncBadge");
  const msg = box.querySelector("#syncMsg");
  const btn = box.querySelector("#syncStart");

  btn.onclick = async () => {
    const t = getLT();
    const listOnly = box.querySelector("#syncListOnly").checked;
    const mod = listOnly ? " (SADECE LİSTE — koordinatsız)" : "";
    if (!confirm(`${LT_LABEL[t]} lisanslari çekilecek${mod}. Görünür tarayıcı açılacak; captcha'yı çözüp Sorgula'ya basın, gerisi otomatik. Başlatılsın mı?`)) return;
    try { await fetch(API + `/api/sync/start?${ltParam()}&sadece_liste=${listOnly}`, { method: "POST" }); toast(`${LT_LABEL[t]} senkronu başlatıldı${mod}. Açılan pencerede captcha'yı çözün.`); }
    catch (e) { toast("Başlatılamadı: " + e.message); }
  };

  let prevDurum = null;
  async function poll() {
    try {
      const s = await getJSON(API + "/api/sync/status");
      badge.className = "badge " + (s.durum || "idle");
      badge.textContent = ({idle:"Hazır", starting:"Başlatılıyor", waiting_captcha:"⚠ Captcha bekleniyor",
        scraping:"Çekiliyor", success:"Tamamlandı", partial:"Kısmi", failed:"Hata",
        skipped_no_captcha:"Atlandı"})[s.durum] || s.durum;
      msg.textContent = s.message || "";
      btn.disabled = s.running;
      btn.textContent = s.running ? "Çalışıyor…" : "Senkronize Et";
      // Oturum dusup captcha beklenince UYAR (siren + baslik yanip soner)
      if (s.durum === "waiting_captcha") { startCaptchaAlert(); startTitleFlash(); }
      else { stopCaptchaAlert(); stopTitleFlash(); }
      prevDurum = s.durum;
    } catch (e) {}
  }
  poll(); setInterval(poll, 2500);
}
