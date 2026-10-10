#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建「中国食物成分表（第6版）+ 中国居民膳食营养素参考摄入量（2023版）」数据库。

产物：
  1) 表 china_food_composition —— 中国食物成分表（1677 条，36 字段）
  2) 表 china_dri_2023        —— 2023 版 DRIs（EAR/RNI/AI/UL/AMDR），逐行标注来源与核实状态
  3) 视图 v_china_foods       —— 中文食物 + 英文名（便于与 USDA 库对照）
  4) 文件 dri_2023.csv        —— DRIs 的纯文本副本，便于人工审阅/修订

DRIs 数据说明（重要）：
  2023 版 DRIs 官方未提供机读下载，本文件的数据分两类来源，用 verified 字段区分：
    verified=1  来自《中国居民膳食营养素参考摄入量（2023版）》原书表格（人民卫生出版社）
                或中国营养学会公开发布的参考摄入量表 —— 已核实
    verified=0  来自社区整理的结构化数据集（已交叉核对，但未经原书逐项核实）
  已知版本混淆坑：维生素A 800/700、铁 女性20mg 是 **2013 版** 数值，
  2023 版为 770/660、18mg —— 本文件已按 2023 版修正。
"""
import os
import os as _os
import sys as _sys

# 仓库根目录（本文件位于 <root>/scripts/import/build_cn.py）
ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(
    _os.path.abspath(__file__))))
import sqlite3, csv, os, sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CN_CSV = os.path.join(BASE, "china", "food_composition_full.csv")
DB = os.environ.get("FDC_DB", os.path.join(BASE, "nutrition.db"))
DRI_CSV = os.path.join(BASE, "china", "dri_2023.csv")

# ---------------------------------------------------------------- 营养素字典
# G2Bent 结构化数据集使用的 key -> (中文名, 单位)
NUTRIENTS = {
    "energy":       ("能量", "kcal/d"),
    "protein":      ("蛋白质", "g/d"),
    "fat":          ("脂肪", "%E"),
    "carbohydrate": ("碳水化合物", "%E"),
    "fiber":        ("膳食纤维", "g/d"),
    "calcium":      ("钙", "mg/d"),
    "phosphorus":   ("磷", "mg/d"),
    "potassium":    ("钾", "mg/d"),
    "sodium":       ("钠", "mg/d"),
    "magnesium":    ("镁", "mg/d"),
    "iron":         ("铁", "mg/d"),
    "zinc":         ("锌", "mg/d"),
    "selenium":     ("硒", "μg/d"),
    "copper":       ("铜", "mg/d"),
    "manganese":    ("锰", "mg/d"),
    "iodine":       ("碘", "μg/d"),
    "vitA":         ("维生素A", "μgRAE/d"),
    "vitD":         ("维生素D", "μg/d"),
    "vitE":         ("维生素E", "mg α-TE/d"),
    "vitK":         ("维生素K", "μg/d"),
    "vitB1":        ("维生素B1", "mg/d"),
    "vitB2":        ("维生素B2", "mg/d"),
    "vitB6":        ("维生素B6", "mg/d"),
    "vitB12":       ("维生素B12", "μg/d"),
    "niacin":       ("烟酸", "mgNE/d"),
    "folate":       ("叶酸", "μgDFE/d"),
    "pantothenic":  ("泛酸", "mg/d"),
    "choline":      ("胆碱", "mg/d"),
    "vitC":         ("维生素C", "mg/d"),
    "cholesterol":  ("胆固醇", "mg/d"),
    "water":        ("水", "mL/d"),
}

# ---------------------------------------------- 原书/官方核实数据 (verified=1)
# 维生素A —— 原书 表11-1-1 中国居民膳食维生素A参考摄入量（2023版）
# (年龄段, EAR男, EAR女, RNI男, RNI女, UL)  UL 单位 μg/d
VA_TABLE = [
    ("1岁~",   250, 240, 340, 330, 700),
    ("4岁~",   280, 270, 390, 380, 1000),
    ("7岁~",   300, 280, 430, 390, 1300),
    ("9岁~",   400, 380, 560, 540, 1800),
    ("12岁~",  560, 520, 780, 730, 2400),
    ("15岁~",  580, 480, 810, 670, 2800),
    ("18岁~",  550, 470, 770, 660, 3000),
    ("30岁~",  550, 470, 770, 660, 3000),
    ("50岁~",  540, 470, 750, 660, 3000),
    ("65岁~",  520, 460, 730, 640, 3000),
    ("75岁~",  500, 430, 710, 600, 3000),
]
# 铁 —— 原书 表10-1-1 中国居民膳食铁参考摄入量（2023版），单位 mg/d
IRON_TABLE = [
    ("0.5岁~", 7,  7,  10, 10, None),
    ("1岁~",   7,  7,  10, 10, 25),
    ("4岁~",   7,  7,  10, 10, 30),
    ("7岁~",   9,  9,  12, 12, 35),
    ("9岁~",   12, 12, 16, 16, 35),
    ("12岁~",  12, 14, 16, 18, 40),
    ("15岁~",  12, 14, 16, 18, 40),
    ("18岁~",  9,  12, 12, 18, 42),
    ("30岁~",  9,  12, 12, 18, 42),
    ("65岁~",  9,  8,  12, 10, 42),
    ("75岁~",  9,  8,  12, 10, 42),
]
# 碘 —— 中国营养学会《中国居民膳食营养素参考摄入量（2023版）》发布值，单位 μg/d
# (年龄段, EAR, RNI, UL)
IODINE_TABLE = [
    ("0岁~",   None, 85,  None),
    ("0.5岁~", None, 115, None),
    ("1岁~",   65,   90,  None),
    ("4岁~",   65,   90,  200),
    ("7岁~",   65,   90,  250),
    ("12岁~",  75,   110, 300),
    ("15岁~",  85,   120, 500),
    ("18岁~",  85,   120, 600),
    ("孕妇",   160,  230, 500),
    ("乳母",   170,  240, 500),
]

# ------------------------------------------------ 社区整理数据 (verified=0)
# 来自 G2Bent/clinical-nutrition-calculator (标注"中国居民膳食营养素参考摄入量 2023 版")
COMMUNITY_GROUPS = [
    ("成年通用", None, "18岁以上", {
        "energy": {"rni": 2000}, "protein": {"rni": 65}, "fiber": {"ai": 25},
        "calcium": {"rni": 800, "ul": 2000}, "phosphorus": {"rni": 720, "ul": 3500},
        "potassium": {"ai": 2000}, "sodium": {"ai": 1500, "ul": 2000},
        "magnesium": {"rni": 330}, "iron": {"rni": 12, "ul": 42},
        "zinc": {"rni": 11, "ul": 40}, "selenium": {"rni": 60, "ul": 400},
        "copper": {"rni": 0.8, "ul": 8}, "manganese": {"ai": 4.5, "ul": 11},
        "iodine": {"rni": 120, "ul": 600}, "vitA": {"rni": 770, "ul": 3000},
        "vitD": {"rni": 10, "ul": 50}, "vitE": {"ai": 14, "ul": 700},
        "vitK": {"ai": 80}, "vitB1": {"rni": 1.4}, "vitB2": {"rni": 1.4},
        "vitB6": {"rni": 1.4, "ul": 60}, "vitB12": {"rni": 2.4},
        "niacin": {"rni": 14, "ul": 35}, "folate": {"rni": 400, "ul": 1000},
        "pantothenic": {"ai": 5}, "choline": {"ai": 450, "ul": 3000},
        "vitC": {"rni": 100, "ul": 2000}, "cholesterol": {"ul": 300},
    }),
    ("男 18-49岁", "male", "18-49岁", {
        "energy": {"rni": 2250}, "protein": {"rni": 65},
        "calcium": {"rni": 800, "ul": 2000}, "iron": {"rni": 12, "ul": 42},
        "zinc": {"rni": 12, "ul": 40}, "vitA": {"rni": 770, "ul": 3000},
        "vitB1": {"rni": 1.4}, "vitB2": {"rni": 1.4},
        "vitC": {"rni": 100, "ul": 2000},
    }),
    ("男 50-64岁", "male", "50-64岁", {
        "energy": {"rni": 2100}, "protein": {"rni": 65},
        "calcium": {"rni": 800, "ul": 2000}, "iron": {"rni": 12, "ul": 42},
        "zinc": {"rni": 12, "ul": 40}, "vitD": {"rni": 10, "ul": 50},
    }),
    ("男 65岁及以上", "male", "65岁及以上", {
        "energy": {"rni": 2050}, "protein": {"rni": 72},
        "calcium": {"rni": 800, "ul": 2000}, "vitD": {"rni": 15, "ul": 50},
        "sodium": {"ai": 1400, "ul": 2000},
    }),
    ("女 18-49岁", "female", "18-49岁", {
        "energy": {"rni": 1800}, "protein": {"rni": 55},
        "calcium": {"rni": 800, "ul": 2000}, "iron": {"rni": 18, "ul": 42},
        "zinc": {"rni": 8.5, "ul": 40}, "vitA": {"rni": 660, "ul": 3000},
        "vitB1": {"rni": 1.2}, "vitB2": {"rni": 1.2},
        "vitC": {"rni": 100, "ul": 2000},
    }),
    ("女 50-64岁", "female", "50-64岁", {
        "energy": {"rni": 1750}, "protein": {"rni": 55},
        "calcium": {"rni": 800, "ul": 2000}, "iron": {"rni": 10, "ul": 42},
        "vitD": {"rni": 10, "ul": 50},
    }),
    ("女 65岁及以上", "female", "65岁及以上", {
        "energy": {"rni": 1700}, "protein": {"rni": 62},
        "calcium": {"rni": 800, "ul": 2000}, "vitD": {"rni": 15, "ul": 50},
        "sodium": {"ai": 1400, "ul": 2000},
    }),
]

# 宏量营养素可接受范围 AMDR 等（2023版，社区整理并已与公开资料交叉核对）
AMDR_ROWS = [
    ("fat", "脂肪", "%E", "成年通用", None, "AMDR", None, "20-30",
     "脂肪供能比 20%-30%E；饱和脂肪酸 <10%E；n-6 PUFA 2.5%-9%E；n-3 PUFA 0.5%-2.0%E"),
    ("carbohydrate", "碳水化合物", "%E", "成年通用", None, "AMDR", None, "50-65",
     "碳水化合物供能比 50%-65%E；添加糖 <10%E"),
    ("fiber", "膳食纤维", "g/d", "成年通用", None, "AI", 25, None,
     "成人 AI 25-30 g/d（中国居民膳食指南2022 建议 25-30 g/d）"),
    ("protein", "蛋白质", "g/d", "孕中期", "female", "RNI", 70, None,
     "孕中期在成年女性 55g 基础上 +15g"),
    ("protein", "蛋白质", "g/d", "孕晚期", "female", "RNI", 85, None,
     "孕晚期在成年女性 55g 基础上 +30g"),
    ("protein", "蛋白质", "g/d", "乳母", "female", "RNI", 80, None,
     "乳母在成年女性 55g 基础上 +25g"),
    ("energy", "能量", "kcal/d", "孕中期", "female", "EER", 300, None,
     "孕中期能量在成年女性基础上 +300 kcal/d"),
    ("energy", "能量", "kcal/d", "孕晚期", "female", "EER", 450, None,
     "孕晚期能量 +450 kcal/d"),
    ("energy", "能量", "kcal/d", "乳母", "female", "EER", 500, None,
     "乳母能量 +500 kcal/d"),
    ("vitamin_a", "维生素A", "μgRAE/d", "孕早期", "female", "RNI", 660, None,
     "原书增量 +0，绝对值与育龄女性相同（660）"),
    ("vitamin_a", "维生素A", "μgRAE/d", "孕中期/孕晚期", "female", "RNI", 730, None,
     "原书增量 EAR +50、RNI +70，绝对值 660+70=730"),
    ("vitamin_a", "维生素A", "μgRAE/d", "乳母", "female", "RNI", 1260, None,
     "原书增量 EAR +400、RNI +600，绝对值 660+600=1260"),
    ("iron", "铁", "mg/d", "孕早期", "female", "RNI", 18, None,
     "原书：+0，即与育龄女性相同（18 mg/d）"),
    ("iron", "铁", "mg/d", "孕中期", "female", "RNI", 25, None, "原书：+7，18+7=25"),
    ("iron", "铁", "mg/d", "孕晚期", "female", "RNI", 29, None, "原书：+11，18+11=29"),
    ("iron", "铁", "mg/d", "乳母", "female", "RNI", 24, None, "原书：+6，18+6=24"),
    ("folate", "叶酸", "μgDFE/d", "孕妇", "female", "RNI", 600, None, "成人 400；孕妇 600"),
    ("folate", "叶酸", "μgDFE/d", "乳母", "female", "RNI", 550, None, "乳母 550"),
    ("vitamin_c", "维生素C", "mg/d", "孕妇", "female", "RNI", 115, None, "成人 100；孕妇 115"),
    ("vitamin_c", "维生素C", "mg/d", "乳母", "female", "RNI", 150, None, "乳母 150"),
    ("water", "水", "mL/d", "成年通用", None, "AI", 1500, None,
     "饮水 AI 约 1500-1700 mL/d（不含食物水分）；总水约 2700-3000 mL/d"),
]


def build_dri_rows():
    """返回 DRI 表的所有行。"""
    rows = []  # (key, cn, unit, age_group, sex, dri_type, value, value_text, source, verified, note)

    def add(key, cn, unit, age, sex, dtype, val, vtext, src, verified, note=""):
        rows.append((key, cn, unit, age, sex, dtype, val, vtext, src, verified, note))

    src_book = "《中国居民膳食营养素参考摄入量（2023版）》原书表格"
    src_cns = "中国营养学会《DRIs（2023版）》发布值"
    src_com = "社区整理数据集（G2Bent/clinical-nutrition-calculator，标注 2023 版）"

    # ---- 维生素A（原书 表11-1-1，已核实）----
    add("vitamin_a", "维生素A", "μgRAE/d", "0岁~", "both", "AI", 300, None, src_book, 1)
    add("vitamin_a", "维生素A", "μgRAE/d", "0.5岁~", "both", "AI", 350, None, src_book, 1)
    for age, em, ef, rm, rf, ul in VA_TABLE:
        add("vitamin_a", "维生素A", "μgRAE/d", age, "male", "EAR", em, None, src_book, 1)
        add("vitamin_a", "维生素A", "μgRAE/d", age, "female", "EAR", ef, None, src_book, 1)
        add("vitamin_a", "维生素A", "μgRAE/d", age, "male", "RNI", rm, None, src_book, 1)
        add("vitamin_a", "维生素A", "μgRAE/d", age, "female", "RNI", rf, None, src_book, 1)
        add("vitamin_a", "维生素A", "μg/d", age, "both", "UL", ul, None, src_book, 1,
            "UL 不包括来自膳食维生素A原类胡萝卜素的 RAE")
    for age in ("0岁~", "0.5岁~"):
        add("vitamin_a", "维生素A", "μg/d", age, "both", "UL", 600, None, src_book, 1)
    add("vitamin_a", "维生素A", "μg/d", "孕早期", "female", "UL", 3000, None, src_book, 1)
    add("vitamin_a", "维生素A", "μg/d", "孕中期/孕晚期", "female", "UL", 3000, None, src_book, 1)
    add("vitamin_a", "维生素A", "μg/d", "乳母", "female", "UL", 3000, None, src_book, 1)

    # ---- 铁（原书 表10-1-1，已核实）----
    add("iron", "铁", "mg/d", "0岁~", "both", "AI", 0.3, None, src_book, 1)
    for age, em, ef, rm, rf, ul in IRON_TABLE:
        add("iron", "铁", "mg/d", age, "male", "EAR", em, None, src_book, 1)
        add("iron", "铁", "mg/d", age, "female", "EAR", ef, None, src_book, 1)
        add("iron", "铁", "mg/d", age, "male", "RNI", rm, None, src_book, 1)
        add("iron", "铁", "mg/d", age, "female", "RNI", rf, None, src_book, 1)
        if ul is not None:
            add("iron", "铁", "mg/d", age, "both", "UL", ul, None, src_book, 1)
    # 50 岁女性分有无月经
    add("iron", "铁", "mg/d", "50岁~", "male", "EAR", 9, None, src_book, 1)
    add("iron", "铁", "mg/d", "50岁~", "male", "RNI", 12, None, src_book, 1)
    add("iron", "铁", "mg/d", "50岁~（无月经）", "female", "EAR", 8, None, src_book, 1)
    add("iron", "铁", "mg/d", "50岁~（无月经）", "female", "RNI", 10, None, src_book, 1)
    add("iron", "铁", "mg/d", "50岁~（有月经）", "female", "EAR", 12, None, src_book, 1,
        "仍有月经者与 30~49 岁相同")
    add("iron", "铁", "mg/d", "50岁~（有月经）", "female", "RNI", 18, None, src_book, 1)
    add("iron", "铁", "mg/d", "50岁~", "both", "UL", 42, None, src_book, 1)

    # ---- 碘（中国营养学会 2023 版发布值，已核实）----
    for age, ear, rni, ul in IODINE_TABLE:
        if ear is not None:
            add("iodine", "碘", "μg/d", age, "both", "EAR", ear, None, src_cns, 1)
        if rni is not None:
            dtype = "AI" if ear is None else "RNI"
            add("iodine", "碘", "μg/d", age, "both", dtype, rni, None, src_cns, 1)
        if ul is not None:
            add("iodine", "碘", "μg/d", age, "both", "UL", ul, None, src_cns, 1)

    # ---- 社区整理的分人群数据（verified=0）----
    for label, sex, age, vals in COMMUNITY_GROUPS:
        for key, dv in vals.items():
            cn, unit = NUTRIENTS.get(key, (key, ""))
            for dtype, val in dv.items():
                if val is None:
                    continue
                add(key, cn, unit, label, sex or "both", dtype.upper(), val, None, src_com, 0)

    # ---- AMDR 与特殊人群增量 ----
    for key, cn, unit, age, sex, dtype, val, vtext, note in AMDR_ROWS:
        src = src_book if "原书" in (note or "") else src_com
        verified = 1 if "原书" in (note or "") else 0
        add(key, cn, unit, age, sex or "both", dtype, val, vtext, src, verified, note)

    return rows


NUMERIC_COLS_HINT = {
    "edible", "water", "energyKCal", "energyKJ", "protein", "fat", "CHO",
    "dietaryFiber", "cholesterol", "ash", "vitaminA", "carotene", "retinol",
    "thiamin", "riboflavin", "niacin", "vitaminC", "vitaminETotal", "vitaminE1",
    "vitaminE2", "vitaminE3", "Ca", "P", "K", "Na", "Mg", "Fe", "Zn", "Se",
    "Cu", "Mn",
}


def import_food_composition(cur):
    """导入中国食物成分表 CSV。'—' / 'Tr' / 空 均记为 NULL。"""
    with open(CN_CSV, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        header = [c.strip().strip('"') for c in next(r)]
        cols = [c.replace("-", "_").replace(" ", "_") for c in header]
        coldefs = ", ".join(f'"{c}" {"REAL" if h in NUMERIC_COLS_HINT else "TEXT"}'
                            for c, h in zip(cols, header))
        cur.execute('DROP TABLE IF EXISTS china_food_composition')
        cur.execute(f'CREATE TABLE china_food_composition ({coldefs})')
        collist = ", ".join(f'"{c}"' for c in cols)
        ph = ", ".join("?" for _ in cols)
        insert = f'INSERT INTO china_food_composition ({collist}) VALUES ({ph})'
        batch, total = [], 0
        for row in r:
            if not row:
                continue
            vals = []
            for c, h, v in zip(cols, header, row):
                v = (v or "").strip()
                if h in NUMERIC_COLS_HINT:
                    if v in ("", "—", "-", "Tr", "tr", "…"):
                        vals.append(None)
                    else:
                        try:
                            vals.append(float(v))
                        except ValueError:
                            vals.append(None)
                else:
                    vals.append(v if v not in ("—", "-") else None)
            batch.append(vals)
            total += 1
            if len(batch) >= 20000:
                cur.executemany(insert, batch)
                batch = []
        if batch:
            cur.executemany(insert, batch)
    cur.execute('CREATE INDEX IF NOT EXISTS idx_cn_foodcode '
                'ON china_food_composition("foodCode")')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_cn_name '
                'ON china_food_composition("foodName")')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_cn_category '
                'ON china_food_composition("category")')
    return total, len(cols)


def main():
    if not os.path.exists(CN_CSV):
        sys.exit(f"找不到 {CN_CSV}")
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("PRAGMA synchronous=OFF")

    n, ncols = import_food_composition(cur)
    print(f"china_food_composition: {n} 条, {ncols} 列")

    cur.execute('DROP TABLE IF EXISTS china_dri_2023')
    cur.execute("""
        CREATE TABLE china_dri_2023 (
            nutrient_key TEXT, nutrient_cn TEXT, unit TEXT,
            age_group TEXT, sex TEXT, dri_type TEXT,
            value REAL, value_text TEXT,
            source TEXT, verified INTEGER, note TEXT
        )""")
    rows = build_dri_rows()
    cur.executemany(
        'INSERT INTO china_dri_2023 (nutrient_key, nutrient_cn, unit, age_group, sex,'
        ' dri_type, value, value_text, source, verified, note) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
        rows)
    cur.execute('CREATE INDEX IF NOT EXISTS idx_dri_nutrient ON china_dri_2023(nutrient_cn)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_dri_group ON china_dri_2023(age_group, sex)')

    # 视图
    cur.execute("""
        CREATE VIEW IF NOT EXISTS v_china_foods AS
        SELECT foodCode, category, foodName, englishName,
               energyKCal, energyKJ, protein, fat, CHO, dietaryFiber,
               Ca, Fe, Zn, vitaminA, vitaminC
        FROM china_food_composition""")

    conn.commit()

    # 导出 CSV 副本便于审阅
    os.makedirs(os.path.dirname(DRI_CSV), exist_ok=True)
    with open(DRI_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["nutrient_key", "nutrient_cn", "unit", "age_group", "sex",
                    "dri_type", "value", "value_text", "source", "verified", "note"])
        w.writerows(rows)

    v1 = sum(1 for r in rows if r[9] == 1)
    print(f"china_dri_2023: {len(rows)} 行（已核实 {v1} 行 / 待核验 {len(rows)-v1} 行）")
    print(f"DRIs CSV 副本: {DRI_CSV}")
    print(f"DONE -> {DB}")
    conn.close()


if __name__ == "__main__":
    main()
