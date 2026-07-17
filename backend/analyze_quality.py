"""
3 kalite kontrolu (yeniden cekim YOK, ham DB uzerinden):
  1) SIRA: ham_koordinat_tm3 'ad' numaralari bozuk mu (atlama/tekrar/geri sicrama),
     ozellikle 50'lik blok sinirlarinda (sayfalama sirasi bozulmasi).
  2) SEKIL: her poligon(alt-halka) kendi kendini kesiyor mu (self-intersection).
  3) TAMLIK: toplanan nokta sayisi beklenenle (alt-poligon max 'ad') tutuyor mu.
"""
import re
import sqlite3
import json

c = sqlite3.connect('data/epdk.db'); cur = c.cursor()


def num(ad):
    m = re.search(r'(\d+)\s*$', str(ad))
    return int(m.group(1)) if m else None


def split_runs(nums):
    """ad numaralarini alt-poligonlara bol: 1'e reset. None'lar atlanir."""
    nums = [x for x in nums if x is not None]
    runs, cur_run = [], []
    for x in nums:
        if x == 1 and cur_run:          # yeni alt-poligon basi
            runs.append(cur_run); cur_run = []
        cur_run.append(x)
    if cur_run:
        runs.append(cur_run)
    return runs


def order_issues(nums):
    """Ardisik saklanan noktalar komsu mu? |fark|==1 degilse ve reset degilse anomali.
    Doner: (anomali_sayisi, 50_sinirindaki_anomali_sayisi)."""
    anom = block50 = 0
    for i in range(1, len(nums)):
        a, b = nums[i - 1], nums[i]
        if a is None or b is None:
            continue
        d = abs(b - a)
        # d==1 komsu (artan/azalan); b==1 temiz reset (alt-poligon); a==1 reset sonrasi
        if d == 1 or b == 1:
            continue
        anom += 1
        if i % 50 == 0:                  # sayfa (50) siniri
            block50 += 1
    return anom, block50


def completeness(nums):
    """Her alt-poligonda ad kumesi {1..max} tam mi? eksik nokta sayisi."""
    missing = 0
    for run in split_runs(nums):
        s = set(run)
        mx = max(run) if run else 0
        full = set(range(1, mx + 1))
        missing += len(full - s)
    return missing


def seg_int(p1, p2, p3, p4):
    def ccw(a, b, cc):
        return (cc[1]-a[1])*(b[0]-a[0]) - (b[1]-a[1])*(cc[0]-a[0])
    d1 = ccw(p3, p4, p1); d2 = ccw(p3, p4, p2)
    d3 = ccw(p1, p2, p3); d4 = ccw(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def self_intersects(ring):
    n = len(ring)
    if n < 4:
        return False
    if n > 1200:                         # cok buyuk -> atla (perf), ayri isaretle
        return None
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        for j in range(i + 1, n):
            if abs(i - j) <= 1 or (i == 0 and j == n - 1):
                continue
            cc, dd = ring[j], ring[(j + 1) % n]
            if seg_int(a, b, cc, dd):
                return True
    return False


def split_rings_ll(poly, ham):
    rings, cur_r = [], []
    for i, pt in enumerate(poly):
        ad = str(ham[i].get('ad', '')).strip().upper() if i < len(ham) else ''
        if cur_r and ad in ('1', 'K1', 'P1', 'N1'):
            rings.append(cur_r); cur_r = []
        cur_r.append(pt)
    if cur_r:
        rings.append(cur_r)
    return rings


rows = cur.execute("select tesis_adi, ham_koordinat_tm3, polygon_wgs84 from facilities "
                   "where ham_koordinat_tm3 is not null").fetchall()

n_total = 0
sira_50 = 0                 # sayfalama (50) sinirindaki anomali (cekim hatasi gostergesi)
tek_temiz = tek_dondurulmus = tek_eksik = cok_parcali = 0
tek_eksik_liste = []
sekil_bozuk, sekil_buyuk = [], []
for adi, ham_s, poly_s in rows:
    ham = json.loads(ham_s) if ham_s else []
    poly = json.loads(poly_s) if poly_s else []
    if not ham:
        continue
    n_total += 1
    nums = [num(p.get('ad')) for p in ham]
    valid = [x for x in nums if x is not None]
    _, b50 = order_issues(nums)
    sira_50 += b50
    # kategori: tek-halka mi cok-parcali mi?
    if valid:
        cnt, uniq, mx = len(valid), len(set(valid)), max(valid)
        if cnt > mx and uniq < cnt:            # ad numaralari tekrar ediyor -> cok parcali
            cok_parcali += 1
        elif uniq == cnt == mx:                # {1..N} tam, tek halka (donmus olabilir)
            if valid[0] == 1:
                tek_temiz += 1
            else:
                tek_dondurulmus += 1
        elif uniq == cnt and cnt < mx:         # tek halka ama GERCEK eksik nokta (bosluk)
            tek_eksik += 1
            tek_eksik_liste.append((adi, mx - cnt, cnt, mx))
        else:
            cok_parcali += 1
    # sekil
    for r in split_rings_ll(poly, ham):
        si = self_intersects(r)
        if si is True:
            sekil_bozuk.append(adi); break
        if si is None:
            sekil_buyuk.append(adi); break

print(f"=== INCELENEN TESIS: {n_total} ===\n")
print("1) SIRA (cekim sirasi bozulmus mu?):")
print(f"   - 50'lik blok (sayfalama) sinirindaki anomali TOPLAM: {sira_50}")
print(f"     (dusuk = cekim sirasi saglam; anomaliler EPDK'nin kendi sirasindandir)")
print(f"   - Tek-halka TEMIZ (1..N sirali): {tek_temiz}")
print(f"   - Tek-halka DONDURULMUS (ortadan baslamis, sekil dogru): {tek_dondurulmus}")
print(f"   - Cok-parcali (birden cok alt-poligon): {cok_parcali}")
print(f"   - Tek-halka GERCEK EKSIK (bosluk var): {tek_eksik}")

print(f"\n2) SEKIL (native sirayla self-intersection): bozuk={len(sekil_bozuk)} "
      f"| cok-buyuk-atlandi={len(set(sekil_buyuk))}")

print(f"\n3) TAMLIK (gercek eksik noktali tek-halka tesis): {tek_eksik}")
for adi, m, cnt, mx in tek_eksik_liste[:15]:
    print(f"     - {adi[:34]:35s} eksik~{m} (var={cnt}, max_ad={mx})")
