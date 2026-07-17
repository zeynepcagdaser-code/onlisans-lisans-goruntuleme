"""BAGIMSIZ dogrulama: scraper'dan ayri, temiz bir istemciyle endpoint'e
art arda POST atar ve WAF engelleme sayfasi donuyor mu diye bakar.
GET geciyor ama POST'lar bloklaniyorsa -> bu bir WAF kurali (kanit)."""
import urllib.request
import urllib.error

URL = ("https://lisans.epdk.gov.tr/epvys-web/faces/pages/lisans/"
       "elektrikUretimOnLisans/elektrikUretimOnLisansOzetSorgula.xhtml")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Faces-Request": "partial/ajax",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": URL,
}
# Koordinat AJAX'ina benzer minimal govde (ViewState gecersiz; onemli degil,
# cunku WAF uygulamadan ONCE devrede -> pattern'i gorurse bloklar).
BODY = ("javax.faces.partial.ajax=true&javax.faces.source=elektrikKoordinatViewDataTable"
        "&elektrikKoordinatViewDataTable_pagination=true"
        "&elektrikKoordinatViewDataTable_first=0"
        "&javax.faces.ViewState=test").encode()


def one():
    req = urllib.request.Request(URL, data=BODY, headers=HEADERS, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read(1200).decode("utf-8", "replace")
            code = r.status
    except urllib.error.HTTPError as e:
        body = e.read(1200).decode("utf-8", "replace")
        code = e.code
    except Exception as e:
        return "HATA", str(e)[:80]
    blocked = ("Access To This Page Has Been Blocked" in body
               or ("Request ID:" in body and "IP Address:" in body))
    snippet = body[:70].replace("\n", " ")
    return ("BLOKLU" if blocked else "app-yanit"), f"HTTP {code} | {snippet}"


if __name__ == "__main__":
    print("10 hizli POST gonderiliyor (scraper'dan bagimsiz)...")
    blok = 0
    for i in range(10):
        st, info = one()
        if st == "BLOKLU":
            blok += 1
        print(f"  POST {i+1}: {st}  ({info})")
    print(f"\nSONUC: {blok}/10 POST -> WAF engelleme sayfasi dondu.")
