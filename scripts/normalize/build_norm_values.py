#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阶段二：建立「公制化长表」+ 「并排展示视图」。

严格遵循用户决策（2026-10-04）：
  · **不合并**——不做跨库食物实体匹配。各来源保持独立记录。
  · **统一公制**——所有质量类数值换算到 g / mg / μg。
  · 非质量单位（IU / kJ / pH / ORAC 等）保留原值并显式标注，不做伪换算。

产出：
  norm_value    长表事实：norm_food_id + nut_key + 数值 + 单位（公制）
  v_by_cat      按统一分类分段 × 来源 并排展示（行=分段，列=来源）
  v_browse      名称浏览视图（分类 + 来源 + 名称 + 主要指标，公制）
"""
import sqlite3
import re
import os
import os as _os
import sys as _sys

# 仓库根目录（本文件位于 <root>/scripts/normalize/build_norm_values.py）
ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(
    _os.path.abspath(__file__))))

DB = _os.environ.get("FDC_DB", _os.path.join(ROOT, "nutrition.db"))

# mg -> g 换算（统一到 g 存，显示时再按需要转 mg/μg）
# 存储策略：质量类一律存 **g**；显示层按 nutrient_master 的 unit 转出。
# 这样跨库数值可直接比较（同一 nut_key 同一单位）。
MASS_TO_G = {
    "g": 1.0, "G": 1.0, "mg": 0.001, "MG": 0.001,
    "ug": 1e-6, "\u00b5g": 1e-6, "\u03bcg": 1e-6, "mcg": 1e-6, "UG": 1e-6, "MCG": 1e-6,
    "\u00b5G": 1e-6, "\u03bcG": 1e-6,
    "ng": 1e-9,
}
# 统一后各营养素的展示单位（质量类）
DISPLAY_UNIT = {
    "water": "g", "protein": "g", "fat": "g", "saturated_fat": "g",
    "carbohydrate": "g", "fiber": "g", "sugar": "g",
    "cholesterol": "mg",
    "calcium": "mg", "phosphorus": "mg", "potassium": "mg", "sodium": "mg",
    "magnesium": "mg", "iron": "mg", "zinc": "mg", "copper": "mg", "manganese": "mg",
    "selenium": "μg",
    "vitamin_c": "mg", "vitamin_a": "μg", "vitamin_e": "mg",
    "thiamin": "mg", "riboflavin": "mg", "niacin": "mg",
    "folate": "μg", "vitamin_b12": "μg", "vitamin_d": "μg", "vitamin_k": "μg",
    "energy": "kcal",
}


def build_norm_value(con, cur):
    """从各库原始表抽取核心营养素 → norm_value（全部换算为公制）"""
    cur.execute("DROP TABLE IF EXISTS norm_value")
    cur.execute("""CREATE TABLE norm_value (
        norm_food_id INTEGER NOT NULL,
        nut_key      TEXT NOT NULL,
        value_si     REAL,          -- 统一单位（质量类=g, 能量=kcal）
        display_val  REAL,          -- 换算到展示单位
        display_unit TEXT,
        raw_value    REAL,          -- 原始值（未换算）
        raw_unit     TEXT,          -- 原始单位
        PRIMARY KEY (norm_food_id, nut_key)
    )""")
    cur.execute("CREATE INDEX idx_nv_key ON norm_value(nut_key)")

    # id 映射
    idmap = {}
    for nid, src, sid in cur.execute(
            "select norm_food_id, source, source_id from norm_food"):
        idmap[(src, sid)] = nid
    print(f"  食物 ID 映射: {len(idmap):,}")

    buf = []
    UNKNOWN_UNITS = {}

    def put(src, sid, pairs):
        nid = idmap.get((src, sid))
        if nid is None:
            return
        for nk, raw, unit in pairs:
            if raw is None:
                continue
            # 守卫：列错位时可能取到字符串标签，跳过而非崩溃
            if not isinstance(raw, (int, float)):
                continue
            du = DISPLAY_UNIT.get(nk)
            if du is None:
                continue
            # 质量类 → 先换算到 g
            if du == "kcal":
                buf.append((nid, nk, float(raw), float(raw), "kcal", raw, unit))
                continue
            f = MASS_TO_G.get(unit) or MASS_TO_G.get((unit or "").strip())
            if f is None:
                # 绝不能静默丢弃：未知单位一律记账，最后统一报出。
                # 曾经踩过的坑——单位字符串用希腊字母 μ(U+03BC) 而字典键是
                # 微符号 μ(U+00B5)，两个字符 Python 判不相等，导致中国库
                # 硒/维生素A 共 2,288 条被无声丢弃却毫无报错。
                UNKNOWN_UNITS[unit] = UNKNOWN_UNITS.get(unit, 0) + 1
                continue
            g = float(raw) * f
            # g -> 展示单位
            if du == "g":
                disp = g
            elif du == "mg":
                disp = g * 1000.0
            elif du == "μg":
                disp = g * 1_000_000.0
            else:
                continue
            buf.append((nid, nk, g, disp, du, raw, unit))

    # ---------- 中国 FCT（两版合并表；已是 g/mg/μg，仅需把 mg/μg 记对）
    # 注意：中国库 vitamin_a_ug 是 μgRAE（视黄醇活性当量），与「质量」同量纲，
    # 按 μg 入库存的是 μgRAE 数值本身；beta_carotene_ug 单列另存备查。
    #
    # saturated_fat 照样入账，但实测两版都没有值（OCR 源 1,810 行该列全空，
    # 早期整理版也无此列），所以全库 CN 的饱和脂肪一律 NULL——不是 0，
    # 「未收录」与「含量为零」在营养学上是两回事，不可混同。
    # 数据来源在 fatty_acid 附录表（972 条），需要时从那里单独取。
    for (sid, water, kcal, pro, fat, sat, cho, fib, chol, ca, p, k, na, mg,
         fe, zn, se, cu, mn, vc, va, ve, thia, rib, nia) in cur.execute("""
        select food_code, water_g, energy_kcal, protein_g, fat_g, fat_sat_g,
               carb_g, fiber_g, cholesterol_mg, calcium_mg, phosphorus_mg,
               potassium_mg, sodium_mg, magnesium_mg, iron_mg, zinc_mg,
               selenium_ug, copper_mg, manganese_mg, vit_c_mg, vit_a_ug,
               vit_e_mg, thiamin_mg, riboflavin_mg, niacin_mg
        from china_food_merged"""):
        put("CN", sid, [
            ("water", water, "g"), ("energy", kcal, "kcal"),
            ("protein", pro, "g"), ("fat", fat, "g"),
            ("saturated_fat", sat, "g"),
            ("carbohydrate", cho, "g"), ("fiber", fib, "g"),
            ("calcium", ca, "mg"), ("phosphorus", p, "mg"), ("potassium", k, "mg"),
            ("sodium", na, "mg"), ("magnesium", mg, "mg"), ("iron", fe, "mg"),
            ("zinc", zn, "mg"), ("selenium", se, "\u03bcg"), ("copper", cu, "mg"),
            ("manganese", mn, "mg"), ("vitamin_c", vc, "mg"), ("vitamin_a", va, "\u03bcg"),
            ("vitamin_e", ve, "mg"), ("thiamin", thia, "mg"),
            ("riboflavin", rib, "mg"), ("niacin", nia, "mg"),
            ("cholesterol", chol, "mg"),
        ])

    # ---------- 英国 CoFID
    # 重要：CoFID 是「每食物 × 每 sheet 一行」的长表（34,644 行但仅 2,886 个唯一
    # food_code），直接按行插入会互相覆盖。必须按 food_code 聚合。
    q = """select food_code,
                  max(water__g), max(energy_kcal__kcal), max(protein__g), max(fat__g),
                  max(carbohydrate__g), max(aoac_fibre__g), max(calcium__mg),
                  max(phosphorus__mg), max(potassium__mg), max(sodium__mg),
                  max(magnesium__mg), max(iron__mg), max(zinc__mg), max(selenium__ug),
                  max(copper__mg), max(manganese__mg), max(vitamin_c__mg),
                  max(retinol_equivalent__ug), max(vitamin_e__mg), max(thiamin__mg),
                  max(riboflavin__mg), max(niacin__mg), max(cholesterol__mg)
           from uk_cofid_food group by food_code"""
    for row in cur.execute(q).fetchall():
        put("UK", row[0], list(zip(
            ["water", "energy", "protein", "fat", "carbohydrate", "fiber",
             "calcium", "phosphorus", "potassium", "sodium", "magnesium", "iron",
             "zinc", "selenium", "copper", "manganese", "vitamin_c", "vitamin_a",
             "vitamin_e", "thiamin", "riboflavin", "niacin", "cholesterol"],
            row[1:],
            ["g", "kcal", "g", "g", "g", "g", "mg", "mg", "mg", "mg", "mg", "mg",
             "mg", "μg", "mg", "mg", "mg", "μg", "mg", "mg", "mg", "mg", "mg"])))

    # ---------- 法国 CIQUAL（__g_100g / __mg_100g / __ug_100g）
    q = """select alim_code, water__g_100g,
                  energy_regulation_eu_no_1169_2011__kcal_100g,
                  protein__g_100g, fat__g_100g, carbohydrate__g_100g, fibres__g_100g,
                  calcium__mg_100g, phosphorus__mg_100g, potassium__mg_100g,
                  sodium__mg_100g, magnesium__mg_100g, iron__mg_100g, zinc__mg_100g,
                  selenium__ug_100g, copper__mg_100g, manganese__mg_100g,
                  vitamin_c__mg_100g, vitamin_a_activity_retinol_equivalent__ug_100mg, vitamin_e__mg_100g,
                  vitamin_b1_or_thiamin__mg_100g, vitamin_b2_or_riboflavin__mg_100g, vitamin_b3_or_niacin__mg_100g,
                  cholesterol__mg_100g
           from ciqual_food"""
    for row in cur.execute(q).fetchall():
        put("FR", str(row[0]), list(zip(
            ["water", "energy", "protein", "fat", "carbohydrate", "fiber",
             "calcium", "phosphorus", "potassium", "sodium", "magnesium", "iron",
             "zinc", "selenium", "copper", "manganese", "vitamin_c", "vitamin_a",
             "vitamin_e", "thiamin", "riboflavin", "niacin", "cholesterol"],
            row[1:],
            ["g", "kcal", "g", "g", "g", "g", "mg", "mg", "mg", "mg", "mg", "mg",
             "mg", "μg", "mg", "mg", "mg", "μg", "mg", "mg", "mg", "mg", "mg"])))

    # ---------- 印尼 TKPI（列名已规范化为 _g/_mg）
    for row in cur.execute("""select food_code, protein_g, fat_g, carbohydrate_g, fiber_g,
                   calcium_mg, phosphorus_mg, iron_mg, sodium_mg, potassium_mg,
                   copper_mg, zinc_mg, thiamine_mg, riboflavin_mg, niacin_mg, vitamin_c_mg
                   from id_tkpi_food""").fetchall():
        put("ID", row[0], list(zip(
            ["protein", "fat", "carbohydrate", "fiber", "calcium", "phosphorus",
             "iron", "sodium", "potassium", "copper", "zinc", "thiamin",
             "riboflavin", "niacin", "vitamin_c"],
            row[1:],
            ["g", "g", "g", "g", "mg", "mg", "mg", "mg", "mg", "mg", "mg",
             "mg", "mg", "mg", "mg"])))
    # TKPI 能量单独处理（energy_kcal 为 INTEGER）
    for sid, e in cur.execute("select food_code, energy_kcal from id_tkpi_food"):
        put("ID", sid, [("energy", e, "kcal")])

    # ---------- 东盟 ASEAN（INFOODS 裸标签，每 100g）
    for row in cur.execute("""select food_code, energy_kcal, WATER, PROCNT, FAT, CHOAVLDF,
                   FIBTG, CA, P, NA, K, FE, CU, ZN, VITC, RETOL, THIA, RIBF, NIA
                   from asean_fcd_2014""").fetchall():
        put("ASEAN", row[0], list(zip(
            ["energy", "water", "protein", "fat", "carbohydrate", "fiber",
             "calcium", "phosphorus", "sodium", "potassium", "iron", "copper",
             "zinc", "vitamin_c", "vitamin_a", "thiamin", "riboflavin", "niacin"],
            row[1:],
            ["kcal", "g", "g", "g", "g", "g", "mg", "mg", "mg", "mg", "mg", "mg",
             "mg", "mg", "μg", "mg", "mg", "mg"])))

    # ---------- FAO 西非 WAFCT（INFOODS，每 100g）
    # 注意：WAFCT 的钠列名为 Sodium_mg（非标准 INFOODS 的 NA）
    for row in cur.execute("""select Code, ENERC, WATER, PROTCNT, FAT, CHOAVLDF, FIBTG,
                   CA, P, K, Sodium_mg, FE, CU, ZN, VITC, THIA, RIBF, NIA, CHOLE
                   from fao_wafct_food where _is_food=1""").fetchall():
        put("WAFCT", row[0], list(zip(
            ["energy", "water", "protein", "fat", "carbohydrate", "fiber",
             "calcium", "phosphorus", "sodium", "potassium", "iron", "copper",
             "zinc", "vitamin_c", "thiamin", "riboflavin", "niacin", "cholesterol"],
            row[1:],
            ["kcal", "g", "g", "g", "g", "g", "mg", "mg", "mg", "mg", "mg", "mg",
             "mg", "mg", "mg", "mg", "mg", "mg"])))

    # ---------- 日本 MEXT（INFOODS，每 100g）
    for row in cur.execute("""select food_number, "ENERC_KCAL", "WATER", "PROT-", "FAT-",
                   "CHOAVLDF-", "FIB-", "CA", "P", "NA", "K", "FE", "CU", "ZN",
                   "VITC", "RETOL", "THIA", "RIBF", "NIA", "CHOLE"
                   from jp_mext_food""").fetchall():
        put("JP", row[0], list(zip(
            ["energy", "water", "protein", "fat", "carbohydrate", "fiber",
             "calcium", "phosphorus", "sodium", "potassium", "iron", "copper",
             "zinc", "vitamin_c", "vitamin_a", "thiamin", "riboflavin", "niacin",
             "cholesterol"],
            row[1:],
            ["kcal", "g", "g", "g", "g", "g", "mg", "mg", "mg", "mg", "mg", "mg",
             "mg", "mg", "μg", "mg", "mg", "mg", "mg"])))

    # ---------- USDA（只取基础层；单位在 nutrient.unit_name）
    # 实测：直接 join 极慢，先取 id 再批量查。
    ids = [r[0] for r in cur.execute(
        "select fdc_id from food where data_type in "
        "('foundation_food','sr_legacy_food','survey_fndds_food')")]
    # nutrient_id → (nut_key, unit) 映射
    NMAP = {
        2047: ("energy", "kcal"), 1008: ("energy", "kcal"),
        1003: ("protein", "G"), 1004: ("fat", "G"), 1005: ("carbohydrate", "G"),
        1079: ("fiber", "G"),
        1087: ("calcium", "MG"), 1091: ("phosphorus", "MG"), 1092: ("potassium", "MG"),
        1093: ("sodium", "MG"), 1090: ("magnesium", "MG"),
        1089: ("iron", "MG"), 1095: ("zinc", "MG"), 1103: ("selenium", "UG"),
        1098: ("copper", "MG"), 1101: ("manganese", "MG"),
        1162: ("vitamin_c", "MG"), 1106: ("vitamin_a", "UG"),
        1109: ("vitamin_e", "MG"), 1168: ("thiamin", "MG"),
        1175: ("riboflavin", "MG"), 1167: ("niacin", "MG"),
        1253: ("cholesterol", "MG"),
    }
    CHUNK = 900
    for k in range(0, len(ids), CHUNK):
        part = ids[k:k + CHUNK]
        ph = ",".join("?" * len(part))
        for fid, nid, amt in cur.execute(
                f"select fdc_id, nutrient_id, amount from food_nutrient "
                f"where fdc_id in ({ph}) and nutrient_id in "
                f"({','.join(str(x) for x in NMAP)})", part):
            nk, un = NMAP[nid]
            put("USDA", str(fid), [(nk, amt, un)])

    cur.executemany("""INSERT OR REPLACE INTO norm_value
        (norm_food_id, nut_key, value_si, display_val, display_unit, raw_value, raw_unit)
        VALUES (?,?,?,?,?,?,?)""", buf)
    print(f"  norm_value: {len(buf):,} 条公制化数值")
    if UNKNOWN_UNITS:
        print("  ⚠ 因单位未识别而丢弃（需补 MASS_TO_G）：")
        for u, n in sorted(UNKNOWN_UNITS.items(), key=lambda x: -x[1]):
            print(f"      {u!r:<12} {n:>6} 条  [{' '.join(hex(ord(c)) for c in u or '')}]")
    return len(buf)


def build_views(con, cur):
    # ---- 并排视图：行=统一分段，列=来源，值=该分段食物数
    cur.execute("DROP VIEW IF EXISTS v_by_cat")
    cur.execute("""
        CREATE VIEW v_by_cat AS
        SELECT canon_cat, cat_cn,
               COUNT(*) AS n_total,
               SUM(source='CN')    AS cn,
               SUM(source='UK')    AS uk,
               SUM(source='FR')    AS fr,
               SUM(source='USDA')  AS usda,
               SUM(source='JP')    AS jp,
               SUM(source='ASEAN') AS asean,
               SUM(source='WAFCT') AS wafct,
               SUM(source='ID')    AS id
        FROM norm_food JOIN norm_canon_cat USING (canon_cat)
        GROUP BY canon_cat, cat_cn
        ORDER BY n_total DESC""")

    # ---- 浏览视图：分类 + 来源 + 名称 + 主要指标（公制）
    cur.execute("DROP VIEW IF EXISTS v_browse")
    cur.execute("""
        CREATE VIEW v_browse AS
        SELECT f.canon_cat, c.cat_cn, f.source, f.source_id,
               COALESCE(f.name_en, f.name_local) AS name,
               f.name_local AS name_local,
               f.state, f.state_basis,
               ROUND(f.kcal,1)  AS kcal_per100g,
               ROUND(MAX(CASE WHEN v.nut_key='protein'      THEN v.display_val END),1) AS protein_g,
               ROUND(MAX(CASE WHEN v.nut_key='fat'          THEN v.display_val END),1) AS fat_g,
               ROUND(MAX(CASE WHEN v.nut_key='carbohydrate' THEN v.display_val END),1) AS carb_g,
               ROUND(MAX(CASE WHEN v.nut_key='fiber'        THEN v.display_val END),1) AS fiber_g,
               ROUND(MAX(CASE WHEN v.nut_key='calcium'      THEN v.display_val END),1) AS calcium_mg,
               ROUND(MAX(CASE WHEN v.nut_key='iron'         THEN v.display_val END),2) AS iron_mg,
               ROUND(MAX(CASE WHEN v.nut_key='vitamin_c'    THEN v.display_val END),1) AS vitc_mg
        FROM norm_food f
        JOIN norm_canon_cat c ON c.canon_cat = f.canon_cat
        LEFT JOIN norm_value v ON v.norm_food_id = f.norm_food_id
        GROUP BY f.norm_food_id
    """)
    print("  视图已建: v_by_cat, v_browse")


def main():
    con = sqlite3.connect(DB)
    con.isolation_level = None
    cur = con.cursor()
    cur.execute("PRAGMA journal_mode=MEMORY")
    cur.execute("PRAGMA synchronous=OFF")
    cur.execute("PRAGMA cache_size=-400000")
    cur.execute("BEGIN")

    # 分类字典表（视图要用）
    cur.execute("DROP TABLE IF EXISTS norm_canon_cat")
    cur.execute("""CREATE TABLE norm_canon_cat (canon_cat TEXT PRIMARY KEY, cat_cn TEXT)""")
    CANON = [("dairy_egg", "乳蛋类"), ("meat", "肉类"), ("fish", "水产"),
             ("vegetable", "蔬菜"), ("fruit", "水果"), ("grain", "谷类"),
             ("legume", "豆类"), ("nut_seed", "坚果种子"), ("oil_fat", "油脂"),
             ("sugar", "糖类"), ("beverage", "饮料"), ("seasoning", "调味品"),
             ("snack", "零食"), ("baby", "婴幼儿"), ("other", "其他")]
    cur.executemany("INSERT INTO norm_canon_cat VALUES (?,?)", CANON)
    print(f"norm_canon_cat: {len(CANON)} 个统一分段")

    n = build_norm_value(con, cur)
    build_views(con, cur)

    cur.execute("COMMIT")
    # 统计
    for sql, lab in [("select count(*) from norm_food", "并排食物条目"),
                     ("select count(*) from norm_value", "公制化数值"),
                     ("select count(distinct nut_key) from norm_value", "覆盖营养素数")]:
        print(f"  {lab}: {cur.execute(sql).fetchone()[0]:,}")
    print("\n各来源数值覆盖:")
    for s, c in cur.execute("""select f.source, count(distinct f.norm_food_id)
                              from norm_value v join norm_food f using(norm_food_id)
                              group by f.source order by 2 desc"""):
        print(f"    {s:<8} {c:>7,}")
    con.close()


if __name__ == "__main__":
    main()
