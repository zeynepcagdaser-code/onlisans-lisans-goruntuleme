"""DENEY (DB'ye yazmaz): halka-bolmeyi 'ad==1 (yeni parsel)' ile yap, mevcut
'ad<prev' ile karsilastir. Tum koordinatli tesislerde self-intersection say."""
import re
import sqlite3
import json
from app.coords import tm_to_wgs84

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


def ll(p):
    lat, lng = tm_to_wgs84(p["meridian"], p["E"], p["N"])
    return [round(lat, 6), round(lng, 6)]


def build_current(pts):
    """Mevcut mantik: tekil 1..N -> tek; degilse ad<prev'de bol."""
    nums = [adnum(p.get("ad")) for p in pts]
    valid = [x for x in nums if x is not None]
    if valid and len(set(valid)) == len(valid) == max(valid):
        order = sorted(range(len(pts)), key=lambda j: nums[j] if nums[j] else 1e9)
        return [[ll(pts[j]) for j in order]]
    parts, cur_, prev = [], [], None
    for j, x in enumerate(nums):
        if prev is not None and x is not None and x < prev:
            parts.append(cur_); cur_ = []
        cur_.append(j); prev = x
    if cur_:
        parts.append(cur_)
    return [[ll(pts[j]) for j in sorted(part, key=lambda j: nums[j] or 1e9)] for part in parts]


def build_new(pts):
    """Yeni mantik: tekil 1..N -> tek; degilse ad==1'de (yeni parsel) bol,
    her parca kendi icinde ad'e gore sirali."""
    nums = [adnum(p.get("ad")) for p in pts]
    valid = [x for x in nums if x is not None]
    if valid and len(set(valid)) == len(valid) == max(valid):
        order = sorted(range(len(pts)), key=lambda j: nums[j] if nums[j] else 1e9)
        return [[ll(pts[j]) for j in order]]
    mn = min(valid) if valid else 1
    parts, cur_ = [], []
    for j, x in enumerate(nums):
        if x == mn and cur_:      # yeni parsel basi
            parts.append(cur_); cur_ = []
        cur_.append(j)
    if cur_:
        parts.append(cur_)
    return [[ll(pts[j]) for j in sorted(part, key=lambda j: nums[j] or 1e9)] for part in parts]


def count_si(rings):
    return sum(1 for r in rings if self_int(r))


rows = cur.execute("""select tesis_adi, ham_koordinat_tm3 from facilities
    where centroid_lat is not null and is_active=1""").fetchall()

cur_si = new_si = 0
cur_rings_tot = new_rings_tot = 0
iyilesme = []
for adi, ham_j in rows:
    pts = json.loads(ham_j) if isinstance(ham_j, str) else (ham_j or [])
    pts = [p for p in pts if p.get("meridian") and p.get("E") is not None and p.get("N") is not None]
    if not pts:
        continue
    rc = build_current(pts)
    rn = build_new(pts)
    sc = count_si(rc)
    sn = count_si(rn)
    cur_si += 1 if sc else 0
    new_si += 1 if sn else 0
    cur_rings_tot += len(rc)
    new_rings_tot += len(rn)
    if sc and not sn:
        iyilesme.append((adi, len(rc), len(rn)))

print(f"Toplam tesis: {len(rows)}")
print(f"  MEVCUT (ad<prev)  : self-intersect {cur_si} tesis | toplam halka {cur_rings_tot}")
print(f"  YENI   (ad==min)  : self-intersect {new_si} tesis | toplam halka {new_rings_tot}")
print()
print(f"YENI ile DUZELEN (kesisme kalkan) tesisler: {len(iyilesme)}")
for adi, nc, nn in iyilesme[:25]:
    print(f"  - {adi[:40]:40} halka {nc} -> {nn}")
