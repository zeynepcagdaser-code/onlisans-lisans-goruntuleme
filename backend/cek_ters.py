# -*- coding: utf-8 -*-
"""
Uretim koordinatlarini SON SAYFADAN GERIYE dogru, sayfa sayfa cek.
Ilk sayfalar (tam-tarama WAF'a takilmadan once islenen bolge) disinda kalan
taranmamis tesisleri kapsar. Turbin/saha ayrimi + konum-duzeltme (cek_uretim'den).
Artimli: zaten cekilmis (ok/supheli/yok-teyitli) tesisler atlanir.

Kullanim (backend/):  python cek_ters.py
"""
import json
import os
import time
from datetime import datetime, timezone

from app.scraper import EpdkScraper, ScrapeCallbacks
from app.database import SessionLocal
from app.models import Facility, License
from app.sync_manager import facility_hash
from cek_uretim import _fetch_sets, _save_coords, FACILITY_DELAY_S, WAF_WAIT_S

ILERLEME = "teshis/ters_ilerleme.json"   # tamamlanan sayfa no'lari (kesintide devam)


def log(m):
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def _utcnow():
    return datetime.now(timezone.utc)


def _oku_ilerleme():
    try:
        with open(ILERLEME, encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def _yaz_ilerleme(s):
    try:
        os.makedirs("teshis", exist_ok=True)
        with open(ILERLEME, "w", encoding="utf-8") as f:
            json.dump(sorted(s), f)
    except Exception:
        pass


def main():
    db = SessionLocal()
    cb = ScrapeCallbacks(log=log)
    sc = EpdkScraper(cb, lisans_tipi="uretim")
    sc.start()
    sc.select_filters()
    log(">>> ACILAN PENCEREDE: 'Ben robot degilim' + Sorgula. Bekliyorum (10dk)...")
    if not sc.wait_for_captcha_and_results():
        log("[!] Sonuc gelmedi."); sc.close(); db.close(); return
    sc.set_rows_per_page()
    total_pg = sc.total_pages()
    # GUVENLIK: SADECE 'Yururlukte' hedeflenirken >45 sayfa = durum secilmemis demek
    # (~69 sayfa/tum durumlar) -> ilerleme dosyasi (40-sayfa duzenine gore) bozulur. DUR.
    # Baska bir durum (or. 'Hepsi'/'Sona Ermis') KASITLI secildiyse cok sayfa NORMALDIR.
    from app.config import settings as _st
    _durum = (_st.lisans_durumu or "").strip().lower()
    _yururlukte = ("rürlükte" in _durum or "rurlukte" in _durum)
    if _yururlukte and total_pg > 45:
        log(f"[!] {total_pg} sayfa geldi (Yururlukte icin beklenen ~40). Durum SECILI "
            f"DEGIL gibi -> tum durumlar geldi. DURULUYOR. Pencerede 'Yururlukte' secip "
            f"Sorgula'ya basip yeniden baslatin.")
        sc.close(); db.close(); return
    tamamlanan = _oku_ilerleme()
    log(f"Toplam {total_pg} sayfa. SON sayfadan GERIYE cekiliyor. "
        f"Onceden tamamlanan {len(tamamlanan)} sayfa ATLANACAK.")

    done_ok = 0
    done_yok = 0
    page = total_pg
    while page >= 1:
        if page in tamamlanan:
            page -= 1
            continue
        sc.goto_page(page)
        lics = sc.parse_current_page()
        log(f"--- Sayfa {page}/{total_pg} ({len(lics)} lisans) [OK={done_ok} yok={done_yok}] ---")
        # KRITIK: 0 lisans = WAF liste vermedi (sayfa yuklenemedi). Bu sayfayi
        # 'tamamlandi' SAYMA (yoksa gercek tesisler atlanir/kaybolur). DUR.
        if not lics:
            log(f"[!] Sayfa {page}: 0 lisans (WAF liste vermedi). DURULUYOR - bu sayfa "
                f"TAMAMLANMADI. Taze IP ile yeniden baslatinca sayfa {page}'den devam eder.")
            sc.close(); db.close(); return
        reauth_oldu = False
        for lic in lics:
            if reauth_oldu:
                break
            lno = lic.get("lisans_no") or ""
            for fac in lic.get("facilities", []):
                uh = facility_hash(lno, fac.get("tesis_adi"), fac.get("il"), fac.get("ilce"))
                fo = db.query(Facility).filter_by(unique_hash=uh).first()
                if fo is None:
                    continue
                if fo.koordinat_alindi and fo.koordinat_durumu in (
                        "ok", "supheli", "koordinat_yok_teyitli"):
                    continue
                btn_ids = fac.get("coord_btn_ids") or (
                    [fac.get("coord_btn_id")] if fac.get("coord_btn_id") else [])
                if not btn_ids:
                    fo.koordinat_durumu = "yok"; fo.koordinat_alindi = True
                    db.commit(); continue

                time.sleep(FACILITY_DELAY_S)
                sets, captcha_dustu, hata = _fetch_sets(sc, btn_ids)
                if captcha_dustu:
                    log(f"    [captcha dustu] {fac.get('tesis_adi')} -> pencerede tekrar Sorgula")
                    sc.reauth_navigate()
                    if not sc.wait_for_captcha_and_results():
                        log("[!] Yenilenemedi."); sc.close(); db.close(); return
                    sc.set_rows_per_page(); total_pg = sc.total_pages()
                    reauth_oldu = True
                    break
                if hata:
                    # WAF (erisim engellendi) = IP olmus. Bu tesisi atlayip DEVAM edersek
                    # sayfadaki geri kalan tesisler de WAF'a takilip atlanir ve sayfa yine
                    # "tamamlandi" isaretlenir -> cekilmemis tesisler SONSUZA kaybolur.
                    # Bu yuzden WAF gorunce DUR: sayfa TAMAMLANMADI, taze IP ile bu
                    # sayfadan (cekilenler atlanarak) devam edilir.
                    if "WAF" in hata or "engellendi" in hata.lower():
                        log(f"[!] WAF (erisim engellendi): {fac.get('tesis_adi')}. DURULUYOR "
                            f"- sayfa {page} TAMAMLANMADI. Taze IP ile sayfa {page}'den devam eder.")
                        sc.close(); db.close(); return
                    log(f"    [HATA-atlandi] {fac.get('tesis_adi')}: {hata}"); continue
                if not sets:
                    fo.koordinat_durumu = "koordinat_yok_teyitli"
                    fo.koordinat_alindi = True; fo.last_seen = _utcnow()
                    db.commit(); done_yok += 1; continue
                sets.sort(key=len, reverse=True)
                saha = sets[0]; turbin = [p for s in sets[1:] for p in s]
                res, nt = _save_coords(db, fo, saha, turbin)
                done_ok += 1
                tstr = f" +{nt} turbin" if nt else ""
                log(f"OK  {fac.get('tesis_adi')} ({fac.get('il')}) -> {len(saha)} saha{tstr} "
                    f"nokta ({res['centroid_lat']},{res['centroid_lng']}) [OK={done_ok}]")

        if reauth_oldu:
            continue   # ayni sayfayi yeni oturumla yeniden isle (page degismez)
        # sayfa TAM islendi -> kaydet (yeniden baslatinca atlanir)
        tamamlanan.add(page)
        _yaz_ilerleme(tamamlanan)
        page -= 1

    log(f"=== BITTI: OK={done_ok}, yok={done_yok} ===")
    sc.close()
    db.close()


if __name__ == "__main__":
    main()
