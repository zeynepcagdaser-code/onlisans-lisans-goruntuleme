"""Bilinen kose/turbini farkli datumlarla cevir - kullanici KMZ'siyle karsilastirsin."""
from app.coords import tm_to_wgs84

# PDF'ten (dilim 27) - kullanicinin KMZ'sinde de olan noktalar
NOKTALAR = {
    "K1 (kuzeydogu kose)": (464384.190, 4507792.570),
    "K68 (bati kose)":     (457208.940, 4507227.470),
    "T5 (turbin)":         (458767.758, 4507286.148),
    "T10 (turbin)":        (460125.151, 4508471.495),
}
for ad, (e, n) in NOKTALAR.items():
    print(f"\n{ad}  E={e} N={n}")
    for datum in ("wgs84", "ed50"):
        lat, lng = tm_to_wgs84(27, e, n, datum)
        print(f"   {datum:6s}: {lat:.6f}, {lng:.6f}   "
              f"https://www.google.com/maps?q={lat:.6f},{lng:.6f}")
