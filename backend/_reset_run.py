import sqlite3
c = sqlite3.connect('data/epdk.db')
c.execute("update scrape_runs set durum='partial' where durum in ('scraping','waiting_captcha','running','starting')")
c.execute("update scrape_runs set last_page=1 where last_page>15")
c.commit()
print("run durumu -> partial, bozuk last_page temizlendi")
print("koordinatli tesis:", c.execute("select count(*) from facilities where centroid_lat is not null").fetchone()[0])
