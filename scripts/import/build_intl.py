#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把国际食物成分数据库导入统一的 nutrition.db。

覆盖：
  - 法国 CIQUAL 2025      -> 表 ciqual_food        （3484 条食物，84 列）
  - FAO/INFOODS 西非表     -> 表 fao_wafct_food     （57 成分汇总表）
  - 英国 CoFID 2021       -> 表 uk_cofid_food      （多 sheet 合并，逐条食物）
  - 日本 MEXT 2020        -> 表 jp_mext_food       （可食部100g成分表）

注意：CIQUAL / CoFID 等欧洲表使用「小数逗号」（"4,41" 表示 4.41），
      数值化前必须先把逗号换成点号，否则会全部变成 NaN。
"""
import os
import os as _os
import sys as _sys

# 仓库根目录（本文件位于 <root>/scripts/import/build_intl.py）
ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(
    _os.path.abspath(__file__))))
import sqlite3, os, re, warnings
import pandas as pd

warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = os.environ.get("FDC_DB", os.path.join(BASE, "nutrition.db"))
INTL = os.path.join(BASE, "intl")

# ---------------------------------------------------------------- 工具

DASHES = ("-", "–", "—", "−", "‐", "‑", "\u2010", "\u2011", "\u2012", "\u2013", "\u2014")
# 空值/缺失标记：欧洲表常用 "-"、tr(痕迹)、na 等
NULL_TOKENS = {"", "-", "–", "—", "−", "na", "n/a", "nd", "tr", "tr.", "nan", "none",
               "0", "\u2013", "\u2014"}


def norm_col(c):
    """把多行表头列名（含换行/单位）规范成 snake_case。"""
    c = str(c).replace("\n", " ").replace("\r", " ")
    c = re.sub(r"\s+", " ", c).strip()
    m = re.search(r"\((.*?)\)\s*$", c)
    unit = m.group(1).strip() if m else ""
    name = c[: m.start()].strip() if m else c
    name = name.lower()
    name = name.replace(" ", "_").replace(",", "").replace("-", "_").replace("'", "")
    name = re.sub(r"[^0-9a-z_]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    if unit:
        u = unit.lower().replace(" ", "_").replace("\u00b5", "u").replace("\u03b3", "g")
        u = re.sub(r"[^0-9a-z_]+", "_", u).strip("_")
        name = f"{name}__{u}"
    return name[:70] or "col"


def dedup(cols):
    seen, out = {}, []
    for c in cols:
        if c in seen:
            seen[c] += 1
            out.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            out.append(c)
    return out


def to_num(s):
    """欧洲小数逗号 -> 点号，再数值化；把 -/tr/na 等当成缺失。"""
    if not pd.api.types.is_numeric_dtype(s):
        s = (s.astype(str)
             .str.replace("\u00a0", " ", regex=False)
             .str.replace(" ", "", regex=False)
             .str.replace(",", ".", regex=False))
        s = s.where(~s.str.lower().isin([t for t in NULL_TOKENS if t != "0"]))
    return pd.to_numeric(s, errors="coerce")


def load_df(df, table):
    with sqlite3.connect(DB) as conn:
        df.to_sql(table, conn, if_exists="replace", index=False)


def report(table, n, extra=""):
    with sqlite3.connect(DB) as conn:
        cols = len(pd.read_sql(f'SELECT * FROM "{table}" LIMIT 1', conn).columns)
    print(f"  {table}: {n} 行, {cols} 列 {extra}")


# ---------------------------------------------------------------- CIQUAL

def import_ciqual():
    path = os.path.join(INTL, "fr_ciqual_2025.xlsx")
    df = pd.read_excel(path, sheet_name="food composition", header=0)
    df.columns = dedup([norm_col(c) for c in df.columns])

    for c in df.columns:
        if "_nom_" in c or c in ("alim_nom_eng", "alim_nom_sci"):
            df[c] = df[c].astype(str).replace("nan", None)      # 名称保持文本
        elif c.endswith("_code") and c == "alim_code":
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
        elif c.endswith("_code"):
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
        else:
            df[c] = to_num(df[c])

    load_df(df, "ciqual_food")
    with sqlite3.connect(DB) as conn:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ciqual_code ON ciqual_food(alim_code)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ciqual_name ON ciqual_food(alim_nom_eng)")
    protein = [c for c in df.columns if c.startswith("protein__")]
    ok = int(df[protein[0]].notna().sum()) if protein else 0
    return len(df), ok


# ---------------------------------------------------------------- FAO WAFCT

def import_wafct():
    path = os.path.join(INTL, "fao_wafct_2019.xlsx")
    raw = pd.read_excel(path, sheet_name="05 NV_sum_57 (per 100g EP)", header=None)
    tags, names = raw.iloc[2].tolist(), raw.iloc[0].tolist()
    data = raw.iloc[3:].reset_index(drop=True)
    cols, seen = [], {}
    for i, (t, n) in enumerate(zip(tags, names)):
        t = str(t).strip() if pd.notna(t) else ""
        n = str(n).replace("\n", " ").strip() if pd.notna(n) else ""
        c = t if t and t != "nan" else n
        c = re.sub(r"[^0-9A-Za-z_]+", "_", c).strip("_") or f"col{i}"
        if c in seen:
            seen[c] += 1
            c = f"{c}_{seen[c]}"
        else:
            seen[c] = 0
        cols.append(c)
    data.columns = cols
    data = data.dropna(axis=1, how="all")

    code_col = cols[0]
    data["_is_food"] = data[code_col].astype(str).str.match(r"^\d+_\d+")
    text_cols = (code_col, "Food_name_in_English", "Food_name_in_French",
                 "Scientific_name", "BiblioID_Source", "_is_food")
    for c in data.columns:
        if c not in text_cols:
            data[c] = to_num(data[c])

    load_df(data, "fao_wafct_food")
    return len(data), int(data["_is_food"].sum())


# ---------------------------------------------------------------- 英国 CoFID

def import_cofid():
    """CoFID 2021 是多 sheet 工作簿。

    每个数据 sheet 的表头是「三行结构」：
        row0 人类可读列名（Water (g), Protein (g) ...）
        row1 INFOODS tagname（WATER, PROT ...）
        row2 描述（Water, Protein ...）
    真正数据从 row3 开始。列名取 row0，附加 row1 的 tagname 以保证唯一。
    """
    path = os.path.join(INTL, "uk_cofid_2021.xlsx")
    xl = pd.ExcelFile(path)
    skip = ("list of tables", "notes", "factors")
    frames = []
    for sh in xl.sheet_names:
        low = sh.lower()
        if any(k in low for k in skip):
            continue
        raw = pd.read_excel(path, sheet_name=sh, header=None)
        # 找表头行：第一列含 "food code"
        # 注意：'1.4 Inorganics' sheet 的 A1 是空格（无 'Food Code' 标题），
        #   但列名在 B/C/D...，数据从 hdr+3 行开始。这类 sheet 必须单独处理，
        #   否则整个矿物质表会被静默丢弃（曾发生的 bug）。
        hdr = None
        for i in range(min(12, len(raw))):
            first = str(raw.iloc[i, 0]).strip().lower() if raw.shape[1] else ""
            if first.startswith("food code"):
                hdr = i
                break
        blank_acol = False
        if hdr is None:
            # 退化检测：A 列首行为空，但 B 列起有列名，且第 3 行出现食物编码
            cand = None
            for i in range(min(6, len(raw))):
                row0 = raw.iloc[i]
                nonempty = [str(x).strip() for x in row0 if pd.notna(x) and str(x).strip()]
                # 列名行应含多个文本列名，且 A 列为空
                if len(nonempty) >= 3 and not str(raw.iloc[i, 0]).strip():
                    if any(k in " ".join(nonempty).lower()
                           for k in ("name", "description", "group")):
                        cand = i
                        break
            if cand is None:
                continue
            hdr = cand
            blank_acol = True
        names = raw.iloc[hdr].tolist()
        tags = raw.iloc[hdr + 1].tolist() if hdr + 1 < len(raw) else [None] * len(names)
        data = raw.iloc[hdr + 3:].reset_index(drop=True)
        if len(data) == 0:
            continue
        if blank_acol:
            # A 列无标题：造一个 food_code 列名，避免整表被丢
            names = ["Food Code"] + list(names[1:])

        cols = []
        for k, (n, t) in enumerate(zip(names, tags)):
            n = str(n).replace("\n", " ").strip() if pd.notna(n) else ""
            t = str(t).strip() if pd.notna(t) else ""

            def clean(x):
                x = re.sub(r"\s+", " ", x).strip()
                m = re.search(r"\(([^()]*)\)\s*$", x)
                unit = m.group(1).strip() if m else ""
                nm = (x[: m.start()].strip() if m else x).lower()
                nm = nm.replace(" ", "_").replace(",", "").replace("-", "_").replace("/", "_")
                nm = nm.replace("'", "").replace(".", "").replace("%", "pct")
                nm = re.sub(r"[^0-9a-z_]+", "_", nm)
                nm = re.sub(r"_+", "_", nm).strip("_") or f"col{k}"
                if unit:
                    u = unit.lower().replace(" ", "").replace("\u00b5", "u").replace("\u03b3", "g")
                    u = re.sub(r"[^0-9a-z_]+", "_", u).strip("_")
                    nm = f"{nm}__{u}"
                return nm[:70]

            c = clean(n) if n and n.lower() != "nan" else ""
            if not c or c.startswith("col"):
                c = re.sub(r"[^0-9A-Za-z_]+", "_", t).strip("_").lower() or f"col{k}"
            cols.append(c)
        data.columns = dedup(cols)

        text_pat = re.compile(r"code|name|description|group|reference|footnote|tagname|source|sheet")
        for c in data.columns:
            if text_pat.search(c):
                continue
            data[c] = to_num(data[c])
        data["_source_sheet"] = sh
        frames.append(data)

    if not frames:
        return 0, 0
    # 以并集列对齐（不同 sheet 列集不完全一致）
    allcols = []
    for f in frames:
        for c in f.columns:
            if c not in allcols:
                allcols.append(c)
    merged = pd.concat([f.reindex(columns=allcols) for f in frames], ignore_index=True)
    merged = merged.dropna(axis=1, how="all")
    merged = merged.dropna(subset=[c for c in merged.columns if "code" in c] or None, how="all")
    load_df(merged, "uk_cofid_food")
    n_nut = len([c for c in merged.columns if not re.search(r"code|description|name|sheet", c)])
    return len(merged), n_nut


# ---------------------------------------------------------------- 日本 MEXT

def import_mext():
    """MEXT 日本食品標準成分表 2020。

    每个 sheet 的固定结构：
        row1  标题「食品番号 / 索引番号 / 可食部 100 g」
        row2  中文分类名（エネルギー/水分/たんぱく質 …）
        row3  子名称
        row10 单位（%, kJ, kcal, g, mg …）
        row11 INFOODS 成分識別子（REFUSE, ENERC, PROT-, FAT- …）  <- 用作列名
        row12 起为数据行
    仅取第 2 表（成分表）；氨基酸组成表另存为 jp_mext_amino_food。
    """
    jobs = [("jp_mext_2020_ch2.xlsx", "jp_mext_food", 2),
            ("jp_mext_2020_amino1.xlsx", "jp_mext_amino_food", None)]
    out = {}
    for fn, table, name_row in jobs:
        path = os.path.join(INTL, fn)
        if not os.path.exists(path):
            continue
        xl = pd.ExcelFile(path)
        frames = []
        for sh in xl.sheet_names:
            if sh in ("表全体",):
                continue
            raw = pd.read_excel(path, sheet_name=sh, header=None)
            # 找 data 起始行：第一列出现类似 5 位食品番号
            start = None
            for i in range(min(30, len(raw))):
                v = str(raw.iloc[i, 1]).strip()
                if re.match(r"^\d{4,5}$", v):
                    start = i
                    break
            if start is None:
                continue
            if name_row == 2:
                tags = [str(v).strip() for v in raw.iloc[start - 1].tolist()]
                # 上一行若为空或不像 tagname，回退一行
                if sum(1 for t in tags if re.match(r"^[A-Z][A-Z0-9_\-\.]{1,}$", t)) < 3:
                    tags = [str(v).strip() for v in raw.iloc[start - 2].tolist()]
                jp_names = [str(v).replace("\n", "").strip() for v in raw.iloc[start - 9].tolist()]
            else:
                tags = [str(v).strip() for v in raw.iloc[start - 1].tolist()]
                jp_names = [str(v).replace("\n", "").strip() for v in raw.iloc[start - 9].tolist()]

            data = raw.iloc[start:].reset_index(drop=True)
            cols = []
            for k, (t, jp) in enumerate(zip(tags, jp_names)):
                c = re.sub(r"[^0-9A-Za-z_\-]+", "_", t).strip("_")
                if not c or c in ("nan", "None"):
                    c = re.sub(r"[^0-9A-Za-z_]+", "_", jp).strip("_") or f"col{k}"
                if k <= 3:
                    c = {0: "food_code", 1: "food_number", 2: "index_number",
                         3: "food_name"}.get(k, c)
                cols.append(c[:70])
            data.columns = dedup(cols)
            data["_source_sheet"] = sh
            for c in data.columns:
                if c in ("food_code", "food_number", "index_number", "food_name", "_source_sheet"):
                    continue
                data[c] = to_num(data[c])
            # 丢弃食品番号为空的残留行
            code_col = "food_number" if "food_number" in data.columns else data.columns[0]
            data = data[data[code_col].notna()]
            if len(data):
                frames.append(data)
        if not frames:
            out[table] = (0, 0)
            continue
        allcols = []
        for f in frames:
            for c in f.columns:
                if c not in allcols:
                    allcols.append(c)
        merged = pd.concat([f.reindex(columns=allcols) for f in frames], ignore_index=True)
        merged = merged.dropna(axis=1, how="all")
        load_df(merged, table)
        out[table] = (len(merged), len(merged.columns))
    return out


# ---------------------------------------------------------------- main

def main():
    print("导入国际食物成分数据库 ->", DB)
    n, ok = import_ciqual()
    report("ciqual_food", n, f"(蛋白质非空 {ok})")
    n, nf = import_wafct()
    report("fao_wafct_food", n, f"(真实食物 {nf})")
    n, ncol = import_cofid()
    report("uk_cofid_food", n, f"({ncol} 列)")
    mext = import_mext()
    for t, (n, ncol) in mext.items():
        report(t, n, f"({ncol} 列)")
    print("DONE ->", DB)


if __name__ == "__main__":
    main()
