"""表头锚定 v13 —— 布局模板 + 序列对齐(最终方案)。

调查结论(15 页样本):
表头字段序列高度稳定,只有两类区段:
  A 区(能量/宏量):食部 水分 能量kcal 能量kJ 蛋白质 脂肪 碳水 膳食纤维 胆固醇 灰分
                   维生素A β-胡萝卜素 视黄醇 硫胺素 核黄素
  B 区(微量):       烟酸 维生素C 维生素E(总/α/β/γ/TE) 钙 磷 钾 钠 镁 铁 锌 硒 铜 锰
相邻页成对出现,两区字段互补 = 完整 31 项。

最终算法:
1. 列位置:数据行 x 聚类(min_gap=42)—— 已验证可靠
2. 字段命名:表头字段序列 vs 数值列序列,Needleman-Wunsch 保序对齐
3. 名称列合并(x 320~720 区间)
4. 相邻页按食物编码合并成完整记录
"""
import re
import statistics
from anchor3 import hits_in
from anchor6 import en_hits

CODE_RE = re.compile(r"^\d{6}$")
UNIT_RE = re.compile(r"^(kcal|kj|mg|ug|μg[\w]*|ugrae|g|%)$", re.I)
X_LO, X_HI = 150, 3120
NAME_LO, NAME_HI = 320, 720

FIELD_ORDER = [
    "food_code", "food_name", "edible_pct", "water_g",
    "energy_kcal", "energy_kj", "protein_g", "protein_pct",
    "fat_g", "fat_pct", "fat_sat_g", "fat_mono_g", "fat_poly_g",
    "carb_g", "fiber_g", "cholesterol_mg", "ash_g",
    "vit_a_ug", "beta_carotene_ug", "retinol_ug",
    "thiamin_mg", "riboflavin_mg", "niacin_mg", "vit_c_mg",
    "vit_e_total_mg", "vit_e_mg", "vit_e_alpha_g", "vit_e_gamma_g", "vit_e_te_mg",
    "calcium_mg", "phosphorus_mg", "potassium_mg", "sodium_mg",
    "magnesium_mg", "iron_mg", "zinc_mg", "selenium_ug",
    "copper_mg", "manganese_mg", "iodine_ug",
    "folate_ug", "biotin_ug", "pantothenic_mg", "choline_mg",
    "vit_b6_mg", "vit_b12_ug", "caox_mg", "comment",
]
OIDX = {k: i for i, k in enumerate(FIELD_ORDER)}


def is_data_row(row):
    return any(CODE_RE.match(it["t"].strip()) for it in row)


def cluster(xs, min_gap=42):
    if not xs:
        return []
    s = sorted(xs)
    groups = [[s[0]]]
    for v in s[1:]:
        if v - groups[-1][-1] <= min_gap:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [statistics.median(g) for g in groups]


def page_layout(page_rows, min_gap=42):
    drows = [r for r in page_rows if is_data_row(r)]
    if not drows:
        return None
    xs = [it["x"] for r in drows for it in r if it["t"].strip()]
    cols = cluster(xs, min_gap)
    if not cols:
        return None
    code_x = cols[0]
    name_cols = [c for c in cols[1:] if NAME_LO < c < NAME_HI]
    numeric = [c for c in cols if c >= NAME_HI]
    name_x = (min(name_cols) + max(name_cols)) / 2 if name_cols else None
    return dict(code_x=code_x, name_x=name_x,
                name_lo=min(name_cols) if name_cols else NAME_LO,
                numeric=numeric)


def header_seq(page_rows, header_scan=14):
    toks = []
    for row in page_rows[:header_scan]:
        if is_data_row(row):
            break
        for it in row:
            if not (X_LO <= it["x"] <= X_HI):
                continue
            t = it["t"].strip()
            if not t or UNIT_RE.match(t):
                continue
            en = en_hits(t)
            ks = [k for k, _ in en] if en else [k for k, _ in hits_in(t)]
            if ks:
                toks.append((it["x"], sorted(ks, key=lambda k: OIDX.get(k, 999))))
    allmap = {}
    for x, ks in toks:
        allmap.setdefault(x, [])
        for k in ks:
            if k not in allmap[x]:
                allmap[x].append(k)
    fields, seen = [], set()
    for x in sorted(allmap):
        for k in allmap[x]:
            if k in seen:
                continue
            seen.add(k)
            fields.append((x, k))
    return fields


def align_map(fields, cols_x, tol=135):
    """Needleman-Wunsch 保序对齐,返回 {col_index: field_key}。"""
    n, m = len(fields), len(cols_x)
    if n == 0 or m == 0:
        return {}
    NEG = -10 ** 7
    dp = [[NEG] * (m + 1) for _ in range(n + 1)]
    bk = [[0] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0
    for j in range(1, m + 1):
        dp[0][j] = dp[0][j - 1] - 1
        bk[0][j] = 2                     # skip_col
    for i in range(1, n + 1):
        dp[i][0] = dp[i - 1][0] - 1
        bk[i][0] = 1                     # skip_field
        for j in range(1, m + 1):
            best, arg = dp[i - 1][j - 1], 0
            d = abs(fields[i - 1][0] - cols_x[j - 1])
            if d <= tol:
                sc = dp[i - 1][j - 1] + (10000 - d * 10)
                if sc > best:
                    best, arg = sc, 0
            if dp[i - 1][j] - 1 > best:
                best, arg = dp[i - 1][j] - 1, 1
            if dp[i][j - 1] - 1 > best:
                best, arg = dp[i][j - 1] - 1, 2
            dp[i][j], bk[i][j] = best, arg
    res, i, j = {}, n, m
    while i > 0 and j > 0:
        a = bk[i][j]
        if a == 0:
            res[j - 1] = i - 1
            i, j = i - 1, j - 1
        elif a == 1:
            i -= 1
        else:
            j -= 1
    return res


def build_columns(page_rows, min_gap=42):
    """返回 (布局 dict, [(x, key|None)])。"""
    lay = page_layout(page_rows, min_gap)
    if not lay:
        return None, []
    fields = header_seq(page_rows)
    cand = [(x, k) for x, k in fields
            if k not in ("food_code", "food_name", "comment")]
    amap = align_map(cand, lay["numeric"])
    cols = []
    for j, cx in enumerate(lay["numeric"]):
        cols.append((cx, cand[amap[j]][1] if j in amap else None))
    return lay, cols


# ——————————————————— 记录抽取 ———————————————————
SYMBOLS = {"Tr", "tr", "TR", "un", "UN", "*", "—", "–", "-", "－", "/",
           "(0)", "（0）", "…", "一", "（"}


def clean_value(t):
    """→ (value|None, symbol|None)"""
    if t is None:
        return None, None
    s = t.strip().replace(" ", "").replace("\u00a0", "")
    for ch in ["—", "–", "－", "—"]:
        s = s.replace(ch, "")
    if s == "":
        return None, None
    if s in SYMBOLS:
        return None, s
    m = re.match(r"^(\d{6})$", s)
    if m:
        return s, None
    m = re.match(r"^([<>~]?)(\d+(?:\.\d+)?)$", s)
    if m:
        return float(m.group(2)), (m.group(1) or None)
    # OCR 形近修正
    t2 = s
    for a, b in [("O", "0"), ("o", "0"), ("l", "1"), ("I", "1"), ("|", "1"),
                 ("S", "5"), ("B", "8"), ("Z", "2"), ("g", "9"), ("D", "0")]:
        t2 = t2.replace(a, b)
    m = re.match(r"^(\d+(?:\.\d+)?)$", t2)
    if m:
        v = float(m.group(1))
        return v, (None if t2 == s else "ocr_fixed")
    m = re.match(r"^(\d+(?:\.\d+)?)x$", s)
    if m:
        return float(m.group(1)), "ocr_fixed"
    return None, "unparsed"


def extract_records(page_rows, lay, cols):
    """抽取该页所有记录。"""
    out = []
    for row in page_rows:
        if not is_data_row(row):
            continue
        code = None
        for it in row:
            m = CODE_RE.match(it["t"].strip())
            if m:
                code = m.group(0)
                break
        if code is None:
            continue
        rec = {"food_code": code, "_page": None}
        name_parts = []
        for it in row:
            t = it["t"].strip()
            if not t or CODE_RE.match(t):
                continue
            x = it["x"]
            if lay["name_x"] is not None and abs(x - lay["name_x"]) <= 190:
                if not re.match(r"^[\d.]+$", t) and t not in SYMBOLS:
                    name_parts.append(t)
                continue
            # 归属最近列
            best, bd = None, 1e9
            for cx, key in cols:
                d = abs(cx - x)
                if d < bd:
                    bd, best = d, key
            if best and bd <= 60:
                v, sym = clean_value(t)
                if rec.get(best) is None:
                    rec[best] = v
                    if sym:
                        rec[best + "_sym"] = sym
                elif rec.get(best) is not None and sym:
                    rec[best + "_sym2"] = sym
        rec["food_name"] = "".join(name_parts).strip()
        out.append(rec)
    return out
