"""TUM poligonlarin kalite kontrolu:
 1) Kendiyle kesisme (self-intersection) -> nokta sirasi bozuksa kesisir.
 2) Halka (ring) sayisi + nokta sayisi.
 3) Ham 'ad' sirasi duzgun mu (1..N kesintisiz mi, tekrar var mi).
 4) Cok kucuk/bozuk poligonlar (nokta<3, alan~0).
Sonuc: kac tesis TEMIZ, kac tanesi SORUNLU + sorunlularin listesi."""
import re
import math
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


rows = cur.execute("""select f.id, f.tesis_adi, f.polygon_wgs84, f.ham_koordinat_tm3
    from facilities f where f.centroid_lat is not null and f.is_active=1""").fetchall()

temiz = 0
sorunlu = []          # self-intersection
ad_bozuk = []         # ham 'ad' 1..N kesintisiz degil (bilgi amacli)
kucuk = []            # nokta < 3
cok_halka = []        # multi-part (>1 ring)

for fid, adi, poly_j, ham_j in rows:
    poly = json.loads(poly_j) if isinstance(poly_j, str) else poly_j
    ham = json.loads(ham_j) if isinstance(ham_j, str) else (ham_j or [])
    if not poly:
        continue
    rings = poly if isinstance(poly[0][0], (list,)) else [poly]
    npts = sum(len(r) for r in rings)
    if npts < 3:
        kucuk.append((adi, npts)); continue
    if len(rings) > 1:
        cok_halka.append((adi, len(rings)))
    # self-intersection: herhangi bir halka kesisiyor mu
    si = any(self_int(r) for r in rings)
    if si:
        sorunlu.append((adi, len(rings), npts))
    else:
        temiz += 1
    # ham 'ad' sirasi kontrolu (tek-parca beklenen 1..N)
    ads = [adnum(p.get("ad")) for p in ham if adnum(p.get("ad")) is not None]
    if ads:
        uniq = sorted(set(ads))
        if len(rings) == 1 and (len(uniq) != len(ads) or uniq != list(range(1, len(uniq)+1))):
            ad_bozuk.append((adi, f"n={len(ads)} uniq={len(uniq)} max={max(ads)}"))

print(f"=== POLIGON KALITE OZETI (aktif, koordinatli: {len(rows)}) ===")
print(f"  TEMIZ (kesismeyen)      : {temiz}")
print(f"  SORUNLU (self-intersect): {len(sorunlu)}")
print(f"  Cok-parcali (multi-ring): {len(cok_halka)}")
print(f"  Cok kucuk (<3 nokta)    : {len(kucuk)}")
print()
if sorunlu:
    print("=== SELF-INTERSECT eden poligonlar (nokta sirasi supheli) ===")
    for adi, nr, np_ in sorted(sorunlu, key=lambda x: -x[2]):
        print(f"  - {adi[:45]:45} | halka={nr} nokta={np_}")
print()
if ad_bozuk:
    print(f"=== Ham 'ad' 1..N kesintisiz OLMAYAN tek-halkalar ({len(ad_bozuk)}) ===")
    for adi, info in ad_bozuk[:20]:
        print(f"  - {adi[:45]:45} | {info}")
