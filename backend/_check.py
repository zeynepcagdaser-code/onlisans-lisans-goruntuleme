import sqlite3
c = sqlite3.connect('data/epdk.db'); cur = c.cursor()
q = lambda s: cur.execute(s).fetchall()
print('licenses:', q('select count(*) from licenses')[0][0])
print('facilities:', q('select count(*) from facilities')[0][0])
print('with_coords:', q('select count(*) from facilities where centroid_lat is not null')[0][0])
print('durum:', dict(q('select koordinat_durumu,count(*) from facilities group by koordinat_durumu')))
r = q('select durum,total_found,new_added,coords_fetched,errors,last_page from scrape_runs order by id desc limit 1')
print('run(durum,total,new,coords,err,page):', r[0])
print('--- ornek koordinatli tesisler (ad, il, kaynak, dilim, lat, lng, durum, nokta) ---')
for row in q("select tesis_adi,il,kaynak_turu,dilim_meridyeni,centroid_lat,centroid_lng,koordinat_durumu,json_array_length(polygon_wgs84) from facilities where centroid_lat is not null limit 8"):
    print(row)
print('--- log son 15 satir ---')
lg = q('select log_text from scrape_runs order by id desc limit 1')
if lg and lg[0][0]:
    print('\n'.join(lg[0][0].splitlines()[-15:]))
