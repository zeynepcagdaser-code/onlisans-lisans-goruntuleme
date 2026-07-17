import sqlite3, json, re
c = sqlite3.connect('data/epdk.db'); cur = c.cursor()
for like in ["ORHANLI 1 JES", "NENEHATUN", "OKUZDERE", "MELET", "AYAZMA"]:
    r = cur.execute("select tesis_adi, ham_koordinat_tm3 from facilities where tesis_adi like ?",
                    (f"%{like}%",)).fetchone()
    if not r:
        # ASCII-insensitive dene
        r = cur.execute("select tesis_adi, ham_koordinat_tm3 from facilities "
                        "where upper(tesis_adi) like ?", (f"%{like[:5]}%",)).fetchone()
    if not r or not r[1]:
        print(f"{like}: bulunamadi"); continue
    pts = json.loads(r[1])
    ads = [str(p.get('ad', '')).strip() for p in pts]
    nums = [int(m.group(1)) if (m := re.search(r'(\d+)\s*$', a)) else None for a in ads]
    valid = [x for x in nums if x is not None]
    print(f"\n=== {r[0][:40]} (nokta={len(pts)}) ===")
    print(f"  ilk 25 ad: {ads[:25]}")
    print(f"  min={min(valid) if valid else '-'} max={max(valid) if valid else '-'} "
          f"benzersiz={len(set(valid))} | None_ad={nums.count(None)}")
    # prefix cesitleri
    prefixes = set(re.sub(r'\d+\s*$', '', a).strip() for a in ads)
    print(f"  prefix'ler: {sorted(prefixes)[:10]}")
    # kac kez 1'e reset
    resets = sum(1 for x in valid if x == 1)
    print(f"  '1'e reset sayisi: {resets}")
