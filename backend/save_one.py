"""
Tek tesis(ler)i cek + DB'ye KAYDET (haritada gorunur). Tam poligon dahil.
Kullanim:  python save_one.py AYAZMA
"""
import sys
import time
from datetime import datetime, timezone

from app.database import SessionLocal, init_db
from app.models import License, Facility
from app.scraper import EpdkScraper, ScrapeCallbacks
from app.coords import process_polygon, tr_num
from app.sync_manager import facility_hash

TESIS_ADI = "#elektrikUretimOzetForm\\:tesisAdiInput"
NUM = ["kurulu_guc_mwm", "kurulu_guc_mwe", "isletme_kapasite_mwm", "isletme_kapasite_mwe",
       "depolama_kapasite_mwh", "depolama_kurulu_guc_mwe",
       "isletme_depolama_kapasite_mwh", "isletme_depolama_kurulu_guc_mwe"]


def now():
    return datetime.now(timezone.utc)


def main():
    aranan = (sys.argv[1] if len(sys.argv) > 1 else "AYAZMA").upper()
    init_db()
    cb = ScrapeCallbacks(log=lambda m: print("  ", m))
    sc = EpdkScraper(cb)
    sc.start()
    sc.select_filters()
    try:
        sc.page.fill(TESIS_ADI, aranan)
        print(f"[*] Tesis Adi filtresi = '{aranan}'")
    except Exception as e:
        print("[!] tesis adi yazilamadi:", e)

    print("\n>>> Acilan pencerede: 'Ben robot degilim' + Sorgula. Bekleniyor...\n")
    if not sc.wait_for_captcha_and_results():
        print("[!] Sonuc gelmedi."); sc.close(); return
    sc.set_rows_per_page()
    lics = sc.parse_current_page()

    db = SessionLocal()
    saved = 0
    for lic in lics:
        lno = lic.get("lisans_no") or ""
        if not lno:
            continue
        for fac in lic.get("facilities", []):
            if aranan not in (fac.get("tesis_adi") or "").upper():
                continue
            # --- lisans ---
            lo = db.query(License).filter_by(lisans_no=lno).first()
            if not lo:
                lo = License(lisans_no=lno, first_seen=now()); db.add(lo)
            for f in ["unvan", "iletisim_adresi", "telefon", "lisans_durumu",
                      "iptal_tarihi", "iptal_aciklama", "baslangic_tarihi", "bitis_tarihi"]:
                setattr(lo, f, lic.get(f))
            lo.is_active = True; lo.last_seen = now(); db.flush()
            # --- tesis ---
            uh = facility_hash(lno, fac.get("tesis_adi"), fac.get("il"), fac.get("ilce"))
            fo = db.query(Facility).filter_by(unique_hash=uh).first()
            if not fo:
                fo = Facility(unique_hash=uh, license_id=lo.id, first_seen=now()); db.add(fo)
            for f in ["tesis_adi", "il", "ilce", "tesis_turu", "kaynak_turu"]:
                setattr(fo, f, fac.get(f))
            for f in NUM:
                setattr(fo, f, tr_num(fac.get(f)))
            fo.license_id = lo.id; fo.is_active = True; fo.last_seen = now()
            # --- koordinat (tam poligon) ---
            pts = sc.fetch_coordinates(fac.get("coord_btn_id"))
            res = process_polygon(pts)
            fo.dilim_meridyeni = res["meridian"]
            fo.ham_koordinat_tm3 = pts or None
            fo.polygon_wgs84 = res["polygon_wgs84"]
            fo.centroid_lat = res["centroid_lat"]
            fo.centroid_lng = res["centroid_lng"]
            fo.first_point_lat = res["first_point_lat"]
            fo.first_point_lng = res["first_point_lng"]
            fo.koordinat_durumu = res["durum"]
            fo.koordinat_alindi = True
            db.commit()
            saved += 1
            print(f"KAYDEDILDI: {fac.get('tesis_adi')} | {len(pts)} nokta | "
                  f"merkez {res['centroid_lat']},{res['centroid_lng']} | durum {res['durum']}")
    db.close()
    time.sleep(2)
    sc.close()
    print(f"\n[*] Bitti. {saved} tesis DB'ye kaydedildi (haritada gorunur).")


if __name__ == "__main__":
    main()
