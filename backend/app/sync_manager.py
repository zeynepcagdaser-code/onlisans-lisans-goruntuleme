"""
Senkron orkestrasyonu: scraper'i ayri thread'de calistirir, DB'ye artimli yazar,
durum takibi yapar. FastAPI endpoint'leri buradan tetikler/sorgular.
"""
import hashlib
import threading
import time
import traceback
from datetime import datetime, timezone

from .config import settings
from .coords import process_polygon, tr_num
from .database import SessionLocal
from .models import Facility, License, ScrapeRun
from .scraper import (BlockedError, BlockPersists, CaptchaInvalid, EpdkScraper,
                      ScrapeCallbacks)

_NUM_FIELDS = [
    "kurulu_guc_mwm", "kurulu_guc_mwe", "isletme_kapasite_mwm", "isletme_kapasite_mwe",
    "depolama_kapasite_mwh", "depolama_kurulu_guc_mwe",
    "isletme_depolama_kapasite_mwh", "isletme_depolama_kurulu_guc_mwe",
]


def _utcnow():
    return datetime.now(timezone.utc)


def facility_hash(lisans_no, tesis_adi, il, ilce):
    key = f"{lisans_no}|{tesis_adi}|{il}|{ilce}".lower()
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


class SessionExpired(Exception):
    """Oturum dustu (ust uste cok koordinat hatasi) -> captcha tazelenmeli."""


REAUTH_THRESHOLD = 6  # ust uste bu kadar koordinat hatasi -> oturum dustu say

# WAF/IP engellemesi gorulunce: OLCTUK -> retry'lar blogu BESLIYOR (kayan
# pencere, son istekten sayiyor). Bu yuzden uzun uzun retry YAPMA; tek kisa
# kontrol (blip miydi?) yap, hala bloklu ise HEMEN 'partial' bitir ki IP
# istek almadan sogusun. Sonraki tur (IP dinlendikten sonra) kaldigi yerden.
BLOCK_BACKOFFS = [90]  # tek deneme; gecmezse dur (IP'yi besleme)
FACILITY_DELAY_S = 1.2  # tesisler arasi nezaket gecikmesi (blogu seyreltmek icin)


class SyncState:
    def __init__(self):
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.running = False
        self.durum = "idle"          # idle | starting | waiting_captcha | scraping | success | partial | failed | skipped_no_captcha
        self.message = "Bekliyor"
        self.run_id: int | None = None
        self.lisans_tipi = "onlisan"
        self._stop = False
        self._consec_fail = 0        # ust uste koordinat hatasi (oturum dususu tespiti)

    def snapshot(self):
        return {"running": self.running, "durum": self.durum,
                "message": self.message, "run_id": self.run_id,
                "lisans_tipi": self.lisans_tipi}


STATE = SyncState()


def is_running() -> bool:
    return STATE.running


def request_stop():
    STATE._stop = True


def start_sync(resume: bool = True, lisans_tipi: str = "onlisan",
               sadece_liste: bool = False) -> dict:
    if lisans_tipi not in ("onlisan", "uretim"):
        lisans_tipi = "onlisan"
    with STATE.lock:
        if STATE.running:
            return {"started": False, "reason": "Zaten calisiyor", **STATE.snapshot()}
        STATE.running = True
        STATE.durum = "starting"
        STATE.message = "Tarayici aciliyor..."
        STATE.lisans_tipi = lisans_tipi
        STATE._stop = False
        STATE._consec_fail = 0
        STATE.thread = threading.Thread(
            target=_run, args=(resume, lisans_tipi, sadece_liste), daemon=True)
        STATE.thread.start()
    return {"started": True, **STATE.snapshot()}


def _set(durum=None, message=None):
    if durum:
        STATE.durum = durum
    if message:
        STATE.message = message


def _resume_start_page(db, lisans_tipi="onlisan") -> int:
    """HER ZAMAN sayfa 1. Koordinat cekimi tum sayfalara dagilmis eksik-koordinatli
    tesisleri yakalamak zorunda; last_page (liste ilerlemesi) koordinat ilerlemesini
    YANSITMAZ -> son sayfaya atlamak eksikleri atlar. Cekilmis tesisler artimli
    (koordinat_alindi) sayesinde koordinat cekmeden hizlica atlanir."""
    return 1


def _run(resume: bool, lisans_tipi: str = "onlisan", sadece_liste: bool = False):
    db = SessionLocal()
    run = ScrapeRun(started_at=_utcnow(), durum="running", log_text="",
                    lisans_tipi=lisans_tipi)
    db.add(run); db.commit()
    STATE.run_id = run.id
    logs: list[str] = []

    def log(msg):
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        logs.append(line)
        run.log_text = "\n".join(logs[-500:])
        run.durum = STATE.durum
        try:
            db.commit()
        except Exception:
            db.rollback()

    def on_status(s):
        _set(durum=s)

    cb = ScrapeCallbacks(log=log, on_status=on_status,
                         should_stop=lambda: STATE._stop)
    scraper = EpdkScraper(cb, lisans_tipi=lisans_tipi)
    log(f"Lisans tipi: {lisans_tipi}" + (" | SADECE LISTE (koordinatsiz)" if sadece_liste else ""))
    seen_started = _utcnow()
    try:
        scraper.start()
        scraper.select_filters()
        _set(durum="waiting_captcha", message="Captcha bekleniyor (coz + Sorgula)")
        ok = scraper.wait_for_captcha_and_results()
        if not ok:
            _finish(db, run, "skipped_no_captcha", log)
            return

        _set(durum="scraping", message="Cekiliyor...")
        scraper.set_rows_per_page()
        total_rec = scraper.total_records()
        total_pg = scraper.total_pages()
        run.total_found = total_rec
        db.commit()
        log(f"Toplam {total_rec} kayit / {total_pg} sayfa.")

        start_page = _resume_start_page(db, lisans_tipi) if resume else 1
        if start_page > total_pg:      # bayat/degismis toplam -> guvenli kelepce
            start_page = 1
        if start_page > 1:
            log(f"Devam: {start_page}. sayfaya atlaniyor (kaldigi yerden)...")
        # TAM tur mu? (sayfa 1'den basladiysak ya da re-auth 1'e dondurduyse).
        # Sadece tam turda pasiflestir; resume'lu kismi turda ASLA (yoksa gorulmeyen
        # tesisler yanlislikla pasif olur).
        full_pass = (start_page == 1)

        # Sayfa iterasyonu; oturum dususunde (SessionExpired) otomatik re-captcha
        # ve bastan (artimli -> cekilenler atlanir) devam.
        while True:
            try:
                if _iterate_pages(db, scraper, run, log, start_page, total_pg,
                                  lisans_tipi, sadece_liste):
                    return  # durdurma istendi -> partial olarak bitirildi
                break  # tum sayfalar tamamlandi
            except BlockPersists as bp:
                log(f"[!] WAF engellemesi gecmedi ({bp}). Calisma 'partial' "
                    f"bitiriliyor; IP blogu tamamen gecince (biraz sonra / daha "
                    f"sonra) 'Senkronize Et' -> kaldigi yerden devam eder.")
                _finish(db, run, "partial", log)
                return
            except SessionExpired:
                log(f"[!] Oturum dustu ({REAUTH_THRESHOLD} ust uste hata). "
                    f"Captcha'nin tazelenmesi bekleniyor...")
                _set(durum="waiting_captcha",
                     message="Oturum düştü — açılan pencerede 'Ben robot değilim' + Sorgula")
                STATE._consec_fail = 0
                scraper.reauth_navigate()
                ok = scraper.wait_for_captcha_and_results()
                if not ok:
                    _finish(db, run, "partial", log); return
                scraper.set_rows_per_page()
                total_pg = scraper.total_pages()
                start_page = 1  # bastan; artimli cekilenleri atlar
                full_pass = True  # re-auth 1'e dondu -> 1..son kapsandi
                _set(durum="scraping", message="Devam ediliyor (kaldigi yerden)...")

        if not settings.max_pages and full_pass:
            _deactivate_stale(db, seen_started, lisans_tipi)
        _finish(db, run, "success" if run.errors == 0 else "partial", log)
    except Exception as e:
        log(f"[HATA] {e}\n{traceback.format_exc()[:1500]}")
        _finish(db, run, "failed", log)
    finally:
        scraper.close()
        db.close()
        STATE.running = False


def _iterate_pages(db, scraper, run, log, start_page, total_pg, lisans_tipi="onlisan",
                   sadece_liste=False) -> bool:
    """Sayfalari start_page'den itibaren gez. Durdurma istenirse True doner
    (partial bitirilmis olur); tum sayfalar bitince False. SessionExpired yukari
    firlar (re-auth icin)."""
    if start_page > 1:
        scraper.goto_page(start_page)
    page = start_page
    while True:
        if STATE._stop:
            log("Durdurma istendi."); _finish(db, run, "partial", log)
            return True
        _set(message=f"Sayfa {page}/{total_pg}")
        lics = scraper.parse_current_page()
        _persist_page(db, scraper, lics, run, log, lisans_tipi, sadece_liste)
        run.last_page = page
        db.commit()
        if settings.max_pages and page >= settings.max_pages:
            log(f"max_pages={settings.max_pages} sinirina ulasildi.")
            return False
        if not scraper.next_page():
            if page < total_pg:
                log(f"[!] Sayfalama {page}/{total_pg}'de takildi (son sayfa degil). "
                    f"'partial' bitiriliyor; sonraki tur kaldigi yerden devam eder.")
                _finish(db, run, "partial", log)
                return True  # _run: zaten bitirildi
            return False
        page += 1


def _sleep_interruptible(seconds) -> bool:
    """STATE._stop gelirse erken cikar (False). Uzun beklemeyi parcalara boler."""
    waited = 0.0
    while waited < seconds:
        if STATE._stop:
            return False
        step = min(2.0, seconds - waited)
        time.sleep(step)
        waited += step
    return True


def _fetch_coords_backoff(scraper, btn, log):
    """Koordinat cek; WAF engellemesinde artan surelerle bekle-tekrar-dene.
    Blok tum beklemelere ragmen gecmezse BlockPersists firlat -> calisma
    'partial' biter, IP blogu gecince sonraki tur kaldigi yerden devam eder.
    (Captcha/re-auth blogu ACMAZ; blok IP'de, oturumda degil.)"""
    try:
        return scraper.fetch_coordinates(btn)
    except BlockedError:
        pass
    for i, wait_s in enumerate(BLOCK_BACKOFFS, start=1):
        _set(durum="blocked",
             message=f"WAF engeli — {wait_s}sn bekleniyor ({i}/{len(BLOCK_BACKOFFS)})")
        log(f"    [WAF ENGELI] IP gecici engellendi -> {wait_s}sn bekleniyor "
            f"(deneme {i}/{len(BLOCK_BACKOFFS)})...")
        if not _sleep_interruptible(wait_s):
            raise BlockPersists("kullanici durdurdu")
        _set(durum="scraping", message="Blok sonrasi devam...")
        try:
            pts = scraper.fetch_coordinates(btn)
            log("    [WAF] Blok gecti, devam ediliyor.")
            return pts
        except BlockedError:
            continue
    raise BlockPersists("WAF engellemesi uzun surdu")


def _persist_page(db, scraper, lics, run, log, lisans_tipi="onlisan", sadece_liste=False):
    for lic in lics:
        lno = lic.get("lisans_no") or ""
        if not lno:
            continue
        license_obj = db.query(License).filter_by(lisans_no=lno).first()
        if not license_obj:
            license_obj = License(lisans_no=lno, lisans_tipi=lisans_tipi, first_seen=_utcnow())
            db.add(license_obj)
            run.new_added += 1
        else:
            license_obj.lisans_tipi = lisans_tipi
        for f in ["unvan", "iletisim_adresi", "telefon", "lisans_durumu",
                  "iptal_tarihi", "iptal_aciklama", "baslangic_tarihi", "bitis_tarihi"]:
            setattr(license_obj, f, lic.get(f))
        license_obj.is_active = True
        license_obj.last_seen = _utcnow()
        db.flush()

        for fac in lic.get("facilities", []):
            uh = facility_hash(lno, fac.get("tesis_adi"), fac.get("il"), fac.get("ilce"))
            fac_obj = db.query(Facility).filter_by(unique_hash=uh).first()
            is_new = fac_obj is None
            if is_new:
                fac_obj = Facility(unique_hash=uh, license_id=license_obj.id,
                                   first_seen=_utcnow())
                db.add(fac_obj)
            for f in ["tesis_adi", "il", "ilce", "tesis_turu", "kaynak_turu"]:
                setattr(fac_obj, f, fac.get(f))
            for f in _NUM_FIELDS:
                setattr(fac_obj, f, tr_num(fac.get(f)))
            fac_obj.license_id = license_obj.id
            fac_obj.is_active = True
            fac_obj.last_seen = _utcnow()
            db.flush()

            # SADECE LISTE modu: koordinat CEKME, sadece listeyi kaydet (hizli,
            # WAF'i tetiklemez). koordinat_alindi'ye dokunma -> sonra cekilir.
            if sadece_liste:
                continue
            # Artimli koordinat: yeni ya da henuz alinmamis tesisler
            need = is_new or not fac_obj.koordinat_alindi
            btn = fac.get("coord_btn_id")
            if need and btn:
                time.sleep(FACILITY_DELAY_S)  # tesisler arasi nezaket gecikmesi
                try:
                    pts = _fetch_coords_backoff(scraper, btn, log)
                    res = process_polygon([{"meridian": p["meridian"], "E": p["E"],
                                            "N": p["N"], "ad": p["ad"]} for p in pts])
                    fac_obj.dilim_meridyeni = res["meridian"]
                    fac_obj.ham_koordinat_tm3 = pts or None
                    fac_obj.polygon_wgs84 = res["polygon_wgs84"]
                    fac_obj.centroid_lat = res["centroid_lat"]
                    fac_obj.centroid_lng = res["centroid_lng"]
                    fac_obj.first_point_lat = res["first_point_lat"]
                    fac_obj.first_point_lng = res["first_point_lng"]
                    if pts:
                        fac_obj.koordinat_durumu = res["durum"]
                        run.coords_fetched += 1
                    else:
                        # Validasyonu temiz gecmis, GERCEKTEN bos donen dialog.
                        # (Validasyon hatasi CaptchaInvalid firlatir, buraya gelmez.)
                        fac_obj.koordinat_durumu = "koordinat_yok_teyitli"
                        log(f"    [koordinatsiz-teyitli] {fac.get('tesis_adi')}")
                    fac_obj.koordinat_alindi = True
                    STATE._consec_fail = 0  # basari -> oturum canli
                    if res["durum"] == "supheli":
                        log(f"    [supheli koordinat] {fac.get('tesis_adi')}")
                except BlockPersists:
                    db.commit()  # o ana kadarki koordinatlari kaydet
                    raise
                except CaptchaInvalid:
                    # Captcha token'i dusmus: sonraki tiklamalar da patlar.
                    # Tesisi ISARETLEME (yeniden denensin), hemen re-auth iste.
                    log(f"    [captcha-validasyon] {fac.get('tesis_adi')}: "
                        f"oturum tazelenecek (tesis tekrar denenecek)")
                    db.commit()
                    raise SessionExpired()
                except Exception as ce:
                    fac_obj.koordinat_durumu = "hata"
                    fac_obj.koordinat_alindi = False
                    run.errors += 1
                    STATE._consec_fail += 1
                    log(f"    [koord HATA] {fac.get('tesis_adi')}: {str(ce)[:100]}")
                    if STATE._consec_fail >= REAUTH_THRESHOLD:
                        db.commit()
                        raise SessionExpired()
            elif need and not btn:
                fac_obj.koordinat_durumu = "yok"
                fac_obj.koordinat_alindi = True
        db.commit()


def _deactivate_stale(db, run_started, lisans_tipi="onlisan"):
    """SADECE bu lisans_tipi icinde, bu turda gorulmeyenleri pasiflestir.
    (Diger tipi ASLA etkileme -> uretim cekince onlisan pasif olmaz.)"""
    db.query(License).filter(
        License.lisans_tipi == lisans_tipi, License.last_seen < run_started).update(
        {License.is_active: False}, synchronize_session=False)
    db.query(Facility).filter(
        Facility.last_seen < run_started,
        Facility.license_id.in_(
            db.query(License.id).filter(License.lisans_tipi == lisans_tipi))
    ).update({Facility.is_active: False}, synchronize_session=False)
    db.commit()


def _finish(db, run, durum, log):
    run.durum = durum
    run.finished_at = _utcnow()
    db.commit()
    _set(durum=durum, message=f"Bitti: {durum} "
         f"(yeni={run.new_added}, koordinat={run.coords_fetched}, hata={run.errors})")
    log(f"=== BITTI: {durum} | yeni={run.new_added} koordinat={run.coords_fetched} "
        f"hata={run.errors} ===")
    STATE.run_id = run.id
