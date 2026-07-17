"""43 self-intersecting tesisi kategorize et:
 - Tip A: cok-parselli (ayni ad farkli koordinat var)
 - Tip B: tek-dizi (ad benzersiz)
 ve TAMLIK: tek-dizi icin nokta sayisi == max(ad) mi? (eksik nokta = WAF artifakti)"""
import re
import sqlite3
import json

c = sqlite3.connect('data/epdk.db')
cur = c.cursor()


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
    if n < 4 or n > 1500:
        return False
    for i in range(n):
        a, b = ring[i], ring[(i+1) % n]
        for j in range(i+1, n):
            if abs(i-j) <= 1 or (i == 0 and j == n-1):
                continue
            if seg_int(a, b, ring[j], ring[(j+1) % n]):
                return True
    return False


rows = cur.execute("""select tesis_adi, ham_koordinat_tm3, polygon_wgs84 from facilities
    where centroid_lat is not null and is_active=1""").fetchall()

tipA, tipB_tam, tipB_eksik = [], [], []
for adi, ham_j, poly_j in rows:
    poly = json.loads(poly_j) if isinstance(poly_j, str) else poly_j
    if not poly:
        continue
    rings = poly if isinstance(poly[0][0], list) else [poly]
    if not any(self_int(r) for r in rings):
        continue
    ham = json.loads(ham_j) if isinstance(ham_j, str) else (ham_j or [])
    ham = [p for p in ham if p.get("E") is not None]
    nums = [adnum(p.get("ad")) for p in ham]
    valid = [x for x in nums if x is not None]
    # ayni ad farkli koordinat?
    ad_to = {}
    for p in ham:
        ad_to.setdefault(str(p.get("ad")), set()).add((p.get("E"), p.get("N")))
    multi = any(len(s) > 1 for s in ad_to.values())
    if multi:
        tipA.append(adi)
    else:
        # tek dizi: tam mi?
        tam = valid and len(set(valid)) == len(valid) == max(valid)
        (tipB_tam if tam else tipB_eksik).append((adi, len(valid), max(valid) if valid else 0))

print(f"=== 43 SORUNLU TESIS KATEGORI ===")
print(f"Tip A (cok-parselli): {len(tipA)}")
for a in tipA: print(f"   - {a[:45]}")
print(f"\nTip B TAM (tek-dizi, nokta=max ad): {len(tipB_tam)}")
for a, n, mx in tipB_tam: print(f"   - {a[:40]:40} n={n} max={mx}")
print(f"\nTip B EKSIK (nokta < max ad -> nokta kayip!): {len(tipB_eksik)}")
for a, n, mx in tipB_eksik: print(f"   - {a[:40]:40} n={n} max={mx}  EKSIK={mx-n}")
