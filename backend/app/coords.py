"""
EPDK koordinat -> WGS84 donusumu.
DOGRULANMIS PROJEKSIYON (kullanicinin resmi KML'i ile ~0.14 m dogruluk):
  6-derece UTM (k0=0.9996), ED50 (International 1924 elipsoid), fit edilmis
  towgs84 = -94.5,-94.5,-133.5. lon_0 = EPDK'nin verdigi dilim orta meridyeni.
Onceki hata: k0=1 (TM3) + GRS80 -> ~1.5-1.8 km guney kaymasi (EPDK aslinda UTM).
E/N metre, false easting 500000, lat_0=0.
"""
import re
from functools import lru_cache

from pyproj import Transformer

from .config import settings

VALID_MERIDIANS = {27, 30, 33, 36, 39, 42, 45}
# 6-derece UTM dilim orta meridyenleri -> k0=0.9996. Digerleri (30/36/42) 3-derece TM -> k0=1.0.
UTM_MERIDIANS = {27, 33, 39, 45}


def _k0(meridian: int) -> float:
    return 0.9996 if int(meridian) in UTM_MERIDIANS else 1.0


@lru_cache(maxsize=64)
def _transformer(meridian: int, k0: float):
    crs = (f"+proj=tmerc +lat_0=0 +lon_0={meridian} +k={k0} +x_0=500000 +y_0=0 "
           f"+ellps=intl +towgs84=-94.5,-94.5,-133.5,0,0,0,0 +units=m +no_defs")
    return Transformer.from_crs(crs, "EPSG:4326", always_xy=True)


def tm_to_wgs84(meridian: int, easting: float, northing: float, datum: str = None):
    """(lat, lng) dondurur. Dogrulanmis EPDK projeksiyonu (UTM k0=0.9996 / 3-TM k0=1.0,
    ED50 intl elipsoid + fit towgs84). AYAZMA resmi KML ile ~0.14 m dogrulandi."""
    lng, lat = _transformer(int(meridian), _k0(meridian)).transform(easting, northing)
    return lat, lng


def _adnum(ad):
    m = re.search(r"(\d+)\s*$", str(ad))
    return int(m.group(1)) if m else None


def build_rings(raw_points):
    """Ham noktalari (E/N) DOGRU cizim halkalarina donustur.
      - TEK-HALKA (ad kumesi {1..N}, donmus dahil): ad'e gore sirala -> TEK halka.
      - COK-PARCALI (ad numaralari tekrar ediyor): ad GERI sicradiginda yeni parca;
        her parca KENDI icinde ad'e gore sirali, AYRI halka. (Global siralama YOK.)
    Doner: [[[lat,lng],...], ...]  (halka listesi)."""
    idx = [i for i, p in enumerate(raw_points)
           if p.get("meridian") is not None and p.get("E") is not None
           and p.get("N") is not None]
    if not idx:
        return []
    nums = [_adnum(raw_points[i].get("ad")) for i in idx]

    def ll(i):
        p = raw_points[i]
        lat, lng = tm_to_wgs84(p["meridian"], p["E"], p["N"])
        return [round(lat, 6), round(lng, 6)]

    valid = [x for x in nums if x is not None]
    single = bool(valid) and len(set(valid)) == len(valid) == max(valid)
    if single:  # tek halka (temiz ya da donmus) -> ad'e gore sirali tek halka
        order = sorted(range(len(idx)),
                       key=lambda j: nums[j] if nums[j] is not None else 10 ** 9)
        return [[ll(idx[j]) for j in order]]

    # cok-parcali: ad ARDISIK DEGILSE (|fark|!=1) yeni parca. Boylece bir halka
    # ARTAN (1,2,3..) ya da AZALAN (256,255,254..) sirada olabilir -> tek halka
    # kalir; yalnizca gercek kopus ( or. 145->158 veya 33->1 reset) yeni parca acar.
    # (Eski 'x < prev' kurali azalan etiketli tesisi her noktada bolup bozuyordu.)
    parts, cur, prev = [], [], None
    for j, x in enumerate(nums):
        if prev is not None and x is not None and abs(x - prev) != 1:
            parts.append(cur); cur = []
        cur.append(j); prev = x
    if cur:
        parts.append(cur)
    rings = []
    for part in parts:
        ps = sorted(part, key=lambda j: nums[j] if nums[j] is not None else 10 ** 9)
        rings.append([ll(idx[j]) for j in ps])
    return rings


def in_turkey(lat: float, lng: float) -> bool:
    return (settings.tr_lat_min <= lat <= settings.tr_lat_max
            and settings.tr_lng_min <= lng <= settings.tr_lng_max)


def centroid(latlngs):
    n = len(latlngs)
    if n == 0:
        return None, None
    return sum(p[0] for p in latlngs) / n, sum(p[1] for p in latlngs) / n


def _ring_area_centroid(ring):
    """Bir halkanin ALAN-merkezi (shoelace). ring=[[lat,lng],...]. Doner (lat,lng,|alan|)."""
    n = len(ring)
    if n < 3:
        la = sum(p[0] for p in ring) / n
        ln = sum(p[1] for p in ring) / n
        return la, ln, 0.0
    a = cx = cy = 0.0
    for i in range(n):
        x0, y0 = ring[i][1], ring[i][0]        # lng, lat
        x1, y1 = ring[(i + 1) % n][1], ring[(i + 1) % n][0]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a *= 0.5
    if abs(a) < 1e-12:  # dejenere (cizgi) -> vertex ortalamasi
        la = sum(p[0] for p in ring) / n
        ln = sum(p[1] for p in ring) / n
        return la, ln, 0.0
    return cy / (6 * a), cx / (6 * a), abs(a)   # lat, lng, alan


def area_centroid(rings):
    """Cok halkali poligonun ALAN-agirlikli merkezi. Kenara kaymaz, gercek ortayi
    verir. rings: [[[lat,lng],...], ...]. Bos ise vertex ortalamasina duser."""
    good = [r for r in rings if r and len(r) >= 3]
    if not good:
        flat = [p for r in rings for p in r]
        return centroid(flat) if flat else (None, None)
    tot = sla = sln = 0.0
    for r in good:
        la, ln, ar = _ring_area_centroid(r)
        w = ar if ar > 0 else 1e-9
        sla += la * w
        sln += ln * w
        tot += w
    return sla / tot, sln / tot


def tr_num(s):
    """Turkce sayi: '564034,833' -> 564034.833 ; '1.234,5' -> 1234.5 ; '' -> None"""
    if s is None:
        return None
    s = str(s).strip().replace(" ", "")
    if not s or s == "-":
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def split_rings(polygon_wgs84, ham_tm3):
    """Bir tesisin duz [lat,lng] listesini ALT-POLIGONLARA bol. EPDK bazi
    tesislerde birden cok poligon veriyor; 'Ad' 1/K1'e resetlendiginde yeni ring
    baslar. Boylece ayri alanlar birbirine baglanmaz (bozuk sekil onlenir)."""
    if not polygon_wgs84:
        return []
    rings, cur = [], []
    for i, pt in enumerate(polygon_wgs84):
        ad = ""
        if ham_tm3 and i < len(ham_tm3):
            ad = str(ham_tm3[i].get("ad", "")).strip().upper()
        if cur and ad in ("1", "K1", "P1", "N1"):  # yeni alt-poligon basi
            rings.append(cur)
            cur = []
        cur.append(pt)
    if cur:
        rings.append(cur)
    return rings


def _saglam_en(E, N):
    """Ham E/N Turkiye TM araliginda mi? EPDK placeholder (1, 111111, 333333,
    1111111 vb.) ve bos degerler elenir.
    N alt siniri 3.90M: Turkiye'nin EN GUNEYI (Hatay ~35.9-36.2N) northing'i
    ~3.96-4.00M olabilir; eski 4.00M siniri Hatay RES'lerini (SENKOY/SEBENOBA)
    yanlislikla eliyordu. Placeholder repdigit'ler (2222222/3333333) yine <3.90M."""
    try:
        return E is not None and N is not None and 150000 < E < 850000 and 3900000 < N < 4700000
    except TypeError:
        return False


def duzelt_noktalar(pts, il):
    """EPDK'nin yanlis/karisik dilim etiketini ve placeholder koordinatlari duzelt.
      1. Placeholder/bozuk E/N noktalarini ATAR.
      2. Kalan her noktayi, tesisin ILINE en yakin dusuren dilimle yeniden etiketler.
    il referansi bulunamazsa dilim'e dokunmaz (sadece placeholder eler).
    Doner: temizlenmis+dogru-dilimli nokta listesi (bos = gecerli koordinat yok)."""
    from .il_koord import il_ref
    temiz = [dict(p) for p in (pts or []) if _saglam_en(p.get("E"), p.get("N"))]
    if not temiz:
        return []
    ref = il_ref(il) if il else None
    if ref:
        for p in temiz:
            best_m, best_d = None, 1e9
            for m in sorted(VALID_MERIDIANS):
                lat, lng = tm_to_wgs84(m, p["E"], p["N"])
                d = ((lat - ref[0]) ** 2 + (lng - ref[1]) ** 2) ** 0.5
                if d < best_d:
                    best_d, best_m = d, m
            p["meridian"] = best_m
    return temiz


def process_polygon(raw_points, datum: str = None, il: str = None):
    """
    raw_points: [{'ad':.., 'meridian':int, 'E':float, 'N':float}, ...]
    il verilirse: yanlis EPDK dilim etiketi + placeholder koordinatlar duzeltilir.
    polygon_wgs84 = HALKA LISTESI [[[lat,lng],...],...] (tek/cok-parcali dogru kurulmus).
    """
    if il:
        raw_points = duzelt_noktalar(raw_points, il)
    rings = build_rings(raw_points)
    meridian = next((int(p["meridian"]) for p in raw_points
                     if p.get("meridian") is not None), None)
    all_pts = [pt for r in rings for pt in r]
    if not all_pts:
        return {"polygon_wgs84": None, "centroid_lat": None, "centroid_lng": None,
                "first_point_lat": None, "first_point_lng": None,
                "durum": "yok", "meridian": meridian}

    clat, clng = area_centroid(rings)
    if clat is None:
        clat, clng = centroid(all_pts)
    supheli = not all(in_turkey(la, ln) for la, ln in all_pts)
    first = rings[0][0]
    return {
        "polygon_wgs84": rings,                     # NESTED halka listesi
        "centroid_lat": round(clat, 6),
        "centroid_lng": round(clng, 6),
        "first_point_lat": first[0],
        "first_point_lng": first[1],
        "durum": "supheli" if supheli else "ok",
        "meridian": meridian,
    }
