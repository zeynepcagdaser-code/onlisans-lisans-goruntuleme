"""
1) AYAZMA'nin mevcut (dogrulanmis 0.14m) poligonunu referans al (ad->latlng).
2) TUM tesisleri ham E/N'den yeniden hesapla (yeni halka kurulumu + projeksiyon).
3) AYAZMA yeni vs referans: max kose sapmasi (metre) -> <1m olmali.
4) Yeni nested poligonlarda self-intersection say -> 33'ten kaca dustu?
"""
import re, math, json
from app.database import SessionLocal, init_db
from app.models import Facility
from app.coords import process_polygon, tm_to_wgs84


def adnum(ad):
    m = re.search(r"(\d+)\s*$", str(ad))
    return int(m.group(1)) if m else None


def seg_int(p1, p2, p3, p4):
    def ccw(a, b, cc):
        return (cc[1]-a[1])*(b[0]-a[0]) - (b[1]-a[1])*(cc[0]-a[0])
    d1, d2 = ccw(p3, p4, p1), ccw(p3, p4, p2)
    d3, d4 = ccw(p1, p2, p3), ccw(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def self_int(ring):
    n = len(ring)
    if n < 4 or n > 1200:
        return False
    for i in range(n):
        a, b = ring[i], ring[(i+1) % n]
        for j in range(i+1, n):
            if abs(i-j) <= 1 or (i == 0 and j == n-1):
                continue
            if seg_int(a, b, ring[j], ring[(j+1) % n]):
                return True
    return False


def main():
    init_db()
    db = SessionLocal()

    # 1) AYAZMA referans (yeniden hesaplamadan ONCE)
    a = db.query(Facility).filter(Facility.tesis_adi.like("%AYAZMA%")).first()
    ref = {}
    if a and a.ham_koordinat_tm3 and a.polygon_wgs84:
        poly = a.polygon_wgs84
        flat = poly if (poly and isinstance(poly[0][0], (int, float))) else [p for r in poly for p in r]
        for i, p in enumerate(a.ham_koordinat_tm3):
            k = adnum(p.get("ad"))
            if k is not None and i < len(flat):
                ref[k] = flat[i]

    # 2) TUM tesisleri yeniden hesapla
    facs = db.query(Facility).filter(Facility.ham_koordinat_tm3.isnot(None)).all()
    for f in facs:
        pts = f.ham_koordinat_tm3 or []
        if not pts:
            continue
        res = process_polygon(pts)
        f.polygon_wgs84 = res["polygon_wgs84"]
        f.centroid_lat = res["centroid_lat"]
        f.centroid_lng = res["centroid_lng"]
        f.first_point_lat = res["first_point_lat"]
        f.first_point_lng = res["first_point_lng"]
        f.dilim_meridyeni = res["meridian"]
    db.commit()
    print(f"[*] {len(facs)} tesis yeniden hesaplandi.")

    # 3) AYAZMA sapma
    a = db.query(Facility).filter(Facility.tesis_adi.like("%AYAZMA%")).first()
    maxdev = 0.0
    if a and a.polygon_wgs84 and ref:
        new_ring = a.polygon_wgs84[0]  # tek halka, ad'e gore sirali (1..N)
        for k, pt in enumerate(new_ring, start=1):
            if k in ref:
                o = ref[k]
                dlat = (pt[0]-o[0])*111320
                dlng = (pt[1]-o[1])*111320*math.cos(math.radians(pt[0]))
                maxdev = max(maxdev, math.hypot(dlat, dlng))
        print(f"[*] AYAZMA yeni vs dogrulanmis referans: MAX kose sapmasi = {maxdev:.3f} m")
        print(f"    (referans kullanicinin resmi KML'i ile 0.14 m dogrulanmisti)")

    # 4) self-intersection say (yeni nested halkalar)
    si = 0
    si_list = []
    for f in db.query(Facility).filter(Facility.polygon_wgs84.isnot(None)).all():
        for r in (f.polygon_wgs84 or []):
            if r and self_int(r):
                si += 1; si_list.append(f.tesis_adi); break
    print(f"[*] Self-intersection (yeni): {si} tesis (eski: 33)")
    for adi in si_list[:15]:
        print(f"     - {adi[:40]}")
    db.close()


if __name__ == "__main__":
    main()
