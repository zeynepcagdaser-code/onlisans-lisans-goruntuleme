"""Cektigim AYAZMA noktalarini resmi PDF degerleriyle karsilastir + ED50 merkez goster."""
import sqlite3, json
from app.coords import process_polygon

# PDF'ten bilinen bazi kose noktalari (E, N)
PDF = {
    "K1": (464384.190, 4507792.570), "K2": (464374.250, 4507867.770),
    "K122": (463039.780, 4506603.010), "K135": (464384.190, 4507792.570),
    "K68": (457208.940, 4507227.470), "K91": (459328.160, 4506268.090),
}
c = sqlite3.connect('data/epdk.db')
r = c.execute("select ham_koordinat_tm3 from facilities where tesis_adi like '%AYAZMA%'").fetchone()
pts = json.loads(r[0])
mine = {str(p["ad"]).strip().upper(): (round(p["E"], 2), round(p["N"], 2)) for p in pts}
print(f"cektigim nokta sayisi: {len(pts)}")
print("--- PDF vs CEKTIGIM (E,N) ---")
allok = True
for k, (pe, pn) in PDF.items():
    m = mine.get(k)
    ok = m and abs(m[0]-pe) < 0.1 and abs(m[1]-pn) < 0.1
    allok = allok and ok
    print(f"  {k}: PDF=({pe},{pn}) | cektigim={m} | {'TUTUYOR' if ok else 'FARK'}")
print("SONUC:", "TUM KONTROL NOKTALARI BIREBIR TUTUYOR" if allok else "FARK VAR")
w = process_polygon(pts, datum="wgs84")
e = process_polygon(pts, datum="ed50")
print(f"\nWGS84 merkez: {w['centroid_lat']:.6f},{w['centroid_lng']:.6f}")
print(f"ED50  merkez: {e['centroid_lat']:.6f},{e['centroid_lng']:.6f}")
