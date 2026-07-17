"""Kullanici manuel dogrulamasi:
 - BEYNAM: koordinati VAR -> yanlis 'yok' -> yeniden cek (beklemede).
 - Diger 6 (Gorele,Kizilca,Melen,Susehri,Semdinli Baraji,Semdinli Reg):
   gercekten koordinatsiz -> 'yok' olarak kesinlestir (tekrar deneme)."""
import sqlite3

c = sqlite3.connect('data/epdk.db')
cur = c.cursor()

BEYNAM = "ÖN/11931-23/05654"
GERCEKTEN_YOK = [
    "ÖN/9288-4/04485",   # GORELE REG VE HES
    "ÖN/7475-7/03808",   # KIZILCA REG. VE HES
    "ÖN/6467-6/03563",   # MELEN HES
    "ÖN/7239-18/03748",  # YENI SUSEHRI HES
    "ÖN/5006-16/02998",  # SEMDINLI BARAJI VE HES
    "ÖN/6558-6/03588",   # SEMDINLI REG. VE HES
]

# BEYNAM -> yeniden cek
cur.execute("""update facilities set koordinat_alindi=0, koordinat_durumu='beklemede'
    where license_id in (select id from licenses where lisans_no=?)""", (BEYNAM,))
print(f"BEYNAM -> beklemede (yeniden cekilecek): {cur.rowcount} satir")

# Diger 6 -> gercekten yok, kesinlestir
q = ",".join("?" * len(GERCEKTEN_YOK))
cur.execute(f"""update facilities set koordinat_alindi=1, koordinat_durumu='koordinat_yok_teyitli'
    where license_id in (select id from licenses where lisans_no in ({q}))""", GERCEKTEN_YOK)
print(f"6 tesis -> 'koordinat_yok_teyitli' (gercekten koordinatsiz): {cur.rowcount} satir")

c.commit()
print()
print("koordinatli:", cur.execute("select count(*) from facilities where centroid_lat is not null").fetchone()[0])
print("beklemede (yeniden cekilecek):", cur.execute("select count(*) from facilities where koordinat_alindi=0").fetchone()[0])
print("teyitli koordinatsiz:", cur.execute("select count(*) from facilities where koordinat_durumu='koordinat_yok_teyitli'").fetchone()[0])
