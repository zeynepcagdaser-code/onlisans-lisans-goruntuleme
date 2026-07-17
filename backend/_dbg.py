import sqlite3
c = sqlite3.connect('data/epdk.db'); cur = c.cursor()
lg = cur.execute('select log_text from scrape_runs order by id desc limit 1').fetchone()[0]
print("=== DBG satirlari ===")
for l in lg.splitlines():
    if 'DBG' in l:
        print(l)
print("=== ilk 6 uyari ===")
for l in [x for x in lg.splitlines() if 'uyari' in x][:6]:
    print(l)
