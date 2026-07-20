"""
Tek tesis (ya da arama terimine uyan tesisler) koordinat cek + DB'ye kaydet.
Kullanici koordinati OLDUGUNU bildigi tesisi verir; biz arayip cekeriz, poligonu
isler, haritada gosterilecek sekilde kaydederiz. Onlisandaki 'dogrula-dogrula' akisi.

Kullanim (backend/):  python cek_tek.py "HISAR DRES"
"""
import sys
import time
from datetime import datetime, timezone

from app.scraper import EpdkScraper, ScrapeCallbacks, SORGULA
from app.coords import process_polygon, tm_to_wgs84
from app.database import SessionLocal
from app.models import Facility, License
from app.sync_manager import facility_hash

TESIS_INPUT = "#elektrikUretimOzetForm\\:tesisAdiInput"
ARANACAK = sys.argv[1] if len(sys.argv) > 1 else "HİSAR DRES"


def _utcnow():
    return datetime.now(timezone.utc)


def log(m):
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def main():
    db = SessionLocal()
    cb = ScrapeCallbacks(log=log)
    sc = EpdkScraper(cb, lisans_tipi="uretim")
    sc.start()
    sc.select_filters()
    try:
        sc.page.fill(TESIS_INPUT, ARANACAK)
        log(f"Tesis Adi filtresi = '{ARANACAK}'")
    except Exception as e:
        log(f"[!] arama kutusu yazilamadi: {e}")

    log(">>> ACILAN PENCEREDE: 'Ben robot degilim' + Sorgula. Bekliyorum (10dk)...")
    if not sc.wait_for_captcha_and_results():
        log("[!] Sonuc gelmedi."); sc.close(); db.close(); return

    sc.set_rows_per_page()
    lics = sc.parse_current_page()
    log(f"{len(lics)} lisans / arama sonucu geldi.")

    islenen = 0
    for lic in lics:
        lno = lic.get("lisans_no") or ""
        for fac in lic.get("facilities", []):
            ad = fac.get("tesis_adi")
            il = fac.get("il")
            log(f"--- TESIS: {ad} ({il} / {fac.get('ilce')}) lisans={lno}")
            btn_ids = fac.get("coord_btn_ids") or (
                [fac.get("coord_btn_id")] if fac.get("coord_btn_id") else [])
            if not btn_ids:
                log("    koordinat butonu YOK"); continue
            log(f"    {len(btn_ids)} koordinat butonu bulundu")
            # HER butonu AYRI SET olarak cek. Cok-setli tesislerde (orn. RES):
            # en COK noktali set = SAHA sinir poligonu; digerleri = TURBIN noktalari
            # (poligon DEGIL, ayri isaretlenir).
            sets = []
            for bi, bid in enumerate(btn_ids, start=1):
                try:
                    seg = sc.fetch_coordinates(bid)
                except Exception as e:
                    log(f"    [buton {bi} HATA] {str(e)[:90]}"); seg = []
                log(f"    buton {bi}: {len(seg)} nokta")
                if seg:
                    sets.append(seg)

            if not sets:
                log("    -> KOORDINAT YOK (sunucu 'Kayit Bulunamadi' dedi)")
                continue

            sets.sort(key=len, reverse=True)
            saha = sets[0]                              # en cok nokta = saha poligonu
            turbin_setleri = sets[1:]                   # kalanlar = turbin noktalari
            saha_pts = saha
            turbin_pts = [p for s in turbin_setleri for p in s]

            from app.coords import duzelt_noktalar
            res = process_polygon([{"meridian": p["meridian"], "E": p["E"],
                                    "N": p["N"], "ad": p["ad"]} for p in saha_pts], il=il)
            # turbin noktalarini WGS84'e cevir (poligon degil, ayri nokta)
            turbin_wgs = []
            for p in duzelt_noktalar(turbin_pts, il):
                la, ln = tm_to_wgs84(p["meridian"], p["E"], p["N"])
                turbin_wgs.append([round(la, 6), round(ln, 6)])

            uh = facility_hash(lno, ad, il, fac.get("ilce"))
            fo = db.query(Facility).filter_by(unique_hash=uh).first()
            if fo:
                fo.dilim_meridyeni = res["meridian"]
                fo.ham_koordinat_tm3 = saha_pts + turbin_pts
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
                kayit = "DB'ye kaydedildi"
            else:
                kayit = "DB'de kayit bulunamadi (kaydedilemedi)"

            halka = len(res["polygon_wgs84"]) if res["polygon_wgs84"] else 0
            log(f"    -> SAHA: {len(saha_pts)} nokta / {halka} poligon-halkasi | "
                f"TURBIN: {len(turbin_wgs)} nokta | dilim={res['meridian']}")
            log(f"    -> MERKEZ: {res['centroid_lat']}, {res['centroid_lng']}  (durum={res['durum']})")
            log(f"    -> Google Maps: https://www.google.com/maps?q={res['centroid_lat']},{res['centroid_lng']}")
            log(f"    -> {kayit}")
            islenen += 1

    if islenen == 0:
        log("[!] Hicbir tesis koordinati cekilemedi.")
    else:
        log(f"=== {islenen} tesis islendi ===")
    time.sleep(1)
    sc.close()
    db.close()


if __name__ == "__main__":
    main()
