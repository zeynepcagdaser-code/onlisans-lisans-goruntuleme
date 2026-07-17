"""EPDK WAF/IP blogunun aktif olup olmadigini olcer. Base sayfaya hafif bir
GET atar; yanitta 'Access ... Blocked' varsa IP hala bloklu demektir."""
import sys
import urllib.request

URL = ("https://lisans.epdk.gov.tr/epvys-web/faces/pages/lisans/"
       "elektrikUretimOnLisans/elektrikUretimOnLisansOzetSorgula.xhtml")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def probe():
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read(2000).decode("utf-8", "replace")
            code = r.status
    except urllib.error.HTTPError as e:
        body = e.read(2000).decode("utf-8", "replace")
        code = e.code
    except Exception as e:
        return "HATA", str(e)[:120]
    blocked = ("Access To This Page Has Been Blocked" in body
               or ("Request ID:" in body and "IP Address:" in body))
    return ("BLOKLU" if blocked else "ACIK"), f"HTTP {code}, {len(body)}b"


if __name__ == "__main__":
    st, info = probe()
    print(f"WAF: {st}  ({info})")
    sys.exit(0 if st == "ACIK" else (2 if st == "BLOKLU" else 1))
