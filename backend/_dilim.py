import sqlite3, json
c = sqlite3.connect('data/epdk.db'); cur = c.cursor()
# hem stored dilim_meridyeni hem ham icindeki meridian degerleri
dist = {}
for (ham_s,) in cur.execute("select ham_koordinat_tm3 from facilities where ham_koordinat_tm3 is not null"):
    for p in (json.loads(ham_s) or []):
        m = p.get("meridian")
        dist[m] = dist.get(m, 0) + 1
print("HAM noktalardaki dilim (meridian) dagilimi:")
for k in sorted(x for x in dist if x is not None):
    utm = "UTM (k=0.9996)" if k in (27, 33, 39, 45) else "TM3? (k=1.0)"
    print(f"  dilim={k}: {dist[k]} nokta   -> {utm}")
none = dist.get(None, 0)
if none:
    print(f"  dilim=None: {none} nokta")
# tesis bazinda hangi dilimler
print("\nTesis bazinda dilim_meridyeni:")
td = {}
for (d,) in cur.execute("select dilim_meridyeni from facilities where dilim_meridyeni is not null"):
    td[d] = td.get(d, 0) + 1
for k in sorted(td):
    print(f"  dilim={k}: {td[k]} tesis")
