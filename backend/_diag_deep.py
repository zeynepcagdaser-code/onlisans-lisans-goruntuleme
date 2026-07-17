"""Sorunlu buyuk tesislerin ham noktalarini DERINLEMESINE incele:
 - TEKRAR eden (ad,E,N) noktalar (sayfalama cakismasi/WAF artifakti?)
 - ad dizisi yapisi (parsel sinirlari)
 - dilim degisimi
Amac: mesele cekim bozulmasi mi (tekrar/eksik) yoksa gercek karmasik yapi mi."""
import re
import sqlite3
import json

c = sqlite3.connect('data/epdk.db')
cur = c.cursor()

targets = ["KEÇİKAYA HES", "ÇAY HES", "TERAS RES", "HAYAT RES",
           "ENERJİKAN-1", "GOPDUROĞLU REG VE HES", "TAÇ REG. VE HES"]


def adnum(ad):
    m = re.search(r"(\d+)\s*$", str(ad))
    return int(m.group(1)) if m else None


for name in targets:
    row = cur.execute("""select ham_koordinat_tm3 from facilities
        where tesis_adi=? and centroid_lat is not null limit 1""", (name,)).fetchone()
    if not row:
        print(f"[{name}] yok\n"); continue
    ham = json.loads(row[0]) if isinstance(row[0], str) else (row[0] or [])
    n = len(ham)
    # tam-tekrar (ad,E,N)
    seen = {}
    for p in ham:
        k = (str(p.get("ad")), p.get("E"), p.get("N"))
        seen[k] = seen.get(k, 0) + 1
    dup = {k: v for k, v in seen.items() if v > 1}
    dup_pts = sum(v - 1 for v in dup.values())
    # ayni ad ama FARKLI koordinat (gercek cok-parca)
    ad_to_coords = {}
    for p in ham:
        a = str(p.get("ad"))
        ad_to_coords.setdefault(a, set()).add((p.get("E"), p.get("N")))
    ad_multi = {a: len(s) for a, s in ad_to_coords.items() if len(s) > 1}
    # ad dizisi ilk 40 (yapiyi gor)
    seq = [adnum(p.get("ad")) for p in ham]
    print(f"=== {name} | {n} nokta ===")
    print(f"  tam-tekrar (ad,E,N) nokta sayisi : {dup_pts}  (farkli tekrar-anahtari: {len(dup)})")
    print(f"  ayni ad farkli koordinat (parca) : {len(ad_multi)} ad")
    print(f"  ad dizisi ilk 40: {seq[:40]}")
    print()
