#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 ASEAN Food Composition Database 2014 (Mahidol Univ.) PDF 重建数据表。

关键发现：页面按 x 坐标天然分成两块——
  x <  229 : 描述区（Origin / Food and description / Alternate name / Food ID）
  x >= 229 : 22 个数值列，每列有固定 x 中心（约 229/256/290/318/347/375/406/436/
             461/486/512/536/560/583/608/637/665/694/719/746/772/802）
因此按 x 分桶即可准确取列，不再依赖多行文本拼接。
"""
import re, subprocess, csv, sys
from collections import defaultdict

PDF = os.path.join(ROOT, "intl_sea", "asean_fcd_2014.pdf")
OUT = os.path.join(ROOT, "intl_sea", "asean_fcd_2014.csv")

TAGS = ["DEN", "ENERC", "WATER", "PROCNT", "FAT", "CHOAVLDF", "FIBTG", "ASH",
        "CA", "P", "NA", "K", "FE", "CU", "ZN",
        "RETOL", "CARTB", "VITA_RAE", "THIA", "RIBF", "NIA", "VITC"]

# 数值列 x 中心（取整）
COLX = [229, 256, 290, 318, 347, 375, 407, 436, 461, 486, 512, 536,
        560, 583, 608, 637, 665, 694, 719, 746, 772, 802]

NUMRE = re.compile(r"^(?:-|\(\s*[\d.,]+\s*\)|[\d.,]+|\d+p|\d+-\d+|T|t|tr)$")


def page_words(page):
    xml = subprocess.run(
        ["pdftotext", "-f", str(page), "-l", str(page), "-bbox-layout", PDF, "-"],
        capture_output=True, text=True).stdout
    return [(float(a), float(b), float(c), float(d), e) for a, b, c, d, e in
            re.findall(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>', xml)]


def to_val(s):
    """返回 (值, flag)。括号内为推算值，- 为缺失。"""
    s = s.strip()
    if s in ("-", ""):
        return None, "missing"
    calc = False
    if s.startswith("(") and s.endswith(")"):
        calc = True
        s = s[1:-1]
    if s.upper() in ("T", "TR"):
        return 0.0, "trace"
    try:
        return float(s), ("calc" if calc else "ok")
    except ValueError:
        return None, "bad"


def main():
    recs = []
    group = ""
    for p in range(35, 88):
        ws = page_words(p)
        if not ws:
            continue
        # 分桶：数值列（按最近 x 中心） + 描述区
        byval = defaultdict(dict)     # y -> {col_idx: word}
        bydesc = defaultdict(list)    # y -> [(x, text)]
        for x0, y0, x1, y1, t in ws:
            if y0 < 130:
                continue
            if x0 >= 225:
                # 归到最近的列中心
                ci = min(range(len(COLX)), key=lambda i: abs(COLX[i] - x0))
                byval[round(y0)].setdefault(ci, t)
            else:
                bydesc[round(y0)].append((x0, t))

        # 分组标题
        for y in sorted(bydesc):
            txt = " ".join(t for _, t in sorted(bydesc[y]))
            if re.match(r"^[A-Z]\s+[A-Z]?[a-z]", txt) and y not in byval:
                group = txt

        # 数值行：22 个数值列位置基本齐全即视为一条记录
        for y in sorted(byval):
            cols = byval[y]
            if len(cols) < 18:
                continue
            vals = [(to_val(cols.get(i, "-"))) for i in range(len(COLX))]
            # 关联本记录的名称行：向上收集，直到遇到上一条数值行
            desc_parts = []
            prev_val_y = max([vy for vy in byval if vy < y and len(byval[vy]) >= 18],
                             default=-1)
            for yy in sorted(bydesc):
                if prev_val_y < yy < y:
                    desc_parts.append(" ".join(t for _, t in sorted(bydesc[yy])))
            desc = " ".join(desc_parts).strip()
            # 排除明显是分组标题的
            if False:
                desc = desc
            rec = {"page": p, "group": group, "desc": desc}
            m = re.search(r"\b([A-Z]{2,3}\d{1,4})\b", desc)
            rec["asean_id"] = m.group(1) if m else None
            for i, tag in enumerate(TAGS):
                rec[tag] = vals[i][0]
            recs.append(rec)

    print(f"解析出 {len(recs)} 条记录", file=sys.stderr)
    cols = ["page", "group", "asean_id", "desc"] + TAGS
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(recs)
    print("->", OUT, file=sys.stderr)
    for r in recs[:8]:
        print(f"  [{r['asean_id']}] enerc={r['ENERC']} prot={r['PROCNT']} ca={r['CA']} vitc={r['VITC']} | {r['desc'][:70]}", file=sys.stderr)


if __name__ == "__main__":
    main()
