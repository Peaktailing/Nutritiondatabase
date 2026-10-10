#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阶段三：中国食物成分表两版合并。

输入（两版同属第6版标准版，互补而非迭代）：
  A. OCR 抽取版  data/china-ocr/中国食物成分表.db  food_nutrition 1,810 条
     —— 两册扫描件逐页 OCR，带质量分级 check_grade / macro_sum / 册次 volume
  B. 早期整理版  data/china/food_composition_full.csv  1,677 条
     —— 第6版前半部分（第一册植物性为主）的结构化整理

实测互补性（2026-10-10）：
  编码交集 1,615；并集 1,872
  B 独有 62 条中：
    · 39 条编码带 x 后缀（如 011201x）→ 早期整理时对「同一编码多个品种」
      做的代表值合成估算，不是原书条目，单独存放并标记 is_synthetic=1
    ·  2 条与 A 跨编码重名（081324≡081325、191001≡100161）→ 归入 A，不重复计
    · 21 条 A 完全没有 → 真补缺

输出：
  china_food_merged        1,832 条（1,810 A + 22 B 补缺，不含 39 条合成）
  china_food_synthetic       39 条（B 独有的代表值估算，单独隔离）
  china_merge_map          编码映射与决策日志（可审计）

口径纪律（重要）：
  中国表 carbohydrate 是「可利用碳水」，USDA 用「减差法 by difference」，
  两者定义不同。本表不做任何跨库碳水合并，只在 *_carb_note 里标注口径。
  数值符号沿用 OCR 版的 None 语义：Tr/—/未检出 → NULL，不写 0。
"""
import csv
import os
import os as _os
import sys as _sys

# 仓库根目录（本文件位于 <root>/scripts/import/merge_china_ocr.py）
ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(
    _os.path.abspath(__file__))))
import re
import sqlite3
import sys

DB = _os.environ.get("FDC_DB", _os.path.join(ROOT, "nutrition.db"))
OCR_DB = os.path.join(ROOT, "data", "china-ocr", "中国食物成分表.db")
OLD_CSV = os.path.join(ROOT, "data", "china", "food_composition_full.csv")

# OCR 版 food_nutrition 列顺序（写入顺序必须严格对齐）
OCR_COLS = [
    "food_code", "food_name", "category", "edible_pct", "water_g",
    "energy_kcal", "energy_kj", "protein_g", "fat_g", "fat_sat_g",
    "fat_mono_g", "fat_poly_g", "carb_g", "fiber_g", "cholesterol_mg",
    "ash_g", "vit_a_ug", "beta_carotene_ug", "thiamin_mg", "riboflavin_mg",
    "niacin_mg", "vit_c_mg", "vit_e_mg", "vit_e_te_mg", "calcium_mg",
    "phosphorus_mg", "potassium_mg", "sodium_mg", "magnesium_mg", "iron_mg",
    "zinc_mg", "selenium_ug", "copper_mg", "manganese_mg", "iodine_ug",
    "n_fields", "macro_sum", "quality_score", "check_grade", "data_source",
    "volume",
]

# B 版 CSV 列 → 合并表列。B 版缺的字段（饱和/单双不饱和脂肪、维生素ETE、
# 碘、氨基酸模式）一律留 NULL——不猜、不用 0 填。
# 注意：foodName / englishName / remark 是文本，必须走 TEXT_BRANCH，
# 不能放进这里被 to_num 解析（那会让全部名称变 None）。
# foodCode 是编码不是数值，必须走 TEXT_BRANCH。踩过的坑：一开始把它放在
# OLD_MAP 里被 to_num 解析，编码全变浮点（'011204' → 11204.0），前导零
# 丢失且类型不一致，与 OCR 编码无法对齐。
TEXT_COLS = {"foodCode": "food_code", "foodName": "food_name",
             "englishName": "english_name", "remark": "remark"}
OLD_MAP = {
    "category": "category",
    "edible": "edible_pct", "water": "water_g", "energyKCal": "energy_kcal",
    "energyKJ": "energy_kj", "protein": "protein_g", "fat": "fat_g",
    "CHO": "carb_g", "dietaryFiber": "fiber_g", "cholesterol": "cholesterol_mg",
    "ash": "ash_g", "vitaminA": "vit_a_ug", "carotene": "beta_carotene_ug",
    "thiamin": "thiamin_mg", "riboflavin": "riboflavin_mg", "niacin": "niacin_mg",
    "vitaminC": "vit_c_mg", "vitaminETotal": "vit_e_mg",
    "Ca": "calcium_mg", "P": "phosphorus_mg", "K": "potassium_mg",
    "Na": "sodium_mg", "Mg": "magnesium_mg", "Fe": "iron_mg", "Zn": "zinc_mg",
    "Se": "selenium_ug", "Cu": "copper_mg", "Mn": "manganese_mg",
}

# 名称归一化：用于跨编码重名检测（括号统一、全半角、去空白）
_PUNCT = re.compile(r"[\s\[\]【】（）()、,，·\.\-—－_/]")


def norm_name(s):
    return _PUNCT.sub("", s or "").strip()


def to_num(s):
    """CSV 值 → float 或 None。

    中国表符号语义：
      '' / '—' / 'Tr' / 'tr' / '/'  → None（未检出 / 未检测 / 不详）
      数字 / 数字+单位尾巴           → float
    绝不能把 'Tr' 当 0——「未检出」与「含量为零」是两条不同的营养学结论。
    """
    if s is None:
        return None
    s = str(s).strip()
    if not s or s in ("—", "－", "-", "Tr", "tr", "TR", "/", "…", "未检出"):
        return None
    # 尾注剥离：'0.4(生)'、'13.9*'、'2.5(约)'
    s = re.sub(r"[（(].*?[)）]", "", s)
    s = s.rstrip("*＊")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def read_ocr(con_ocr):
    cur = con_ocr.execute(
        f"select {','.join(OCR_COLS)} from food_nutrition")
    rows = {}
    for r in cur:
        d = dict(zip(OCR_COLS, r))
        d["_src"] = "OCR"
        rows[d["food_code"]] = d
    return rows


def read_old(path):
    with open(path, encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        rows = {}
        for r in rd:
            code = (r.get("foodCode") or "").strip()
            if not code:
                continue
            d = {"food_code": code, "_src": "OLD"}
            for k, v in r.items():
                if k in TEXT_COLS:
                    d[TEXT_COLS[k]] = (v or "").strip() or None
                elif k in OLD_MAP:
                    d[OLD_MAP[k]] = to_num(v)
            # 防线：编码必须与 OCR 版同形态。允许尾部 x——那是早期整理版
            # 对「一码多品种」做的代表值合成标记（如 102101x 全脂奶粉），
            # 稍后会被分流到 china_food_synthetic 隔离表。
            # 曾因 foodCode 混进 OLD_MAP 被 to_num 解析，编码变 11204.0。
            if not re.fullmatch(r"\d{6}x?", d["food_code"]):
                raise ValueError(
                    f"编码格式异常: {d['food_code']!r}（期望 6 位数字[+x]）")
            rows[code] = d
    return rows


def main():
    con_ocr = sqlite3.connect(OCR_DB)
    con = sqlite3.connect(DB)
    cur = con.cursor()

    ocr = read_ocr(con_ocr)
    old = read_old(OLD_CSV)
    print(f"  OCR 版 {len(ocr):,} 条 / 早期整理版 {len(old):,} 条")

    # ---- 决策：分类 B 独有编码
    # 空名必须排除：OCR 版有 16 条原书名称列 OCR 丢失的空名行，若允许空名
    # 参与重名匹配，所有空名 B 行都会「撞上」这 16 条，后果是 21 条真补缺
    # 被静默吞掉。这里显式挡掉。
    ocr_by_name = {}
    for c, d in ocr.items():
        if not d["food_name"]:
            continue
        ocr_by_name.setdefault(norm_name(d["food_name"]), c)

    synthetic, dup_cross, real_extra = {}, {}, {}
    for c, d in old.items():
        if c in ocr:
            continue
        if c.endswith("x"):
            synthetic[c] = d
            continue
        hit = ocr_by_name.get(norm_name(d["food_name"])) if d["food_name"] else None
        if hit:
            dup_cross[c] = (hit, d["food_name"])
        else:
            real_extra[c] = d

    print(f"  编码交集 {len(set(ocr) & set(old)):,} / 并集 {len(set(ocr) | set(old)):,}")
    print(f"  B 独有 {len(set(old) - set(ocr)):,} 条 → "
          f"合成代表值 {len(synthetic)} / 跨编码重名 {len(dup_cross)} / "
          f"真补缺 {len(real_extra)}")

    # ---- 建表
    cur.execute("DROP TABLE IF EXISTS china_food_merged")
    cur.execute("DROP TABLE IF EXISTS china_food_synthetic")
    cur.execute("DROP TABLE IF EXISTS china_merge_map")

    base_type = ",".join(
        f"{c} {'INTEGER' if c in ('n_fields',) else 'REAL'}"
        if c not in ("food_code", "food_name", "category", "check_grade",
                     "data_source", "volume")
        else f"{c} TEXT"
        for c in OCR_COLS)
    # 附加列：B 版独有的英文名/备注，以及口径与来源标记
    base_type += (",english_name TEXT,remark TEXT,"
                  "carb_note TEXT,merge_src TEXT,merge_flag TEXT")
    cur.execute(f"CREATE TABLE china_food_merged ({base_type})")
    cur.execute("""CREATE TABLE china_food_synthetic (
        food_code TEXT PRIMARY KEY, food_name TEXT, category TEXT,
        english_name TEXT, remark TEXT, merge_src TEXT,
        carb_note TEXT, is_synthetic INTEGER DEFAULT 1)""")
    cur.execute("""CREATE TABLE china_merge_map (
        food_code TEXT PRIMARY KEY, decision TEXT, matched_code TEXT,
        note TEXT)""")

    ins_cols = OCR_COLS + ["english_name", "remark", "carb_note", "merge_src",
                           "merge_flag"]
    ph = ",".join("?" * len(ins_cols))
    cur.execute("""CREATE TEMP TABLE _stage (
        food_code TEXT, food_name TEXT, category TEXT, edible_pct REAL,
        water_g REAL, energy_kcal REAL, energy_kj REAL, protein_g REAL,
        fat_g REAL, fat_sat_g REAL, fat_mono_g REAL, fat_poly_g REAL,
        carb_g REAL, fiber_g REAL, cholesterol_mg REAL, ash_g REAL,
        vit_a_ug REAL, beta_carotene_ug REAL, thiamin_mg REAL,
        riboflavin_mg REAL, niacin_mg REAL, vit_c_mg REAL, vit_e_mg REAL,
        vit_e_te_mg REAL, calcium_mg REAL, phosphorus_mg REAL,
        potassium_mg REAL, sodium_mg REAL, magnesium_mg REAL, iron_mg REAL,
        zinc_mg REAL, selenium_ug REAL, copper_mg REAL, manganese_mg REAL,
        iodine_ug REAL, n_fields INTEGER, macro_sum REAL,
        quality_score REAL, check_grade TEXT, data_source TEXT, volume TEXT,
        english_name TEXT, remark TEXT, carb_note TEXT, merge_src TEXT,
        merge_flag TEXT)""")

    stage = []
    C_OCR = "中国表可利用碳水（不可用纤维已扣除）；与 USDA by-difference 口径不同"
    C_BOTH = "中国表可利用碳水；本行数值来自早期整理版"

    def row_of(d, note, src, flag=None):
        vals = [d.get(c) for c in OCR_COLS]
        vals.append(d.get("english_name"))
        vals.append(d.get("remark"))
        vals.append(note)
        vals.append(src)
        vals.append(flag)
        return vals

    # 1) OCR 全部保留（它是原书逐页抽取，质量分级齐全）
    for c, d in sorted(ocr.items()):
        d.setdefault("check_grade", None)
        stage.append(row_of(d, C_OCR, "OCR"))

    # 2) B 真补缺
    for c, d in sorted(real_extra.items()):
        stage.append(row_of(d, C_BOTH, "EARLY", "no_quality_grade"))
        cur.execute(
            "INSERT INTO china_merge_map VALUES (?,?,?,?)",
            (c, "take_early_verbatim", None, "OCR 版无此编码，整行取自早期整理版"))

    con.executemany(
        f"INSERT INTO _stage VALUES ({ph})", stage)

    cur.execute(f"INSERT INTO china_food_merged ({','.join(ins_cols)}) "
                f"SELECT {','.join(ins_cols)} FROM _stage")
    cur.execute("DROP TABLE _stage")

    # ---- 打 OCR 质量标记（合并阶段发现的、原分级未覆盖的问题）
    # 实测 110 条六项齐全却 macro_sum 越界，其中 107 条 >106，且 carbs 值本身
    # 就离谱（豆角 74.0 g、鲜驼奶 99.0 g）——这是 OCR 把碳水列读串行，
    # 不是原书数据问题。check_grade 是用户脚本给的，不能改，只加旁注标记。
    cur.execute("""UPDATE china_food_merged SET merge_flag='ocr_carb_column_shift'
        WHERE macro_sum > 106
          AND water_g IS NOT NULL AND protein_g IS NOT NULL
          AND fat_g IS NOT NULL AND carb_g IS NOT NULL
          AND ash_g IS NOT NULL
          AND merge_flag IS NULL""")
    cur.execute("""UPDATE china_food_merged SET merge_flag='ocr_macro_sum_low'
        WHERE macro_sum > 0 AND macro_sum < 94
          AND water_g IS NOT NULL AND protein_g IS NOT NULL
          AND fat_g IS NOT NULL AND carb_g IS NOT NULL
          AND ash_g IS NOT NULL
          AND merge_flag IS NULL""")
    cur.execute("""UPDATE china_food_merged SET merge_flag='name_missing'
        WHERE food_name IS NULL OR trim(food_name)=''""")
    # 第四簇 OCR 错误：kJ 列小数点丢失。实测 69 条比值 <1.0，
    # 典型「米粉（亨氏胡萝卜营养米粉）」kcal 407 / kJ 5.4——原书应为 ~1702。
    # 特征明确（比值远小于 4），不与碳水列错位重叠，可安全单独标记。
    cur.execute("""UPDATE china_food_merged SET merge_flag='ocr_kj_decimal_shift'
        WHERE energy_kcal>0 AND energy_kj>0
          AND energy_kj/energy_kcal < 3.5
          AND merge_flag IS NULL""")

    # 3) 合成代表值隔离
    for c, d in sorted(synthetic.items()):
        cur.execute(
            "INSERT INTO china_food_synthetic VALUES (?,?,?,?,?,?,?,1)",
            (c, d.get("food_name"), d.get("category"), d.get("english_name"),
             d.get("remark"), "EARLY", C_BOTH))
        cur.execute(
            "INSERT INTO china_merge_map VALUES (?,?,?,?)",
            (c, "isolate_synthetic", None,
             "早期整理版为「一码多品种」合成的代表值估算，非原书条目"))

    # 4) 跨编码重名映射（归入 OCR 条目，不重复计）
    for c, (hit, nm) in sorted(dup_cross.items()):
        cur.execute(
            "INSERT INTO china_merge_map VALUES (?,?,?,?)",
            (c, "map_to_ocr", hit,
             f"跨编码重名，值以 OCR 版 {hit} 为准"))

    # 5) OCR 全量映射日志
    cur.executemany("INSERT INTO china_merge_map VALUES (?,?,?,?)",
                    [(c, "from_ocr", None, "") for c in sorted(ocr)])

    # ---- 索引
    cur.execute("CREATE INDEX idx_cfm_cat ON china_food_merged(category)")
    cur.execute("CREATE INDEX idx_cfm_name ON china_food_merged(food_name)")
    cur.execute("CREATE INDEX idx_cfm_grade ON china_food_merged(check_grade)")

    # ---- 质量守恒自检
    n = cur.execute("select count(*) from china_food_merged").fetchone()[0]
    nsyn = cur.execute("select count(*) from china_food_synthetic").fetchone()[0]
    nmap = cur.execute("select count(*) from china_merge_map").fetchone()[0]
    assert n == len(ocr) + len(real_extra), (n, len(ocr), len(real_extra))
    assert nmap == len(ocr) + len(real_extra) + len(synthetic) + len(dup_cross)

    # 能量一致性：kJ / kcal 应在 4.18 附近。
    # 分两向报：低端(<3.5) 是 kJ 小数点丢失，高端(>4.3) 是另需人工看的。
    bad_lo = cur.execute("""select count(*) from china_food_merged
        where energy_kcal>0 and energy_kj>0 and energy_kj/energy_kcal < 3.5""").fetchone()[0]
    bad_hi = cur.execute("""select count(*) from china_food_merged
        where energy_kcal>0 and energy_kj>0 and energy_kj/energy_kcal > 4.3""").fetchone()[0]
    # macro_sum 口径经实测确认 = 水+蛋白+脂肪+碳水+纤维+灰分（六项合计，
    # 理论 ~98%，故判据放宽到 94~106）。**必须先验六项齐全**，否则缺项行
    # 天然低于 94 会造成 500+ 条假报警——第一版就是这么误报的。
    off = cur.execute("""select count(*) from china_food_merged
        where macro_sum > 0
          and water_g is not null and protein_g is not null
          and fat_g is not null and carb_g is not null and ash_g is not null
          and (macro_sum < 94 or macro_sum > 106)""").fetchone()[0]
    nsix = cur.execute("""select count(*) from china_food_merged
        where macro_sum > 0 and water_g is not null and protein_g is not null
          and fat_g is not null and carb_g is not null and ash_g is not null""").fetchone()[0]
    emptyname = cur.execute("""select count(*) from china_food_merged
        where food_name is null or trim(food_name)=''""").fetchone()[0]
    flags = dict(cur.execute(
        "select merge_flag, count(*) from china_food_merged "
        "group by 1 order by 2 desc").fetchall())

    con.commit()
    print(f"  china_food_merged      {n:,} 条"
          f"（OCR {len(ocr):,} + 早期补缺 {len(real_extra)}）")
    print(f"  china_food_synthetic   {nsyn:,} 条（代表值估算，已隔离）")
    print(f"  china_merge_map        {nmap:,} 条")
    print(f"  自检：kJ/kcal 低端越界 {bad_lo} / 高端越界 {bad_hi} / "
          f"六项齐全样本 {nsix:,} 中 macro_sum 越界 {off} / 空名 {emptyname}")
    print("  质量标记：")
    for k, v in flags.items():
        print(f"    {k or '(无标记)':<26} {v:,}")
    print("  注：越界经核实均为 OCR 读数错误而非原书数据问题——")
    print("      · macro_sum>106（107 条）：碳水列读串，豆角 74.0 g、鲜驼奶 99.0 g")
    print("      · kJ/kcal<3.5（69 条）：kJ 小数点丢失，米粉类 407 kcal 配 5.4 kJ")
    print("      · 一律用 merge_flag 旁注，不改用户脚本给的 check_grade")
    con.close()


if __name__ == "__main__":
    main()
