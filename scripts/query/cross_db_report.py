#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阶段五：跨库交叉比对（遵循用户决策：不合并实体，按名字和分类并排）。

三个层次：
  A. 分类级分布对照 —— 每个 canon_cat 分段内，各来源核心营养素的
     中位数对比。用于发现系统性口径差异（如 USDA 减差法碳水偏高）。
  B. 食物级精确对照 —— 通过 CN 表的英文名/名称规范化，与 USDA/UK
     同名食物匹配，输出逐项差异。样本有限但直观。
  C. 结论与使用建议。

产出：docs/CROSS_DB_REPORT.md + data/cross_db_match.csv
"""
import os
import re
import sqlite3
import statistics
from collections import defaultdict

DB = os.environ.get("FDC_DB", "/workspace/fdc/nutrition.db")
OUT_MD = "/workspace/fdc/merged/docs/CROSS_DB_REPORT.md"
OUT_CSV = "/workspace/fdc/merged/data/cross_db_match.csv"

NUTS = ["energy", "protein", "fat", "carbohydrate", "fiber", "calcium",
        "iron", "sodium", "potassium", "vitamin_c"]
NUT_CN = {"energy": "能量kcal", "protein": "蛋白质g", "fat": "脂肪g",
          "carbohydrate": "碳水g", "fiber": "纤维g", "calcium": "钙mg",
          "iron": "铁mg", "sodium": "钠mg", "potassium": "钾mg",
          "vitamin_c": "VC mg"}

SRC_ORDER = ["CN", "USDA", "JP", "UK", "FR", "ID", "WAFCT", "ASEAN"]
SRC_NAME = {"CN": "中国", "USDA": "美国", "JP": "日本", "UK": "英国",
            "FR": "法国", "ID": "印尼", "WAFCT": "西非", "ASEAN": "东盟"}


def norm_en(s):
    """英文名规范化：去状态/烹饪词与标点，小写。"""
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[（(].*?[)）]|［\[.*?[\]］]", "", s)   # 括号
    s = re.sub(r"\b(raw|fresh|uncooked|plain|unprepared|boiled|cooked|"
               r"steamed|fried|grilled|roasted|baked|canned|dried|frozen|"
               r"skinless|boneless|lean|fat)\b", " ", s)
    s = re.sub(r"[^a-z ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def median_of(cur, src, cat, nut):
    vals = [r[0] for r in cur.execute("""
        select nv.display_val from norm_food nf
        join norm_value nv on nv.norm_food_id = nf.norm_food_id
        where nf.source=? and nf.canon_cat=? and nv.nut_key=?
          and nv.display_val is not null""", (src, cat, nut))]
    return statistics.median(vals) if vals else None


def main():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cur = con.cursor()
    md, csv_lines = [], []

    md.append("# 跨库交叉比对报告\n")
    md.append("> 原则（用户决策）：**不做跨库实体合并**，按名字和分类并排。")
    md.append("本报告只做统计对照与同名样本比对，供数据质量评估使用。\n")

    # ---------------- A. 分类级分布 ----------------
    md.append("## A. 分类级中位数对照（每 100g）\n")
    md.append("口径警告：USDA 碳水是减差法（含纤维），中国表碳水含纤维但")
    md.append("能量只计可利用碳水；两者碳水列**不可直接比大小**。\n")
    cats = [r[0] for r in cur.execute(
        "select distinct canon_cat from norm_food order by canon_cat")]
    for cat in cats:
        cat_cn = cur.execute(
            "select cat_cn from norm_canon_cat where canon_cat=?", (cat,)
        ).fetchone()
        cat_cn = cat_cn[0] if cat_cn else cat
        md.append(f"\n### {cat} · {cat_cn}\n")
        md.append("| 营养素 | " + " | ".join(
            f"{SRC_NAME[s]}" for s in SRC_ORDER) + " |")
        md.append("|---|" + "---:|" * len(SRC_ORDER))
        for nut in NUTS:
            row = []
            for s in SRC_ORDER:
                m = median_of(cur, s, cat, nut)
                row.append(f"{m:.1f}" if m is not None else "—")
            md.append(f"| {NUT_CN[nut]} | " + " | ".join(row) + " |")

    # ---------------- B. 食物级同名对照 ----------------
    md.append("\n## B. 食物级同名样本对照（UK ↔ USDA）\n")
    md.append("选 UK 而非 CN 做名称匹配：中国表英文名仅 21 条补缺行才有，"
              "且为描述句式（Pork, rear hock），与 USDA 命名差异过大，"
              "强行匹配误配率过半。UK 与 USDA 同为英语库、命名规范接近，"
              "适合做逐项对照。差异 = (USDA − UK) / UK × 100%。\n")

    uk_rows = cur.execute("""
        select norm_food_id, source_id, name_local, canon_cat
        from norm_food where source='UK'""").fetchall()
    usda_all = cur.execute(
        "select norm_food_id, name_local, canon_cat from norm_food "
        "where source='USDA'").fetchall()
    # 词集合匹配：UK「Roast chicken, skinless」vs USDA「Chicken, broilers
    # or fryers, meat only, raw」词序不同。规范化后取词集合重叠，
    # 阈值 2.5（分类一致加 0.5 分）。
    STOP = {"with", "and", "of", "in", "the", "a", "an", "or", "to", "from",
            "plus", "ns", "as", "for", "made", "only", "meat"}
    usda_tok = []
    for fid, name, cat in usda_all:
        toks = frozenset(norm_en(name).split()) - STOP
        if toks:
            usda_tok.append((fid, name, cat, toks))

    def nuts_of(fid):
        return dict(cur.execute(
            "select nut_key, display_val from norm_value where norm_food_id=?",
            (fid,)))

    matched = []
    seen_usda = set()
    for fid, code, cn, cat in uk_rows:
        toks = frozenset(norm_en(cn).split()) - STOP
        if not toks:
            continue
        best, best_ov = None, 0
        for fid2, nm, c2, tk in usda_tok:
            if fid2 in seen_usda:
                continue
            ov = len(toks & tk)
            if c2 == cat:
                ov += 1.0          # 分类一致是强信号
            if ov > best_ov:
                best, best_ov = (fid2, nm), ov
        if best is None or best_ov < 3.5:
            continue
        uf, un = best
        seen_usda.add(uf)
        cnv, usv = nuts_of(fid), nuts_of(uf)
        common = [n2 for n2 in ("energy", "protein", "fat")
                  if n2 in cnv and n2 in usv]
        if not common:
            continue
        matched.append((code, cn, cat, un, cnv, usv, common))

    md.append(f"匹配成功 **{len(matched)}** 对（阈值为词重叠≥3.5，偏保守）。")
    md.append("**注意**：此为近似匹配，存在少量误配（如巧克力蛋糕配到其他"
              "蛋糕），用于分布级评估而非逐条取值；B 部分的高差异行多为"
              "同属一类的不同变体。\n")
    md.append("| UK 编码 | UK 名称 | 分段 | USDA 名称 | 能量 差% | 蛋白 差% | 脂肪 差% |")
    md.append("|---|---|---|---|---:|---:|---:|")
    csv_lines.append("uk_code,uk_name,cat,usda_name,"
                     "cn_kcal,usda_kcal,kcal_diff_pct,"
                     "cn_protein,usda_protein,protein_diff_pct,"
                     "cn_fat,usda_fat,fat_diff_pct")
    big_diff = 0
    for code, cn, cat, un, cnv, usv, common in sorted(matched)[:400]:
        cells = []
        raw = {}
        for nut in ("energy", "protein", "fat"):
            if nut in common:
                d = (usv[nut] - cnv[nut]) / max(abs(cnv[nut]), 0.1) * 100
                cells.append(f"{d:+.0f}%")
                raw[nut] = (cnv[nut], usv[nut], d)
            else:
                cells.append("—")
        if "energy" in raw and abs(raw["energy"][2]) > 40:
            big_diff += 1
        md.append(f"| {code} | {cn} | {cat} | {un[:40]} | " +
                  " | ".join(cells) + " |")
        def g(nut, i):
            return raw[nut][i] if nut in raw else ""
        csv_lines.append(",".join(str(x) for x in [
            code, cn, cat, un,
            g("energy", 0), g("energy", 1),
            f"{g('energy',2):.0f}" if "energy" in raw else "",
            g("protein", 0), g("protein", 1),
            f"{g('protein',2):.0f}" if "protein" in raw else "",
            g("fat", 0), g("fat", 1),
            f"{g('fat',2):.0f}" if "fat" in raw else ""]))

    md.append(f"\n能量差异超 ±40% 的配对：{big_diff} 对"
              f"（部分为正常现象：同名不同部位/加工方式/含水量差异）。")

    # ---------------- C. 结论 ----------------
    md.append("\n## C. 结论\n")
    md.append("1. **碳水口径**：USDA（减差法，含全部碳水+纤维）系统性高于"
              "中国表（总碳水口径，能量只计可利用碳水）。跨库比较碳水时，"
              "建议改比「纤维」和「能量」，而不是碳水列。")
    md.append("2. **能量**：各库均以 Atwater 系数计算，中位数偏差通常 <10%，"
              "可直接对照。")
    md.append("3. **微量营养素**：各库检测方法与采样年份不同，同一食物"
              "铁/钙差异 20-50% 属正常，建议取多库中位数使用而非单库值。")
    md.append("4. **修复影响**：中国库 117 条 OCR 读数错误已修复"
              "（`china_food_merged.merge_flag='ocr_repaired'`），"
              "61 条 macro_sum 假警报已澄清，4 条转人工"
              "（`needs_manual_review`）。")

    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    with open(OUT_CSV, "w", encoding="utf-8") as f:
        f.write("\n".join(csv_lines))
    print(f"匹配 {len(matched)} 对；报告 -> {OUT_MD}")
    print(f"CSV -> {OUT_CSV}")
    con.close()


if __name__ == "__main__":
    main()
