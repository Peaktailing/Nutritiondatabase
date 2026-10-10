#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
营养数据库整合库查询助手（命令行）。

覆盖三套数据：
  - USDA FoodData Central（接口 v_usda_*，需先跑 build_db.py 导入）
  - 中国食物成分表（第6版）      china_food_composition / v_china_foods
  - 中国居民膳食营养素参考摄入量（2023版）  china_dri_2023

用法：
  python3 query.py cnsearch 苹果            # 搜中文食物
  python3 query.py cnnutrients 061101x      # 某中文食物的全部成分
  python3 query.py dri --nutrient 铁        # 查某营养素的参考摄入量
  python3 query.py dri --nutrient 维生素A --age 18岁~
  python3 query.py search "apple"           # 搜 USDA 食品（需已导入）
  python3 query.py nutrients 1103865        # USDA 某食品营养素
  python3 query.py tables                   # 列出所有表及行数

默认数据库：/workspace/fdc/nutrition.db
"""
import sqlite3, argparse, sys, os

DB = os.environ.get("FDC_DB", "/workspace/fdc/nutrition.db")


def conn():
    if not os.path.exists(DB):
        sys.exit(f"找不到数据库 {DB}")
    return sqlite3.connect(DB)


# ------------------------------------------------------------ 中国食物成分表
CN_NUMERIC = {
    "edible": "可食部 %", "water": "水分 g", "energyKCal": "能量 kcal",
    "energyKJ": "能量 kJ", "protein": "蛋白质 g", "fat": "脂肪 g",
    "CHO": "碳水化合物 g", "dietaryFiber": "膳食纤维 g", "cholesterol": "胆固醇 mg",
    "ash": "灰分 g", "vitaminA": "维生素A μgRAE", "carotene": "胡萝卜素 μg",
    "retinol": "视黄醇 μg", "thiamin": "硫胺素 mg", "riboflavin": "核黄素 mg",
    "niacin": "烟酸 mg", "vitaminC": "维生素C mg", "vitaminETotal": "维生素E mg",
    "Ca": "钙 mg", "P": "磷 mg", "K": "钾 mg", "Na": "钠 mg", "Mg": "镁 mg",
    "Fe": "铁 mg", "Zn": "锌 mg", "Se": "硒 μg", "Cu": "铜 mg", "Mn": "锰 mg",
}


def cnsearch(q, limit=20):
    c = conn()
    rows = c.execute(
        "SELECT foodCode, category, foodName, englishName, energyKCal, protein, fat, CHO "
        "FROM china_food_composition WHERE foodName LIKE ? OR englishName LIKE ? "
        "ORDER BY foodCode LIMIT ?",
        (f"%{q}%", f"%{q}%", limit),
    ).fetchall()
    if not rows:
        print("未找到匹配食物。")
        return
    print(f"{'编码':<10} {'名称':<18} {'英文名':<24} {'kcal':>6} {'蛋白':>6} {'脂肪':>6} {'碳水':>6}")
    print("-" * 82)
    for r in rows:
        print(f"{str(r[0]):<10} {str(r[2])[:18]:<18} {str(r[3] or '')[:24]:<24} "
              f"{str(r[4] or '-'):>6} {str(r[5] or '-'):>6} {str(r[6] or '-'):>6} {str(r[7] or '-'):>6}")


def cnnutrients(code):
    c = conn()
    row = c.execute(
        "SELECT foodCode, category, foodName, englishName, remark, * "
        "FROM china_food_composition WHERE foodCode = ?", (code,)
    ).fetchone()
    if not row:
        print(f"找不到编码 {code}")
        return
    cols = [d[0] for d in c.execute("SELECT * FROM china_food_composition LIMIT 1").description]
    d = dict(zip(cols, row))
    print(f"{d['foodName']}  ({d['foodCode']})   [{d['category']}]")
    print(f"英文名: {d.get('englishName') or '-'}    备注: {d.get('remark') or '-'}")
    print("-" * 46)
    for k, label in CN_NUMERIC.items():
        v = d.get(k)
        print(f"  {label:<16} {v if v is not None else '—'}")


# ------------------------------------------------------------------- DRIs
def dri(nutrient=None, age=None, sex=None, only_verified=False):
    c = conn()
    sql = ("SELECT nutrient_cn, unit, age_group, sex, dri_type, value, value_text, "
           "verified, source FROM china_dri_2023 WHERE 1=1")
    ps = []
    if nutrient:
        sql += " AND (nutrient_cn LIKE ? OR nutrient_key LIKE ?)"
        ps += [f"%{nutrient}%", f"%{nutrient}%"]
    if age:
        sql += " AND age_group LIKE ?"
        ps.append(f"%{age}%")
    if sex:
        sql += " AND sex IN (?, 'both')"
        ps.append(sex)
    if only_verified:
        sql += " AND verified = 1"
    sql += " ORDER BY nutrient_cn, age_group, sex, dri_type"
    rows = c.execute(sql, ps).fetchall()
    if not rows:
        print("未找到匹配的参考摄入量记录。")
        return
    print(f"{'营养素':<10} {'单位':<10} {'年龄段':<16} {'性别':<8} {'类型':<6} {'值':>10}  核实")
    print("-" * 76)
    for r in rows:
        val = r[6] if r[6] else (f"{r[5]:g}" if r[5] is not None else "-")
        print(f"{r[0]:<10} {str(r[1]):<10} {str(r[2])[:16]:<16} {str(r[3]):<8} "
              f"{str(r[4]):<6} {str(val):>10}  {'✓' if r[7] else '?'}")


# ------------------------------------------------------------------ USDA
def search(q, limit=20, dtype=None):
    c = conn()
    try:
        sql = ("SELECT fdc_id, data_type, description, food_category FROM v_foods "
               "WHERE description LIKE ?")
        ps = [f"%{q}%"]
        if dtype:
            sql += " AND data_type = ?"
            ps.append(dtype)
        sql += " LIMIT ?"
        ps.append(limit)
        rows = c.execute(sql, ps).fetchall()
    except sqlite3.Error:
        print("USDA 数据尚未导入（先跑 build_db.py）。")
        return
    for r in rows:
        print(f"{str(r[0]):>10}  {str(r[1] or ''):<12}  {str(r[3] or ''):<20}  {r[2]}")


def nutrients(fdc_id):
    c = conn()
    try:
        rows = c.execute(
            "SELECT nutrient_name, amount, unit_name FROM v_food_nutrients "
            "WHERE fdc_id = ? ORDER BY nutrient_name", (fdc_id,)).fetchall()
    except sqlite3.Error:
        print("USDA 数据尚未导入。")
        return
    for name, amt, unit in rows:
        print(f"  {str(name):<34} {amt if amt is not None else '-'} {str(unit or '')}")


def cofid(q, limit=15):
    """搜索英国 CoFID 食物成分表。"""
    c = conn()
    try:
        rows = c.execute(
            "SELECT food_code, food_name, protein__g, fat__g, carbohydrate__g, energy_kcal__kcal "
            "FROM uk_cofid_food WHERE food_name LIKE ? OR description LIKE ? LIMIT ?",
            (f"%{q}%", f"%{q}%", limit)).fetchall()
    except sqlite3.Error:
        print("英国 CoFID 数据未导入。")
        return
    print(f"{'code':>8} {'名称':<46} {'蛋白':>6} {'脂肪':>6} {'碳水':>6} {'kcal':>6}")
    print("-" * 82)
    for r in rows:
        print(f"{str(r[0]):>8} {str(r[1])[:46]:<46} "
              f"{r[2] if r[2] is not None else '-':>6} {r[3] if r[3] is not None else '-':>6} "
              f"{r[4] if r[4] is not None else '-':>6} {r[5] if r[5] is not None else '-':>6}")


def mext(q, limit=15):
    """搜索日本食品標準成分表 2020。"""
    c = conn()
    try:
        rows = c.execute(
            'SELECT food_number, food_name, "ENERC_KCAL", "WATER", "PROT-", "FAT-", "CHOCDF-" '
            'FROM jp_mext_food WHERE food_name LIKE ? LIMIT ?', (f"%{q}%", limit)).fetchall()
    except sqlite3.Error:
        print("日本 MEXT 数据未导入。")
        return
    print(f"{'番号':>8} {'名称':<34} {'kcal':>6} {'水分':>6} {'蛋白':>6} {'脂肪':>6} {'碳水':>6}")
    print("-" * 78)
    for r in rows:
        print(f"{str(r[0]):>8} {str(r[1])[:34]:<34} "
              f"{r[2] if r[2] is not None else '-':>6} {r[3] if r[3] is not None else '-':>6} "
              f"{r[4] if r[4] is not None else '-':>6} {r[5] if r[5] is not None else '-':>6} "
              f"{r[6] if r[6] is not None else '-':>6}")


def tkpi(q, limit=15):
    """搜索印尼 TKPI 2017 (Tabel Komposisi Pangan Indonesia)。"""
    c = conn()
    try:
        rows = c.execute(
            "SELECT food_code, energy_kcal, protein_g, fat_g, carbohydrate_g, "
            "calcium_mg, iron_mg, vitamin_c_mg FROM id_tkpi_food "
            "WHERE food_code LIKE ? LIMIT ?", (f"%{q}%", limit)).fetchall()
    except sqlite3.Error:
        print("印尼 TKPI 数据未导入。")
        return
    print(f"{'code':>8} {'kcal':>6} {'蛋白':>6} {'脂肪':>6} {'碳水':>6} {'钙':>7} {'铁':>6} {'VC':>6}")
    print("-" * 60)
    for r in rows:
        print(f"{str(r[0]):>8} {r[1] if r[1] is not None else '-':>6} "
              f"{r[2] if r[2] is not None else '-':>6} {r[3] if r[3] is not None else '-':>6} "
              f"{r[4] if r[4] is not None else '-':>6} {r[5] if r[5] is not None else '-':>7} "
              f"{r[6] if r[6] is not None else '-':>6} {r[7] if r[7] is not None else '-':>6}")


def asean(q, limit=15):
    """搜索东盟食物成分数据库 ASEAN FCD 2014 (印尼/马来西亚/菲律宾/泰国/越南/文莱)。"""
    c = conn()
    try:
        rows = c.execute(
            "SELECT food_code, food_name, \"group\", energy_kcal, PROCNT, FAT, CHOAVLDF, CA, VITC "
            "FROM asean_fcd_2014 WHERE food_name LIKE ? OR desc LIKE ? OR \"group\" LIKE ? LIMIT ?",
            (f"%{q}%", f"%{q}%", f"%{q}%", limit)).fetchall()
    except sqlite3.Error:
        print("东盟 ASEAN FCD 数据未导入。")
        return
    print(f"{'code':>6} {'名称':<40} {'kcal':>6} {'蛋白':>5} {'脂肪':>5} {'碳水':>6} {'钙':>6} {'VC':>5}")
    print("-" * 82)
    for r in rows:
        print(f"{str(r[0]):>6} {str(r[1])[:40]:<40} "
              f"{r[3] if r[3] is not None else '-':>6} {r[4] if r[4] is not None else '-':>5} "
              f"{r[5] if r[5] is not None else '-':>5} {r[6] if r[6] is not None else '-':>6} "
              f"{r[7] if r[7] is not None else '-':>6} {r[8] if r[8] is not None else '-':>5}")


def gi(q=None, group=None, limit=30):
    """查询中国食物血糖生成指数 (GI, 第6版附录)。"""
    c = conn()
    try:
        sql = ("SELECT seq, food_group, food_name, gi_value, matched_food_code, "
               "matched_food_name, match_type FROM china_food_gi WHERE 1=1")
        ps = []
        if q:
            sql += " AND (food_name LIKE ? OR matched_food_name LIKE ?)"
            ps += [f"%{q}%", f"%{q}%"]
        if group:
            sql += " AND food_group LIKE ?"
            ps.append(f"%{group}%")
        sql += " ORDER BY seq LIMIT ?"
        ps.append(limit)
        rows = c.execute(sql, ps).fetchall()
    except sqlite3.Error:
        print("GI 数据未导入。")
        return
    if not rows:
        print("未找到匹配的 GI 记录。")
        return
    print(f"{'序':>4} {'食物':<26} {'GI':>6} {'所属组':<12} 对应成分表食物(编码)")
    print("-" * 84)
    for r in rows:
        m = f"{r[5]} ({r[4]})" if r[4] else "—"
        print(f"{r[0]:>4} {str(r[2])[:26]:<26} {r[3] if r[3] is not None else '-':>6} "
              f"{str(r[1])[:12]:<12} {m}")


def tables():
    c = conn()
    names = [r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
    print(f"共 {len(names)} 张表：")
    for nm in names:
        n = c.execute(f'SELECT COUNT(*) FROM "{nm}"').fetchone()[0]
        print(f"  {nm:<40} {n:>10} 行")


# ==================================================================
#            并排浏览层（不合并：各来源保持独立记录，只按分类+名字排列）
# ==================================================================
import unicodedata


def dw(s, width):
    """按终端显示宽度截断/补齐（中文与全角符号算 2 格，否则表头会错位）。"""
    s = "" if s is None else str(s)
    out, w = "", 0
    for ch in s:
        cw = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if w + cw > width:
            out += "…" if width > 1 else ""
            w += 1
            break
        out += ch
        w += cw
    return out + " " * (width - w)


def fnum(v, width, dec=1):
    """数字右对齐并保留小数位，缺失显示为破折号。"""
    if isinstance(v, (int, float)):
        return f"{v:>{width}.{dec}f}"
    return "—" * 1 + " " * (width - 1)


SRC_CN = {
    "CN": "中国食物成分表", "UK": "英国 CoFID", "FR": "法国 CIQUAL",
    "USDA": "USDA FDC", "JP": "日本 MEXT", "ASEAN": "东盟 FCD",
    "WAFCT": "FAO 西非", "ID": "印尼 TKPI",
}
SRC_ORDER = ["CN", "UK", "FR", "USDA", "JP", "ASEAN", "WAFCT", "ID"]
STATE_CN = {
    "raw": "生/鲜", "cooked": "熟", "processed": "加工",
    "dried_or_concentrated": "干制/浓缩", "unknown": "未标注",
}


def _has_norm():
    c = conn()
    ok = c.execute(
        "select count(*) from sqlite_master where name='norm_food'").fetchone()[0]
    if not ok:
        print("并排层尚未构建，请先运行 build_norm.py 与 build_norm_values.py。")
        sys.exit(1)
    return c


def catmap():
    """分类代码 → 中文名"""
    c = _has_norm()
    try:
        return dict(c.execute("SELECT canon_cat, cat_cn FROM norm_canon_cat"))
    except sqlite3.Error:
        sys.exit("norm_canon_cat 缺失，请重新运行 build_norm_values.py。")


def browse(cat=None, source=None, name=None, state=None, limit=25):
    """按分类 + 名字并排浏览（不合并，各来源独立成行）。

    例：
      browse --cat 蔬菜                  按统一分类浏览全部来源
      browse --cat 乳蛋类 --source CN    指定来源
      browse --name 苹果                 按名字跨来源列出
      browse --name rice --state cooked  带状态过滤
    """
    c = _has_norm()
    cats = catmap()
    where, args = [], []

    if cat:
        # 允许中文段名或英文代码
        hit = [k for k, v in cats.items() if k == cat or v == cat]
        if not hit:
            print(f"未知分类「{cat}」。可用分类：")
            for k, v in cats.items():
                n = c.execute("select count(*) from norm_food where canon_cat=?",
                              (k,)).fetchone()[0]
                print(f"  {v:<8} ({k:<12} {n:>7,} 条)")
            return
        where.append("f.canon_cat = ?")
        args.append(hit[0])

    if source:
        srcs = [s.strip().upper() for s in source.split(",")]
        bad = [s for s in srcs if s not in SRC_CN]
        if bad:
            print(f"未知来源 {bad}。可用：{', '.join(SRC_ORDER)}")
            return
        where.append("f.source in (%s)" % ",".join("?" * len(srcs)))
        args += srcs

    if name:
        where.append("(f.name_local LIKE ? OR f.name_en LIKE ? OR f.name_cn LIKE ?)")
        args += [f"%{name}%", f"%{name}%", f"%{name}%"]

    if state:
        sts = [s.strip() for s in state.split(",")]
        where.append("f.state in (%s)" % ",".join("?" * len(sts)))
        args += sts

    sql = f"""SELECT f.canon_cat, f.source, COALESCE(f.name_local, f.name_en,
                  f.source_id) AS nm, f.name_cn, f.name_en, f.state,
                  f.kcal, f.protein, f.fat, f.carb, f.source_id
           FROM norm_food f
           {'WHERE ' + ' AND '.join(where) if where else ''}
           ORDER BY
             CASE f.source {' '.join(f"WHEN '{s}' THEN {i}" for i, s in enumerate(SRC_ORDER))} END,
             f.name_local COLLATE NOCASE
           LIMIT ?"""
    rows = c.execute(sql, args + [limit]).fetchall()
    if not rows:
        print("无匹配记录。可先用 browse --cat <分类> 列出可用分类。")
        return

    cur_cat = None
    print(f"{'来源':<7}{dw('中文名', 26)}{dw('原名', 40)}{dw('状态', 9)}"
          f"{'kcal':>6}{'蛋白g':>8}{'脂肪g':>8}{'碳水g':>8}")
    print("-" * 112)
    for r in rows:
        if r[0] != cur_cat:
            cur_cat = r[0]
            if cat or len(cats) <= 3:
                print(f"\n【{cats.get(cur_cat, cur_cat)}】")
        orig = r[2] or ""
        cn = r[3] or "(未译)"
        print(f"{r[1]:<7}{dw(cn, 26)}{dw(orig, 40)}"
              f"{dw(STATE_CN.get(r[5], r[5] or '-'), 9)}"
              f"{fnum(r[6], 6, 0)}{fnum(r[7], 8)}{fnum(r[8], 8)}{fnum(r[9], 8)}")
    print(f"\n共显示 {len(rows)} 条（各来源独立记录，未做跨库合并）。")


def bycat():
    """列出统一分类分段 × 来源的分布矩阵。"""
    c = _has_norm()
    cats = catmap()
    rows = c.execute("SELECT * FROM v_by_cat").fetchall()
    short = {"CN": "中国", "UK": "英国", "FR": "法国", "USDA": "USDA",
             "JP": "日本", "ASEAN": "东盟", "WAFCT": "西非", "ID": "印尼"}
    print(dw("分段", 10) + f"{'合计':>8}" + "".join(f"{short[s]:>8}" for s in SRC_ORDER))
    print("-" * 82)
    for r in rows:
        print(dw(r[1], 10) + f"{r[2]:>8,}"
              + "".join(f"{(r[3 + i] or 0):>8,}" for i in range(8)))
    print("\n注：USDA 仅含 foundation/sr_legacy/survey 三类单食材基础层，不含品牌复合食品。")


def sidebyside(name, cat=None, limit=40):
    """同一关键词在各来源的并排对照表（按分类分组，不做实体合并）。"""
    c = _has_norm()
    cats = catmap()
    where = ["(f.name_local LIKE ? OR f.name_en LIKE ? OR f.name_cn LIKE ?)"]
    args = [f"%{name}%", f"%{name}%", f"%{name}%"]
    if cat:
        hit = [k for k, v in cats.items() if k == cat or v == cat]
        if hit:
            where.append("f.canon_cat = ?")
            args.append(hit[0])
    # 每个来源取前 N 条再合并：否则 USDA 条数一多会把其他来源全部挤出结果
    per = max(3, limit // 2)
    case = " ".join(f"WHEN '{s}' THEN {i}" for i, s in enumerate(SRC_ORDER))
    rows = []
    for src in SRC_ORDER:
        sw = where + ["f.source = ?"]
        rows += c.execute(f"""SELECT f.canon_cat, f.source,
                                    COALESCE(f.name_local, f.name_en, f.source_id),
                                    f.state, f.kcal, f.protein, f.fat, f.carb,
                                    MAX(CASE WHEN v.nut_key='calcium' THEN v.display_val END),
                                    MAX(CASE WHEN v.nut_key='iron' THEN v.display_val END),
                                    f.name_cn
                             FROM norm_food f
                             LEFT JOIN norm_value v ON v.norm_food_id = f.norm_food_id
                             WHERE {' AND '.join(sw)}
                             GROUP BY f.norm_food_id
                             ORDER BY f.name_local COLLATE NOCASE LIMIT ?""",
                        args + [src, per]).fetchall()
    rows.sort(key=lambda r: (SRC_ORDER.index(r[1]), str(r[2] or "")))
    if not rows:
        print(f"各来源均未找到「{name}」。注意不同库语言不同（CN 中文 / FR 英文 / JP 日文 / ID 印尼文），")
        print("建议用各库本地语言关键词分别检索。")
        return

    print(f"关键词「{name}」在各来源的并排结果（每行一条独立记录，未合并）\n")
    print(f"{'来源':<7}{dw('中文名', 24)}{dw('原名', 38)}{dw('分段', 10)}"
          f"{dw('状态', 9)}{'kcal':>6}{'蛋白g':>8}{'脂肪g':>8}{'碳水g':>8}{'钙mg':>8}")
    print("-" * 132)
    for r in rows:
        print(f"{r[1]:<7}{dw(r[10] or '(未译)', 24)}{dw(r[2], 38)}"
              f"{dw(cats.get(r[0], r[0]), 10)}"
              f"{dw(STATE_CN.get(r[3], r[3] or '-'), 9)}"
              f"{fnum(r[4], 6, 0)}{fnum(r[5], 8)}{fnum(r[6], 8)}{fnum(r[7], 8)}"
              f"{fnum(r[8], 8)}")
    print(f"\n共 {len(rows)} 条（各来源均衡取样）。数值均为每 100g，已统一到公制（g/mg/μg）。")


def ciqual(q, limit=15):
    c = conn()
    try:
        rows = c.execute(
            "SELECT alim_code, alim_nom_eng, alim_grp_nom_eng, "
            "protein__g_100g, fat__g_100g, carbohydrate__g_100g, calcium__mg_100g "
            "FROM ciqual_food WHERE alim_nom_eng LIKE ? LIMIT ?", (f"%{q}%", limit)).fetchall()
    except sqlite3.Error:
        print("CIQUAL 数据未导入。")
        return
    print(f"{'code':>7} {'名称':<42} {'蛋白':>6} {'脂肪':>6} {'碳水':>6} {'钙':>7}")
    print("-" * 78)
    for r in rows:
        print(f"{str(r[0]):>7} {str(r[1])[:42]:<42} "
              f"{r[3] if r[3] is not None else '-':>6} {r[4] if r[4] is not None else '-':>6} "
              f"{r[5] if r[5] is not None else '-':>6} {r[6] if r[6] is not None else '-':>7}")


def wafct(q, limit=15):
    """搜索 FAO/INFOODS 西非食物成分表。"""
    c = conn()
    try:
        rows = c.execute(
            'SELECT Code, Food_name_in_English, ENERC, PROTCNT, FAT, CA '
            'FROM fao_wafct_food WHERE _is_food=1 AND Food_name_in_English LIKE ? LIMIT ?',
            (f"%{q}%", limit)).fetchall()
    except sqlite3.Error:
        print("FAO 西非表未导入。")
        return
    print(f"{'code':>8} {'名称':<46} {'kcal':>6} {'蛋白':>6} {'钙':>6}")
    print("-" * 76)
    for r in rows:
        print(f"{str(r[0]):>8} {str(r[1])[:46]:<46} "
              f"{r[2] if r[2] is not None else '-':>6} {r[3] if r[3] is not None else '-':>6} "
              f"{r[4] if r[4] is not None else '-':>6}")


def main():
    ap = argparse.ArgumentParser(description="营养整合库查询助手")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("cnsearch", help="搜索中国食物成分表")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("cnnutrients", help="查看某中文食物的全部成分")
    p.add_argument("code", help="食物编码 foodCode")

    p = sub.add_parser("dri", help="查询膳食营养素参考摄入量(2023版)")
    p.add_argument("--nutrient")
    p.add_argument("--age")
    p.add_argument("--sex")
    p.add_argument("--verified", action="store_true", help="只显示已核实数据")

    p = sub.add_parser("search", help="搜索 USDA 食品")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--type", default=None)

    p = sub.add_parser("nutrients", help="USDA 某食品营养素")
    p.add_argument("fdc_id", type=int)

    p = sub.add_parser("ciqual", help="搜索法国 CIQUAL 食物库")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=15)

    p = sub.add_parser("wafct", help="搜索 FAO/INFOODS 西非食物成分表")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=15)

    p = sub.add_parser("cofid", help="搜索英国 CoFID 食物成分表")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=15)

    p = sub.add_parser("mext", help="搜索日本食品標準成分表 2020")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=15)

    p = sub.add_parser("tkpi", help="搜索印尼食物成分表 TKPI 2017")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=15)

    p = sub.add_parser("asean", help="搜索东盟食物成分数据库 ASEAN FCD 2014")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=15)

    p = sub.add_parser("gi", help="查询中国食物血糖生成指数 GI")
    p.add_argument("query", nargs="?", default=None)
    p.add_argument("--group", default=None)
    p.add_argument("--limit", type=int, default=30)

    sub.add_parser("tables", help="列出所有表及行数")

    # ---- 并排浏览层（不合并 + 分类/名字排列 + 公制）----
    p = sub.add_parser("browse", help="按分类/名字并排浏览各来源（不合并）")
    p.add_argument("--cat", default=None, help="统一分类（中文段名或英文代码）")
    p.add_argument("--source", default=None, help="来源，逗号分隔，如 CN,UK")
    p.add_argument("--name", default=None, help="名称关键词")
    p.add_argument("--state", default=None, help="状态，逗号分隔，如 raw,cooked")
    p.add_argument("--limit", type=int, default=25)

    sub.add_parser("bycat", help="统一分类分段 × 来源 分布矩阵")

    p = sub.add_parser("side", help="某关键词在各来源的并排对照（每 100g，公制）")
    p.add_argument("name")
    p.add_argument("--cat", default=None)
    p.add_argument("--limit", type=int, default=40)

    a = ap.parse_args()
    if a.cmd == "cnsearch":
        cnsearch(a.query, a.limit)
    elif a.cmd == "cnnutrients":
        cnnutrients(a.code)
    elif a.cmd == "dri":
        dri(a.nutrient, a.age, a.sex, a.verified)
    elif a.cmd == "ciqual":
        ciqual(a.query, a.limit)
    elif a.cmd == "wafct":
        wafct(a.query, a.limit)
    elif a.cmd == "cofid":
        cofid(a.query, a.limit)
    elif a.cmd == "mext":
        mext(a.query, a.limit)
    elif a.cmd == "tkpi":
        tkpi(a.query, a.limit)
    elif a.cmd == "asean":
        asean(a.query, a.limit)
    elif a.cmd == "gi":
        gi(a.query, a.group, a.limit)
    elif a.cmd == "browse":
        browse(a.cat, a.source, a.name, a.state, a.limit)
    elif a.cmd == "bycat":
        bycat()
    elif a.cmd == "side":
        sidebyside(a.name, a.cat, a.limit)
    elif a.cmd == "search":
        search(a.query, a.limit, a.type)
    elif a.cmd == "nutrients":
        nutrients(a.fdc_id)
    elif a.cmd == "tables":
        tables()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
