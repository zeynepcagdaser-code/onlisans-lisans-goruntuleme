import sqlite3
c = sqlite3.connect('data/epdk.db'); cur = c.cursor()
q = lambda s: cur.execute(s).fetchall()
print('KAYITLI VERI (guvende, silinmedi):')
print('  lisans:', q('select count(*) from licenses')[0][0])
print('  tesis:', q('select count(*) from facilities')[0][0])
print('  koordinatli tesis:', q('select count(*) from facilities where centroid_lat is not null')[0][0])
tot = q('select sum(json_array_length(polygon_wgs84)) from facilities where polygon_wgs84 is not null')[0][0]
print('  toplam koordinat noktasi:', tot)
cur.execute("update scrape_runs set durum='partial' where durum='scraping'")
c.commit()
print('  calisma durumu -> partial (devam icin hazir)')
