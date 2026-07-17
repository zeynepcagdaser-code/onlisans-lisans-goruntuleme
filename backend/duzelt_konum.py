# -*- coding: utf-8 -*-
"""Yanlis/karisik EPDK dilim etiketinden kaynaklanan konum kaymalarini duzelt.

Yontem: Bir tesisin mevcut merkezi ILINE cok uzaksa (>1.5 derece), o tesisin HER
noktasini, tesisin il-merkezine EN YAKIN dusuren dilimle yeniden donustur. E/N
koordinatlari (ham veri) DEGISMEZ; sadece dogru dilim secilir. Il'e zaten yakin
(dogru) tesislere DOKUNULMAZ.
"""
import json
import math
import sqlite3

from app.coords import tm_to_wgs84, process_polygon, VALID_MERIDIANS
from il_koord import il_ref

UZAK_ESIK = 1.5   # merkez il'e bu kadar uzaksa (derece) suphesli -> duzelt
DB = "data/epdk.db"


def best_meridian(E, N, ref):
    """E/N'yi tum dilimlerle dene; il-merkezine (ref) en yakin dusuren dilimi dondur."""
    best_m, best_d = None, 1e9
    for m in sorted(VALID_MERIDIANS):
        la, ln = tm_to_wgs84(m, E, N)
        d = math.hypot(la - ref[0], ln - ref[1])
        if d < best_d:
            best_d, best_m = d, m
    return best_m


def _saglam(p):
    """Ham nokta Turkiye TM araliginda mi? (placeholder 1/111111/333333 elenir)"""
    E, N = p.get("E"), p.get("N")
    return E is not None and N is not None and 150000 < E < 850000 and 4000000 < N < 4700000


def main():
    con = sqlite3.connect(DB, timeout=30)
    c = con.cursor()
    c.execute("""SELECT f.id, f.tesis_adi, f.il, f.centroid_lat, f.centroid_lng,
                        f.ham_koordinat_tm3, f.turbine_points
                 FROM facilities f JOIN licenses l ON f.license_id=l.id
                 WHERE l.lisans_tipi='uretim' AND f.koordinat_alindi=1
                       AND f.koordinat_durumu IN ('ok','supheli')""")
    rows = c.fetchall()
    duzeltilen = 0
    bozuk_temizlenen = 0
    atlanamayan = []
    for fid, ad, il, clat, clng, ham, tw in rows:
        ref = il_ref(il)
        if not ref or clat is None:
            continue
        # mevcut merkez il'e yakinsa DOGRU -> dokunma
        if math.hypot(clat - ref[0], clng - ref[1]) <= UZAK_ESIK:
            continue

        pts = json.loads(ham)
        turb = json.loads(tw) if tw else []
        nt = len(turb)

        # HAM E/N placeholder/bozuk mu? Sagalam nokta yoksa -> koordinatsiz
        if not any(_saglam(p) for p in pts):
            c.execute("""UPDATE facilities SET polygon_wgs84=NULL, turbine_points=NULL,
                         centroid_lat=NULL, centroid_lng=NULL, first_point_lat=NULL,
                         first_point_lng=NULL, koordinat_durumu='koordinat_yok_teyitli'
                         WHERE id=?""", (fid,))
            bozuk_temizlenen += 1
            print(f"BOZUK-TEMIZLENDI: {ad.encode('ascii','replace').decode()} (EPDK placeholder E/N)")
            continue

        # HER noktayi il-referansli dogru dilimle yeniden etiketle
        for p in pts:
            if p.get("E") is None or p.get("N") is None:
                continue
            p["meridian"] = best_meridian(p["E"], p["N"], ref)

        saha = pts[:len(pts) - nt] if nt else pts
        turbin = pts[len(pts) - nt:] if nt else []

        res = process_polygon([{"meridian": p["meridian"], "E": p["E"],
                                "N": p["N"], "ad": p["ad"]} for p in saha])
        if res["centroid_lat"] is None:
            atlanamayan.append(ad)
            continue
        # duzeltme il'e yakinlastirmadi mi? (guvenlik: hala uzaksa uygulama)
        if math.hypot(res["centroid_lat"] - ref[0], res["centroid_lng"] - ref[1]) > UZAK_ESIK + 0.8:
            atlanamayan.append(f"{ad} (duzelmedi)")
            continue

        turbin_wgs = []
        for p in turbin:
            la, ln = tm_to_wgs84(p["meridian"], p["E"], p["N"])
            turbin_wgs.append([round(la, 6), round(ln, 6)])

        c.execute("""UPDATE facilities SET ham_koordinat_tm3=?, polygon_wgs84=?,
                     turbine_points=?, centroid_lat=?, centroid_lng=?,
                     first_point_lat=?, first_point_lng=?, dilim_meridyeni=?,
                     koordinat_durumu=? WHERE id=?""",
                  (json.dumps(saha + turbin), json.dumps(res["polygon_wgs84"]),
                   json.dumps(turbin_wgs) if turbin_wgs else None,
                   res["centroid_lat"], res["centroid_lng"],
                   res["first_point_lat"], res["first_point_lng"],
                   res["meridian"], res["durum"], fid))
        duzeltilen += 1
        old = f"({clat:.2f},{clng:.2f})"
        new = f"({res['centroid_lat']:.2f},{res['centroid_lng']:.2f})"
        print(f"DUZELTILDI: {ad} ({il.encode('ascii','replace').decode()}) {old} -> {new}")

    con.commit()
    con.close()
    print(f"\n=== {duzeltilen} tesis duzeltildi ===")
    if atlanamayan:
        print("Duzeltilemeyen:", atlanamayan)


if __name__ == "__main__":
    main()
