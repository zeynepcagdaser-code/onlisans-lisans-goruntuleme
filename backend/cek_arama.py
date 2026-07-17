"""
ARAMA-BAZLI uretim koordinat cekici.

Fikir (kullanici onerisi): Koordinati eksik tesisleri DB'den biliyoruz. Her birini
'Tesis Adi' kutusuna yazip aratiriz -> tesis TEMIZ, gercek DOM'da gelir -> koordinat
butonu sorunsuz calisir. Liste-sayfalama sirasindaki 'enjekte DOM' sorunu (butonlarin
bozulmasi) TAMAMEN atlanir.

Captcha: ilk aramada KULLANICI cozer. Sonraki aramalarda otomatik Sorgula denenir;
sonuc gelmezse (captcha tekrar gerekti) kullanicidan yeniden cozmesi istenir.

Kullanim (backend/):  python cek_arama.py
"""
import time
from datetime import datetime, timezone

from app.scraper import (EpdkScraper, ScrapeCallbacks, BlockedError,
                         CaptchaInvalid, SORGULA)
from app.coords import process_polygon
from app.database import SessionLocal
from app.models import Facility, License
from app.sync_manager import facility_hash

TESIS_ADI_INPUT = "#elektrikUretimOzetForm\\:tesisAdiInput"
RESULT_ROWS = "#elektrikUretimOzetSorguSonucu\\:list tbody tr"

WAF_WAIT_S = 90
BETWEEN_SEARCH_S = 1.2


def _utcnow():
    return datetime.now(timezone.utc)


def log(m):
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def _norm(s):
    return (s or "").strip().upper()


class AramaCekici:
    def __init__(self):
        self.db = SessionLocal()
        self.sc = None
        self.done_ok = 0
        self.done_empty = 0

    def eksikler(self):
        """Koordinati eksik uretim tesisleri; ayni tesis_adi'ni TEK arama icin grupla."""
        rows = self.db.query(Facility).join(License).filter(
            License.lisans_tipi == "uretim",
            (Facility.koordinat_alindi == False) |
            (Facility.koordinat_durumu.in_(["beklemede", "hata", "yok"]))
        ).all()
        gruplar = {}
        for f in rows:
            ad = _norm(f.tesis_adi)
            if not ad:
                continue
            gruplar.setdefault(ad, 0)
            gruplar[ad] += 1
        # arama terimi: tesis adinin ILK 3 kelimesi (cok uzun/ozel karakter kacinmak)
        return gruplar

    def _table_sig(self) -> str:
        """Sonuc tablosunun anlik imzasi (ilk satirlar + satir sayisi). Sorgula
        sonrasi bu DEGISIRSE yeni sonuc geldi demektir (captcha gecti)."""
        try:
            return self.sc.page.evaluate(r"""
            () => {
              const tb = document.querySelector("#elektrikUretimOzetSorguSonucu\\:list");
              if (!tb) return 'yok';
              const trs = tb.querySelectorAll('tbody tr');
              let sig = trs.length + '|';
              let n = 0;
              for (const tr of trs) { sig += (tr.innerText||'').slice(0,40); if(++n>=3) break; }
              return sig;
            }
            """) or 'yok'
        except Exception:
            return 'yok'

    def _row_state(self) -> str:
        """rows | empty | yok — mevcut tablo durumu (imzadan bagimsiz)."""
        try:
            return self.sc.page.evaluate(r"""
            () => {
              const tb = document.querySelector("#elektrikUretimOzetSorguSonucu\\:list");
              if (!tb) return 'yok';
              const trs = tb.querySelectorAll('tbody tr');
              for (const tr of trs) {
                if (tr.querySelectorAll('td').length > 1 &&
                    !/Kay.t Bulunamad/i.test(tr.innerText)) return 'rows';
              }
              if (/Kay.t Bulunamad/i.test(tb.innerText||'')) return 'empty';
              return 'yok';
            }
            """) or 'yok'
        except Exception:
            return 'yok'

    def _captcha_iste(self, ilk=False):
        """Kullanicidan captcha coz + Sorgula iste; GERCEK sonuc satiri (>0) gelene
        kadar bekle. Baslangictaki bos 'Kayit Bulunamadi' tablosunu KABUL ETME."""
        if ilk:
            log(">>> ACILAN PENCEREDE: (arama kutusu BOS) 'Ben robot degilim' + "
                "Sorgula'ya bas. Tum liste gelince otomatik devam. Bekliyorum (10dk)...")
        else:
            log(">>> CAPTCHA TEKRAR GEREKTI. Pencerede 'Ben robot degilim' + Sorgula. Bekliyorum...")
        # tesis adi kutusunu TEMIZLE -> Sorgula tum listeyi getirir (satir>0 kesin)
        try:
            self.sc.page.fill(TESIS_ADI_INPUT, "")
        except Exception:
            pass
        for _ in range(600):
            if self._row_state() == 'rows':
                self.sc.capture_form_params()
                time.sleep(0.5)
                return True
            time.sleep(1)
        return False

    def _ara(self, terim: str) -> str:
        """Tesis adini yaz + Sorgula'ya BIZ bas. Tablo imzasi DEGISENE kadar bekle.
        Doner: 'rows'|'empty'|'captcha' (imza degismedi -> captcha gerekti)."""
        sig0 = self._table_sig()
        try:
            self.sc.page.fill(TESIS_ADI_INPUT, terim)
        except Exception as e:
            log(f"    [!] arama kutusu yazilamadi: {str(e)[:60]}")
            return 'captcha'
        try:
            self.sc.page.click(SORGULA, force=True, timeout=5000, no_wait_after=True)
        except Exception:
            try:
                self.sc.page.eval_on_selector(SORGULA, "e=>{if(e)e.click();}")
            except Exception:
                return 'captcha'
        # imza degisimini bekle (yeni sonuc geldi) ~18sn
        deadline = time.time() + 18
        while time.time() < deadline:
            if self._table_sig() != sig0:
                time.sleep(0.4)  # otursun
                return self._row_state()  # 'rows' | 'empty'
            time.sleep(0.4)
        return 'captcha'  # imza hic degismedi -> Sorgula islemedi (captcha)

    def _cek_gorunenler(self, hedef_ad: str):
        """Ekrandaki sonuc(lar)dan hedef_ad'e uyan tesisleri koordinatiyla kaydet."""
        lics = self.sc.parse_current_page()
        islenen = 0
        for lic in lics:
            lno = lic.get("lisans_no") or ""
            for fac in lic.get("facilities", []):
                if _norm(fac.get("tesis_adi")) != hedef_ad:
                    continue
                uh = facility_hash(lno, fac.get("tesis_adi"), fac.get("il"), fac.get("ilce"))
                fo = self.db.query(Facility).filter_by(unique_hash=uh).first()
                if fo is None:
                    continue
                if fo.koordinat_alindi and fo.koordinat_durumu in (
                        "ok", "supheli", "koordinat_yok_teyitli"):
                    islenen += 1
                    continue
                btn = fac.get("coord_btn_id")
                if not btn:
                    fo.koordinat_durumu = "yok"; fo.koordinat_alindi = True
                    self.db.commit(); islenen += 1; continue
                pts = self._cek_koord(btn, fac.get("tesis_adi"))
                if pts:
                    res = process_polygon([{"meridian": p["meridian"], "E": p["E"],
                                            "N": p["N"], "ad": p["ad"]} for p in pts])
                    fo.dilim_meridyeni = res["meridian"]; fo.ham_koordinat_tm3 = pts
                    fo.polygon_wgs84 = res["polygon_wgs84"]
                    fo.centroid_lat = res["centroid_lat"]; fo.centroid_lng = res["centroid_lng"]
                    fo.first_point_lat = res["first_point_lat"]
                    fo.first_point_lng = res["first_point_lng"]
                    fo.koordinat_durumu = res["durum"]; fo.koordinat_alindi = True
                    fo.last_seen = _utcnow()
                    self.db.commit()
                    self.done_ok += 1
                    log(f"  OK  {fac.get('tesis_adi')} ({fac.get('il')}) -> {len(pts)} nokta "
                        f"({res['centroid_lat']},{res['centroid_lng']}) [OK={self.done_ok}]")
                else:
                    self.done_empty += 1
                    log(f"  BOS {fac.get('tesis_adi')} ({fac.get('il')})")
                islenen += 1
        return islenen

    def _cek_koord(self, btn, ad):
        try:
            return self.sc.fetch_coordinates(btn)
        except CaptchaInvalid:
            log(f"    [captcha-validasyon] {ad}")
            return None
        except BlockedError:
            log(f"    [WAF BLOK] {WAF_WAIT_S}sn bekleniyor...")
            time.sleep(WAF_WAIT_S)
            try:
                return self.sc.fetch_coordinates(btn)
            except Exception as e:
                log(f"    [WAF sonrasi hata] {str(e)[:70]}")
                return None
        except Exception as e:
            log(f"    [HATA] {ad}: {str(e)[:80]}")
            return None

    def run(self):
        gruplar = self.eksikler()
        adlar = sorted(gruplar.keys())
        log(f"Eksik-koordinatli benzersiz tesis-adi: {len(adlar)} "
            f"(toplam ~{sum(gruplar.values())} tesis)")
        if not adlar:
            log("Eksik yok. Cikiliyor."); return

        cb = ScrapeCallbacks(log=log)
        self.sc = EpdkScraper(cb, lisans_tipi="uretim")
        self.sc.start()
        self.sc.select_filters()
        self.sc.set_rows_per_page()

        # ILK: arama kutusu BOS, kullanici captcha coz + Sorgula -> tum liste gelir
        if not self._captcha_iste(ilk=True):
            log("[!] Ilk sonuc gelmedi. Cikiliyor."); self.sc.close(); return

        # TUM aramalar: her tesis adini arat; captcha gerekirse kullanicidan iste
        for i, ad in enumerate(adlar, start=1):
            time.sleep(BETWEEN_SEARCH_S)
            r = self._ara(ad)
            if r == 'captcha':
                # Sorgula islemedi -> captcha tekrar gerekti; coz + AYNI aramayi tekrar
                if not self._captcha_iste(ilk=False):
                    log("[!] Captcha yenilenemedi. Duruluyor."); break
                r = self._ara(ad)
                if r == 'captcha':
                    log(f"  (captcha sonrasi hala sonuc yok: {ad})"); continue
            if r == 'empty':
                log(f"  (sonuc yok: {ad})")
                continue
            self._cek_gorunenler(ad)
            if i % 25 == 0:
                log(f"=== Ilerleme: {i}/{len(adlar)} arama | OK={self.done_ok} bos={self.done_empty} ===")

        log(f"=== BITTI: yeni koordinat={self.done_ok}, bos={self.done_empty} ===")
        self.sc.close()
        self.db.close()


if __name__ == "__main__":
    AramaCekici().run()
