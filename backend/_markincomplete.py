"""Eksik noktali 2 tesisi yeniden-cekilecek isaretle."""
import sqlite3
c = sqlite3.connect('data/epdk.db'); cur = c.cursor()
targets = ["G3-%ANKIRI-2-3%", "KARA%SMA%LLER%"]
for t in targets:
    rows = cur.execute("select id, tesis_adi from facilities where tesis_adi like ?", (t,)).fetchall()
    for fid, adi in rows:
        cur.execute("""update facilities set koordinat_alindi=0, koordinat_durumu='beklemede',
                       polygon_wgs84=NULL, ham_koordinat_tm3=NULL, centroid_lat=NULL,
                       centroid_lng=NULL where id=?""", (fid,))
        print("isaretlendi (yeniden cekilecek):", adi)
c.commit()
print("koordinatli kalan:", cur.execute("select count(*) from facilities where centroid_lat is not null").fetchone()[0])
