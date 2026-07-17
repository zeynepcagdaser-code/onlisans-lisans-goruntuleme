"""Sorunlu tesislerin ham 'ad' yapisini incele: sira no mu, tekrar mi ediyor,
dilim degisiyor mu. Poligon kurulum mantigini dogrulamak icin."""
import sqlite3
import json

c = sqlite3.connect('data/epdk.db')
cur = c.cursor()

targets = ["TERAS RES", "HAYAT RES", "ENERJİKAN-1", "KARACA-3 GES",
           "KEÇİKAYA HES", "ÇAY HES", "MERGE RES", "GES-2 GES"]

for name in targets:
    row = cur.execute("""select tesis_adi, ham_koordinat_tm3 from facilities
        where tesis_adi = ? and centroid_lat is not null limit 1""", (name,)).fetchone()
    if not row:
        print(f"[{name}] bulunamadi"); continue
    adi, ham_j = row
    ham = json.loads(ham_j) if isinstance(ham_j, str) else (ham_j or [])
    ads = [str(p.get("ad")) for p in ham]
    mers = [p.get("meridian") for p in ham]
    print(f"=== {adi} | {len(ham)} nokta ===")
    print(f"  ilk 15 ad : {ads[:15]}")
    print(f"  son 10 ad : {ads[-10:]}")
    print(f"  dilimler  : {sorted(set(mers))}")
    # ad tekrar analizi
    seen = {}
    for a in ads:
        seen[a] = seen.get(a, 0) + 1
    tekrar = {a: n for a, n in seen.items() if n > 1}
    print(f"  benzersiz ad: {len(seen)} / {len(ads)} | tekrar eden ad sayisi: {len(tekrar)}")
    if tekrar:
        ornek = list(tekrar.items())[:5]
        print(f"  tekrar ornek: {ornek}")
    print()
