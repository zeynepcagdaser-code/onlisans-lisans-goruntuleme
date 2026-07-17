"""
Tum tesislerin polygon_wgs84 + centroid degerlerini, DB'deki HAM E/N (ham_koordinat_tm3)
uzerinden YENIDEN HESAPLA. Yeniden cekim YOK. Projeksiyon degistiginde calistir.
"""
from app.database import SessionLocal, init_db
from app.models import Facility
from app.coords import process_polygon


def main():
    init_db()
    db = SessionLocal()
    facs = db.query(Facility).filter(Facility.ham_koordinat_tm3.isnot(None)).all()
    print(f"[*] {len(facs)} tesisin koordinati yeniden hesaplaniyor...")
    updated = 0
    for f in facs:
        pts = f.ham_koordinat_tm3 or []
        if not pts:
            continue
        res = process_polygon(pts)
        f.dilim_meridyeni = res["meridian"]
        f.polygon_wgs84 = res["polygon_wgs84"]
        f.centroid_lat = res["centroid_lat"]
        f.centroid_lng = res["centroid_lng"]
        f.first_point_lat = res["first_point_lat"]
        f.first_point_lng = res["first_point_lng"]
        f.koordinat_durumu = res["durum"] if res["durum"] != "yok" else f.koordinat_durumu
        updated += 1
    db.commit()
    # AYAZMA'yi goster
    a = db.query(Facility).filter(Facility.tesis_adi.like("%AYAZMA%")).first()
    if a:
        print(f"[*] AYAZMA yeni merkez: {a.centroid_lat}, {a.centroid_lng}")
        print(f"    Google Maps: https://www.google.com/maps?q={a.centroid_lat},{a.centroid_lng}")
    db.close()
    print(f"[*] Bitti. {updated} tesis guncellendi (yeniden cekim yapilmadi).")


if __name__ == "__main__":
    main()
