"""Uretim (tam lisans) sayfasinin form yapisini onlisans ile karsilastir.
GET ile HTML cek, form alan ID'lerini/isimlerini cikar."""
import re
import urllib.request

URL = ("https://lisans.epdk.gov.tr/epvys-web/faces/pages/lisans/"
       "elektrikUretim/elektrikUretimOzetSorgula.xhtml")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

req = urllib.request.Request(URL, headers={"User-Agent": UA})
try:
    with urllib.request.urlopen(req, timeout=25) as r:
        html = r.read().decode("utf-8", "replace")
        code = r.status
except Exception as e:
    print("HATA:", e)
    raise SystemExit

print(f"HTTP {code}, {len(html)} bytes")
print()
# form id
forms = re.findall(r'<form[^>]*id="([^"]+)"', html)
print("form id'leri:", forms)
print()
# input/select name'leri (elektrikUretimOzetForm:...)
names = sorted(set(re.findall(r'(?:name|id)="(elektrikUretim\w*[^"]*)"', html)))
print("=== form alanlari (ilk 40) ===")
for n in names[:40]:
    print("  ", n)
print()
# lisansDurumu secenekleri (Yururlukte degeri ne?)
m = re.search(r'lisansDurumu.*?</select>', html, re.DOTALL)
if m:
    opts = re.findall(r'value="([^"]*)"[^>]*>([^<]*)<', m.group(0))
    print("=== Lisans Durumu secenekleri ===")
    for v, t in opts[:15]:
        print(f"   value={v!r} -> {t.strip()!r}")
# ViewState var mi
vs = re.search(r'name="javax\.faces\.ViewState"[^>]*value="([^"]{0,30})', html)
print("\nViewState:", "VAR" if vs else "yok")
# recaptcha
print("reCAPTCHA:", "VAR" if "g-recaptcha" in html or "recaptcha" in html.lower() else "yok")
