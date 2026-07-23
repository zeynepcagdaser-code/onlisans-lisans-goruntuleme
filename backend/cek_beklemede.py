# -*- coding: utf-8 -*-
"""
'beklemede' kalan (ters cekimde HASH tutmadigi icin eslesmemis) uretim
tesislerini TEK captcha ile cek.

Yeniden ARAMA (Sorgula) her seferinde captcha ister; ama PAGINATION istemez.
Bu yuzden: filtresiz TUM listeyi sayfa sayfa gez (tek captcha), hedefleri
NORMALIZE-ISIM ile esle, SADECE hedeflerin koordinatini cek (WAF-minimum: 17
istek). Bulunan koordinat BILINEN DB kaydina (fo id) yazilir. WAF gorulurse
temiz durur (kalan hedefler icin taze IP ile tekrar calistir).

Kullanim (backend/):  python cek_beklemede.py
"""
import time
from datetime import datetime, timezone

from app.scraper import EpdkScraper, ScrapeCallbacks
from app.coords import process_polygon, tm_to_wgs84, duzelt_noktalar
from app.database import SessionLocal
from app.models import Facility, License

_TRMAP = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def _utcnow():
    return datetime.now(timezone.utc)


def log(m):
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def _norm(s):
    s = (s or "").translate(_TRMAP).upper()
    return "".join(ch for ch in s if ch.isalnum())


def _save(db, fo_id, saha, turbin, il):
    fo = db.get(Facility, fo_id)
    if fo is None:
        return None
    res = process_polygon([{"meridian": p["meridian"], "E": p["E"],
                            "N": p["N"], "ad": p["ad"]} for p in saha], il=il)
    turbin_wgs = []
    for p in duzelt_noktalar(turbin, il):
        la, ln = tm_to_wgs84(p["meridian"], p["E"], p["N"])
        turbin_wgs.append([round(la, 6), round(ln, 6)])
    fo.dilim_meridyeni = res["meridian"]
    fo.ham_koordinat_tm3 = saha + turbin
    fo.polygon_wgs84 = res["polygon_wgs84"]
    fo.turbine_points = turbin_wgs or None
    fo.centroid_lat = res["centroid_lat"]
    fo.centroid_lng = res["centroid_lng"]
    fo.first_point_lat = res["first_point_lat"]
    fo.first_point_lng = res["first_point_lng"]
    fo.koordinat_durumu = res["durum"]
    fo.koordinat_alindi = True
    fo.last_seen = _utcnow()
    db.commit()
    return res, len(turbin_wgs)


def main():
    db = SessionLocal()
    q = (db.query(Facility, License).join(License, Facility.license_id == License.id)
         .filter(License.lisans_tipi == "uretim",
                 Facility.koordinat_durumu == "beklemede").all())
    # norm_isim -> (fo_id, ad, lno, il, ilce)
    hedef = {}
    for f, l in q:
        hedef[_norm(f.tesis_adi)] = (f.id, f.tesis_adi, l.lisans_no, f.il, f.ilce)
    log(f"{len(hedef)} 'beklemede' hedef (normalize-isim ile eslenecek).")
    if not hedef:
        log("Beklemede tesis yok."); db.close(); return

    cb = ScrapeCallbacks(log=log)
    sc = EpdkScraper(cb, lisans_tipi="uretim")
    sc.start()
    sc.select_filters()
    log(">>> ACILAN PENCEREDE captcha + Sorgula (ARAMA KUTUSU BOS, tum liste). "
        "Bekliyorum (10dk)...")
    if not sc.wait_for_captcha_and_results():
        log("[!] Sonuc gelmedi."); sc.close(); db.close(); return
    sc.set_rows_per_page()
    total_pg = sc.total_pages()
    log(f"Toplam {total_pg} sayfa. Sadece {len(hedef)} hedef cekilecek (digerleri atlanir).")

    kalan = dict(hedef)   # henuz cekilmeyen hedefler
    ok = yok = 0
    page = 1
    dur = False
    while page <= total_pg and kalan and not dur:
        if page > 1:
            sc.goto_page(page)
        lics = sc.parse_current_page()
        if not lics:
            log(f"[!] Sayfa {page}: 0 sonuc (WAF/oturum). DURULUYOR."); break
        for lic in lics:
            lno = lic.get("lisans_no") or ""
            for fac in lic.get("facilities", []):
                nn = _norm(fac.get("tesis_adi"))
                if nn not in kalan:
                    continue
                fo_id, ad, tlno, il, ilce = kalan.pop(nn)
                btn_ids = fac.get("coord_btn_ids") or (
                    [fac.get("coord_btn_id")] if fac.get("coord_btn_id") else [])
                log(f"HEDEF sayfa {page}: {ad} ({il}) -> {len(btn_ids)} buton")
                if not btn_ids:
                    fo = db.get(Facility, fo_id)
                    fo.koordinat_durumu = "yok"; fo.koordinat_alindi = True
                    fo.last_seen = _utcnow(); db.commit(); yok += 1
                    log("    -> buton YOK ('yok')"); continue
                sets = []
                for bi, bid in enumerate(btn_ids, start=1):
                    try:
                        seg = sc.fetch_coordinates(bid)
                    except Exception as e:
                        msg = str(e)
                        if "WAF" in msg or "engellendi" in msg.lower():
                            log(f"    [!] WAF -> DURULUYOR. Kalan {len(kalan)+1} hedef "
                                f"icin taze IP ile tekrar calistir.")
                            kalan[nn] = (fo_id, ad, tlno, il, ilce)  # geri koy
                            dur = True; break
                        log(f"    [buton {bi} HATA] {msg[:70]}"); seg = []
                    if seg:
                        sets.append(seg)
                if dur:
                    break
                if not sets:
                    fo = db.get(Facility, fo_id)
                    fo.koordinat_durumu = "koordinat_yok_teyitli"
                    fo.koordinat_alindi = True; fo.last_seen = _utcnow(); db.commit()
                    yok += 1; log("    -> KOORDINAT YOK (Kayit Bulunamadi)"); continue
                sets.sort(key=len, reverse=True)
                saha = sets[0]; turbin = [p for s in sets[1:] for p in s]
                out = _save(db, fo_id, saha, turbin, il)
                if out:
                    res, nt = out
                    tstr = f" +{nt} turbin" if nt else ""
                    if res["centroid_lat"] is not None:
                        ok += 1
                    else:
                        yok += 1
                    log(f"    OK -> {len(saha)} saha{tstr} nokta, merkez "
                        f"({res['centroid_lat']},{res['centroid_lng']}) durum={res['durum']}")
            if dur:
                break
        page += 1

    log(f"=== BITTI: ok={ok}, yok={yok}, bulunamayan={len(kalan)} (toplam {len(hedef)}) ===")
    for v in kalan.values():
        log(f"    bulunamadi: {v[1]} ({v[3]})")
    sc.close()
    db.close()


if __name__ == "__main__":
    main()
