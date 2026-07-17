"""koordinat_durumu='yok' (0 nokta donen) tesisleri yeniden-cekilecek isaretle.
Bir sonraki turda (taze IP) yeniden denenir; gercekten bos donerse yine 'yok'
olur, koordinati varsa kurtarilir."""
import sqlite3

c = sqlite3.connect('data/epdk.db')
cur = c.cursor()

before = cur.execute("select count(*) from facilities where centroid_lat is null").fetchone()[0]
rows = cur.execute("""select id from facilities
                      where centroid_lat is null and koordinat_durumu='yok'""").fetchall()
ids = [r[0] for r in rows]
cur.executemany("""update facilities set koordinat_alindi=0, koordinat_durumu='beklemede'
                   where id=?""", [(i,) for i in ids])
c.commit()

print(f"{len(ids)} tesis 'beklemede' -> yeniden cekilecek.")
print(f"koordinatli: {cur.execute('select count(*) from facilities where centroid_lat is not null').fetchone()[0]}")
print(f"beklemede (yeniden cekilecek): {cur.execute(chr(39).join(['select count(*) from facilities where koordinat_alindi=0']))}".replace(chr(39),''), end='')
print(" ->", cur.execute("select count(*) from facilities where koordinat_alindi=0").fetchone()[0])
