"""TM3 (k0=1.0) vs UTM (k0=0.9996) - hangisi ~1.67km kaymayi aciklar?"""
import math
from pyproj import Transformer

def conv(e, n, lon0=27, k0=1.0, datum="wgs84"):
    if datum == "ed50":
        crs = (f"+proj=tmerc +lat_0=0 +lon_0={lon0} +k={k0} +x_0=500000 +y_0=0 "
               f"+ellps=intl +towgs84=-87,-98,-121,0,0,0,0 +units=m +no_defs")
    else:
        crs = (f"+proj=tmerc +lat_0=0 +lon_0={lon0} +k={k0} +x_0=500000 +y_0=0 "
               f"+ellps=GRS80 +units=m +no_defs")
    lng, lat = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(e, n)
    return lat, lng

def dist(a, b):
    dlat = (b[0]-a[0])*111320
    dlng = (b[1]-a[1])*111320*math.cos(math.radians(a[0]))
    brg = (math.degrees(math.atan2(dlng, dlat)) + 360) % 360
    return math.hypot(dlat, dlng), brg

NOK = {"K1": (464384.190, 4507792.570), "T5": (458767.758, 4507286.148),
       "T10": (460125.151, 4508471.495)}
for ad, (e, n) in NOK.items():
    tm = conv(e, n, k0=1.0, datum="wgs84")
    utm = conv(e, n, k0=0.9996, datum="wgs84")
    d, b = dist(tm, utm)
    print(f"{ad}:")
    print(f"  TM3  (k0=1.0)    : {tm[0]:.6f},{tm[1]:.6f}  maps?q={tm[0]:.6f},{tm[1]:.6f}")
    print(f"  UTM  (k0=0.9996) : {utm[0]:.6f},{utm[1]:.6f}  maps?q={utm[0]:.6f},{utm[1]:.6f}")
    print(f"  fark: {d:.0f} m  yon={b:.0f} derece (TM3->UTM)")
    utm_ed = conv(e, n, k0=0.9996, datum="ed50")
    print(f"  UTM+ED50         : {utm_ed[0]:.6f},{utm_ed[1]:.6f}  maps?q={utm_ed[0]:.6f},{utm_ed[1]:.6f}")
