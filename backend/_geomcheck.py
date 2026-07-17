import sqlite3, json
c = sqlite3.connect('data/epdk.db'); cur = c.cursor()
q = lambda s: cur.execute(s).fetchall()
# il merkezleri (kaba) - pin dogrulugu icin
IL = {'ERZINCAN':(39.75,39.5),'MUGLA':(37.2,28.4),'CANAKKALE':(40.1,26.7),'BURSA':(40.2,29.1),
      'BAYBURT':(40.25,40.2),'SINOP':(42.0,35.15),'KAHRAMANMARAS':(37.6,36.9),'ADANA':(37.3,35.3),
      'MANISA':(38.6,27.4),'IZMIR':(38.4,27.1),'ARTVIN':(41.18,41.8),'MERSIN':(36.8,34.6),'SAKARYA':(40.7,30.4)}
def norm(s):
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFKD',s) if ord(c)<128).upper()
print('--- PIN dogrulugu (il merkezine uzaklik, derece) ---')
for r in q("select tesis_adi,il,centroid_lat,centroid_lng,json_array_length(polygon_wgs84) from facilities where centroid_lat is not null order by random() limit 12"):
    ilc = IL.get(norm(r[1]))
    d = ''
    if ilc:
        d = f"il_merkezine ~{((r[2]-ilc[0])**2+(r[3]-ilc[1])**2)**0.5:.2f} derece"
    print(f"  {r[0][:24]:25s} {r[1][:10]:11s} ({r[2]:.3f},{r[3]:.3f}) np={r[4]} {d}")
# poligon yapisi: ham_koordinat_tm3'te 'Ad' kac kez '1'/'K1'e resetleniyor (alt-poligon sayisi)
print('--- ALT-POLIGON yapisi (Ad reset sayisi) ---')
for r in q("select tesis_adi, ham_koordinat_tm3 from facilities where json_array_length(polygon_wgs84)>20 limit 5"):
    pts = json.loads(r[1]) if r[1] else []
    ads = [str(p.get('ad','')).strip() for p in pts]
    resets = sum(1 for i,a in enumerate(ads) if a in ('1','K1') )
    print(f"  {r[0][:26]:27s} nokta={len(ads)} alt_poligon(reset)~={resets} ilk_ad'lar={ads[:8]}")
