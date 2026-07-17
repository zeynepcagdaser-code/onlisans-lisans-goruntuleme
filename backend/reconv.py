"""AYAZMA'yi ED50 vs WGS84 ile cevir, kaymayi olc, DB'yi ED50'ye guncelle."""
import sqlite3, json, math, sys
from app.coords import process_polygon

ADI = (sys.argv[1] if len(sys.argv) > 1 else "AYAZMA")
c = sqlite3.connect('data/epdk.db'); cur = c.cursor()
r = cur.execute("select id, tesis_adi, ham_koordinat_tm3 from facilities where tesis_adi like ?",
                (f"%{ADI}%",)).fetchone()
if not r or not r[2]:
    print("bulunamadi / koordinat yok"); sys.exit()
fid, adi, pts = r[0], r[1], json.loads(r[2])
w = process_polygon(pts, datum="wgs84")
e = process_polygon(pts, datum="ed50")
print(f"TESIS: {adi} ({len(pts)} nokta)")
print(f"WGS84 merkez: {w['centroid_lat']:.6f}, {w['centroid_lng']:.6f}")
print(f"  Maps: https://www.google.com/maps?q={w['centroid_lat']},{w['centroid_lng']}")
print(f"ED50  merkez: {e['centroid_lat']:.6f}, {e['centroid_lng']:.6f}")
print(f"  Maps: https://www.google.com/maps?q={e['centroid_lat']},{e['centroid_lng']}")
dlat = (e['centroid_lat'] - w['centroid_lat']) * 111320
dlng = (e['centroid_lng'] - w['centroid_lng']) * 111320 * math.cos(math.radians(w['centroid_lat']))
print(f"ED50 vs WGS84 KAYMA: {math.hypot(dlat, dlng):.0f} m  (kuzey={dlat:+.0f}m, dogu={dlng:+.0f}m)")

# DB'yi ED50'ye guncelle (kullanici karsilastirsin)
cur.execute("""update facilities set polygon_wgs84=?, centroid_lat=?, centroid_lng=?,
               first_point_lat=?, first_point_lng=? where id=?""",
            (json.dumps(e["polygon_wgs84"]), e["centroid_lat"], e["centroid_lng"],
             e["first_point_lat"], e["first_point_lng"], fid))
c.commit()
print("\n[*] AYAZMA DB'de ED50'ye guncellendi. Haritayi/KMZ'yi yenile, gercek KMZ ile karsilastir.")
