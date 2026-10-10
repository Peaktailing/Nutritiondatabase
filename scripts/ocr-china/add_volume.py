# -*- coding: utf-8 -*-
"""为数据库添加 volume(册次) 字段 —— 以原始两个营养 CSV 的实际拆分为准"""
import csv, sqlite3, os, sys, json

BASE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(BASE, "pkg")
CSV1 = os.path.join(PKG, "数据表CSV", "营养成分_第一册_植物性食物.csv")
CSV2 = os.path.join(PKG, "数据表CSV", "营养成分_第二册_动物性食物.csv")
DB1 = os.path.join(PKG, "数据库", "中国食物成分表.db")
DB2 = os.path.join(PKG, "数据库", "中国食物成分表_USDA兼容版.db")

# ---------- 1. 从营养 CSV 构建 food_code -> volume 映射（硬依据） ----------
mapping = {}
dup = 0
for path, vol in [(CSV1, "第一册"), (CSV2, "第二册")]:
    with open(path, encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            code = row["食物编码"].strip()
            if code in mapping and mapping[code] != vol:
                dup += 1
                print(f"[警告] {code} 出现在两册 CSV 中，保留首见 {mapping[code]}")
            else:
                mapping[code] = vol
print(f"映射表: {len(mapping)} 个 food_code (跨册冲突 {dup})")

def prefix_volume(code):
    """退回规则: 01~07 第一册; 08~13,21 第二册;
    19 油脂类按段位: 1910xx 动物油脂→第二册, 1920xx 植物油脂→第一册;
    其余返回 None"""
    p = code[:2]
    if "01" <= p <= "07":
        return "第一册"
    if p in ("08","09","10","11","12","13","21"):
        return "第二册"
    if p == "19":
        seg = code[2:4]
        if seg == "10":
            return "第二册"   # 1910xx 动物油脂(鸭油/羊油/猪油等)
        if seg in ("20","21","22"):
            return "第一册"   # 1920xx 植物油脂通用 / 1921xx 品牌植物油 / 1922xx 品牌进口植物油
    return None

report = {}

def add_volume(conn, table, code_col, use_mapping=True, prefix_fallback=True):
    cur = conn.cursor()
    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})")]
    if "volume" not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN volume TEXT")
    rows = cur.execute(f"SELECT rowid, {code_col} FROM {table}").fetchall()
    n1 = n2 = nfx = nnone = nmiss = 0
    for rowid, code in rows:
        code = (code or "").strip()
        vol = mapping.get(code) if use_mapping else None
        if vol is None and prefix_fallback:
            vol = prefix_volume(code)
        if vol is None:
            nnone += 1
        elif vol == "第一册":
            n1 += 1
        else:
            n2 += 1
        cur.execute(f"UPDATE {table} SET volume=? WHERE rowid=?", (vol, rowid))
    # 映射覆盖不到且前缀也定不了的
    nmiss = nnone
    report[table] = dict(total=len(rows), 第一册=n1, 第二册=n2, 未定=nnone)
    print(f"[{table}] 共{len(rows)}  第一册={n1} 第二册={n2} 未定={nnone}")
    return nmiss

# ---------- 2. 主库 ----------
con = sqlite3.connect(DB1)
cur = con.cursor()
# 主表必须 100% 由 CSV 映射覆盖
tot = cur.execute("SELECT COUNT(*) FROM food_nutrition").fetchone()[0]
covered = sum(1 for (c,) in cur.execute("SELECT food_code FROM food_nutrition") if c.strip() in mapping)
print(f"主表映射覆盖: {covered}/{tot}")
assert covered == tot, "主表存在 CSV 映射覆盖不到的行, 中止!"

add_volume(con, "food_nutrition", "food_code", use_mapping=True, prefix_fallback=False)
add_volume(con, "sample_desc", "food_code")
add_volume(con, "amino_acid", "food_code")
add_volume(con, "fatty_acid", "food_code")

# meta 更新
meta_updates = {
    "record_nutrition": str(cur.execute("SELECT COUNT(*) FROM food_nutrition").fetchone()[0]),
    "record_amino_acid": str(cur.execute("SELECT COUNT(*) FROM amino_acid").fetchone()[0]),
    "record_fatty_acid": str(cur.execute("SELECT COUNT(*) FROM fatty_acid").fetchone()[0]),
    "record_sample_desc": str(cur.execute("SELECT COUNT(*) FROM sample_desc").fetchone()[0]),
    "volume_mapping": "volume字段: 第一册(植物性食物)=food_code前两位01~07及植物油脂类; 第二册(动物性食物)=08~13及动物油脂/药食两用(21); 油脂类(19)按原书实际页面归属拆分; 附录三表优先按主表映射,无法判定时留空",
    "source": "两册扫描版 OCR 抽取(第一册植物性 387页 / 第二册动物性 454页), v2 已添加 volume 册次字段",
}
for k, v in meta_updates.items():
    cur.execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))
con.commit()
con.close()
print("主库完成")

# ---------- 3. USDA 兼容版 ----------
con = sqlite3.connect(DB2)
cur = con.cursor()
add_volume(con, "food_nutrition", "food_code", use_mapping=True, prefix_fallback=False)
add_volume(con, "sample_desc", "food_code")
add_volume(con, "amino_acid", "food_code")
add_volume(con, "fatty_acid", "food_code")
# 重建 v_full 视图, 在 category 后插入 volume (幂等: 先移除已有 volume 引用)
sql = cur.execute("SELECT sql FROM sqlite_master WHERE name='v_full'").fetchone()[0]
sql = sql.replace('n.volume, ', '').replace(', n.volume', '')
assert ', n."Water"' in sql, "v_full 结构与预期不符"
new_sql = sql.replace(', n."Water"', ', n.volume, n."Water"', 1)
cur.execute("DROP VIEW v_full")
cur.execute(new_sql)
# meta 同步
for k, v in [("volume_mapping", meta_updates["volume_mapping"]),
             ("record_nutrition", meta_updates["record_nutrition"])]:
    cur.execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))
con.commit()
# 验证视图
cols = [r[1] for r in cur.execute("PRAGMA table_info(v_full)")]
print("v_full 列数:", len(cols), "| 第4列:", cols[3])
con.close()
print("USDA 版完成")

with open(os.path.join(BASE, "volume_report.json"), "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print("\n=== 汇总 ===")
print(json.dumps(report, ensure_ascii=False, indent=2))
