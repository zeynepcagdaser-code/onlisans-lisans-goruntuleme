"""DENEY: ad'e gore sirala, sonra ardisik noktalar arasi BUYUK MESAFE
sicramasinda halkayi bol (parsel siniri). E/N (metre) uzerinde calisir.
Mevcut mantikla self-intersection karsilastir."""
import re
import sqlite3
import json
import math
from statistics import median
from app.coords import tm_to_wgs84, build_rings

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


def rings_jump(pts):
    """Once ad==1'de parsele bol; her parseli ad'e gore sirala; sonra parsel
    ICINDE ardisik E/N mesafesi >> medyan ise TEKRAR bol (sinir sicramasi)."""
    nums = [adnum(p.get("ad")) for p in pts]
    valid = [x for x in nums if x is not None]
    if not valid:
        return []
    mn = min(valid)
    # 1) parsellere bol (ad==mn yeni parsel)
    parcels, cur_ = [], []
    for j, x in enumerate(nums):
        if x == mn and cur_:
            parcels.append(cur_); cur_ = []
        cur_.append(j)
    if cur_:
        parcels.append(cur_)
    rings = []
    for parc in parcels:
        ps = sorted(parc, key=lambda j: nums[j] if nums[j] is not None else 1e9)
        EN = [(pts[j]["E"], pts[j]["N"]) for j in ps]
        if len(EN) < 2:
            continue
        d = [math.dist(EN[i], EN[i+1]) for i in range(len(EN)-1)]
        med = median(d) if d else 0
        thr = max(med * 8, 300)   # sicrama esigi: 8x medyan veya 300m
        # buyuk sicramada alt-halkalara bol
        sub, s = [], [ps[0]]
        for i in range(1, len(ps)):
            if d[i-1] > thr:
                sub.append(s); s = []
            s.append(ps[i])
        if s:
            sub.append(s)
        for seg in sub:
            ll = [[round(*tm_to_wgs84(pts[j]["meridian"], pts[j]["E"], pts[j]["N"])[:1], 6)]
                  for j in seg]  # placeholder (asagida duzgun)
        # duzgun lat/lng
        for seg in sub:
            ring = []
            for j in seg:
                lat, lng = tm_to_wgs84(pts[j]["meridian"], pts[j]["E"], pts[j]["N"])
                ring.append([round(lat, 6), round(lng, 6)])
            rings.append(ring)
    return rings


rows = cur.execute("""select tesis_adi, ham_koordinat_tm3, polygon_wgs84 from facilities
    where centroid_lat is not null and is_active=1""").fetchall()

cur_si = new_si = 0
fixed, broke = [], []
for adi, ham_j, poly_j in rows:
    pts = json.loads(ham_j) if isinstance(ham_j, str) else (ham_j or [])
    pts = [p for p in pts if p.get("meridian") and p.get("E") is not None and p.get("N") is not None]
    if not pts:
        continue
    poly_cur = json.loads(poly_j) if isinstance(poly_j, str) else poly_j
    rings_cur = poly_cur if (poly_cur and isinstance(poly_cur[0][0], list)) else [poly_cur]
    sc = any(self_int(r) for r in rings_cur)
    rj = rings_jump(pts)
    sn = any(self_int(r) for r in rj)
    cur_si += 1 if sc else 0
    new_si += 1 if sn else 0
    if sc and not sn:
        fixed.append((adi, len(rings_cur), len(rj)))
    if not sc and sn:
        broke.append(adi)

print(f"Toplam: {len(rows)}")
print(f"  MEVCUT self-intersect : {cur_si}")
print(f"  JUMP-SPLIT self-inter : {new_si}")
print(f"  DUZELEN: {len(fixed)} | BOZULAN: {len(broke)}")
print()
for adi, nc, nn in fixed[:30]:
    print(f"  + {adi[:40]:40} halka {nc} -> {nn}")
if broke:
    print("  BOZULANLAR:", ", ".join(b[:25] for b in broke[:10]))
