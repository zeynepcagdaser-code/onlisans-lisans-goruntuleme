import sqlite3, json
from app.coords import tm_to_wgs84
c = sqlite3.connect('data/epdk.db'); cur = c.cursor()
r = cur.execute("select tesis_adi, il, dilim_meridyeni, ham_koordinat_tm3, centroid_lat, centroid_lng from facilities where tesis_adi like 'FINDIK%'").fetchone()
print("tesis:", r[0], "| il:", r[1], "| dilim:", r[2])
print("centroid:", r[4], r[5])
pts = json.loads(r[3])
print("ilk 3 ham nokta:", pts[:3])
# dilim'leri say
dilimler = {}
for p in pts:
    dilimler[p.get('meridian')] = dilimler.get(p.get('meridian'),0)+1
print("dilim dagilimi:", dilimler)
# ilk noktayi FARKLI dilimlerle dene (dogru il neresi olur)
p0 = pts[0]
print("--- ilk nokta farkli dilimlerle ---")
for d in [27,30,33,36,39]:
    lat,lng = tm_to_wgs84(d, p0['E'], p0['N'])
    print(f"  dilim={d}: ({lat:.3f},{lng:.3f})")
