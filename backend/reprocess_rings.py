# -*- coding: utf-8 -*-
"""
build_rings duzeltmesini (azalan etiketli poligonlar) SAKLANAN ham veriye uygula.
EPDK'dan YENIDEN CEKMEZ (captcha/WAF yok) - ham_koordinat_tm3'ten yeniden isler.
GUVENLIK: turbine_points olan tesisler ATLANIR (onlarda ham = saha+turbin karisik,
yeniden bolme turbinleri poligona katardi). Sadece halka-yapisi DEGISEN kayit yazilir.

Kullanim (backend/):  python reprocess_rings.py
"""
import json
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models import Facility
from app.coords import process_polygon


def _load(v):
    return json.loads(v) if isinstance(v, str) else v


def ringsig(poly):
    if not poly:
        return None
    try:
        return tuple(len(r) for r in poly)
    except TypeError:
        return None


def main():
    db = SessionLocal()
    facs = (db.query(Facility)
            .filter(Facility.ham_koordinat_tm3.isnot(None),
                    Facility.turbine_points.is_(None)).all())
    kontrol = degisen = 0
    ornek = []
    for fo in facs:
        ham = _load(fo.ham_koordinat_tm3)
        if not ham:
            continue
        kontrol += 1
        old = _load(fo.polygon_wgs84)
        res = process_polygon(ham, il=fo.il)
        new = res["polygon_wgs84"]
        if ringsig(old) == ringsig(new):
            continue
        # cizilebilir halka sayisi arttiysa (ya da yapisi degistiyse) yaz
        fo.polygon_wgs84 = new
        fo.centroid_lat = res["centroid_lat"]
        fo.centroid_lng = res["centroid_lng"]
        fo.first_point_lat = res["first_point_lat"]
        fo.first_point_lng = res["first_point_lng"]
        fo.dilim_meridyeni = res["meridian"]
        fo.koordinat_durumu = res["durum"]
        fo.last_seen = datetime.now(timezone.utc)
        degisen += 1
        if len(ornek) < 15:
            eski_ok = sum(1 for r in (old or []) if r and len(r) >= 3)
            yeni_ok = sum(1 for r in (new or []) if r and len(r) >= 3)
            ornek.append(f"  {fo.tesis_adi[:34]:34} | cizilebilir halka {eski_ok} -> {yeni_ok}")
    db.commit()
    print(f"kontrol edilen (turbinsiz): {kontrol}")
    print(f"DEGISEN (yeniden islenen)  : {degisen}")
    for o in ornek:
        print(o)
    # turbinli + bozuk kalan var mi?
    db.close()


if __name__ == "__main__":
    main()
