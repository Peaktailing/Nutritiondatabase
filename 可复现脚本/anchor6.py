"""表头锚定 v6 —— 以英文/单位行为主锚(最终方案)。

关键洞察:
中文表头常被 OCR 连读成一整串,不可靠;而**英文表头行**天然按列排布,
单位行(kcal/kJ/mg/ugRAE/%)同样按列排布 —— 二者结合即可精确锚定。

实测(第61页)英文行:
  Niacin@838 | Vitamin C@998 | Total@1156 | α-E@1294 | (β+)-E@1446 |
  8-E@1588 | Ca@1720 | Na@2124 | MgFe@2305 | Zn@2494 | Se@2632 |
  Cu@2772 | Mn@2904 | Remark@3043
其中 `MgFe@2305` 是 Mg 与 Fe 连读 → 需要拆分为两列。

做法:
1. 只取表头区的英文行(ASCII 占比高)与单位行
2. 英文 token 内按已知缩写表拆分(MgFe → Mg,Fe)
3. 与数据列位置做顺序对齐
"""
import re
import statistics
from anchor3 import hits_in

# 英文缩写 → 字段
EN_ABBR = [
    ("food_code",      r"food\s*code"),
    ("food_name",      r"food\s*name"),
    ("edible_pct",     r"edible"),
    ("water_g",        r"water"),
    ("energy_kcal",    r"kcal"),
    ("energy_kj",      r"\bkj\b"),
    ("protein_pct",    r"protein\s*%"),
    ("protein_g",      r"protein"),
    ("fat_pct",        r"fat\s*%"),
    ("fat_g",          r"fat"),
    ("fat_sat_g",      r"saturated"),
    ("fat_mono_g",     r"mono"),
    ("fat_poly_g",     r"poly"),
    ("carb_g",         r"\bcho\b|carbo"),
    ("fiber_g",        r"fiber"),
    ("cholesterol_mg", r"cholesterol"),
    ("ash_g",          r"ash"),
    ("vit_a_ug",       r"vitamin\s*a"),
    ("beta_carotene_ug", r"carotene"),
    ("retinol_ug",     r"retinol"),
    ("thiamin_mg",     r"thiamin"),
    ("riboflavin_mg",  r"riboflavin"),
    ("niacin_mg",      r"niacin"),
    ("vit_c_mg",       r"vitamin\s*c"),
    ("vit_e_total_mg", r"total"),
    ("vit_e_alpha_g",  r"α-e|a-e"),
    ("vit_e_gamma_g",  r"δ-e|8-e"),
    ("vit_e_te_mg",    r"a-te|\bte\b"),
    ("vit_e_mg",       r"vitamin\s*e"),
    ("calcium_mg",     r"\bca\b|calcium"),
    ("phosphorus_mg",  r"phosphorus"),
    ("sodium_mg",      r"\bna\b|sodium"),
    ("magnesium_mg",   r"\bmg\b|magnesium"),
    ("iron_mg",        r"\bfe\b|iron"),
    ("zinc_mg",        r"\bzn\b|zinc"),
    ("selenium_ug",    r"\bse\b|selenium"),
    ("copper_mg",      r"\bcu\b|copper"),
    ("manganese_mg",   r"\bmn\b|manganese"),
    ("iodine_ug",      r"iodine"),
    ("folate_ug",      r"folate"),
    ("biotin_ug",      r"biotin"),
    ("pantothenic_mg", r"pantothenic"),
    ("choline_mg",     r"choline"),
    ("vit_b6_mg",      r"pyridoxine|b6"),
    ("vit_b12_ug",     r"cobalamin|b12"),
    ("caox_mg",        r"oxalic|oxalate"),
    ("comment",        r"remark"),
]
EN_C = [(k, re.compile(p, re.I)) for k, p in EN_ABBR]

# 顺序(用于同 token 内排序 + 顺序对齐时的先验)
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

ASCII_RE = re.compile(r"[A-Za-z]")


def en_hits(text):
    """英文 token → [(field, pos)] 支持连读拆分(MgFe → Mg,Fe)。"""
    t = text.strip()
    if not t or not ASCII_RE.search(t):
        return []
    found = {}
    for k, rx in EN_C:
        m = rx.search(t)
        if m:
            found[k] = m.start()
    return sorted(found.items(), key=lambda z: z[1])


def data_row_xs(page_rows, code_len=6):
    xs = []
    for row in page_rows:
        if not any(it["t"].strip().isdigit()
                   and len(it["t"].strip()) == code_len for it in row):
            continue
        for it in row:
            t = it["t"].strip()
            if t.isdigit() and len(t) == code_len:
                continue
            # 排除食物名称(纯中文且位于名称列区间)
            if not ASCII_RE.search(t) and not re.match(r"^[\d.]+$", t) and t not in ("Tr", "tr", "*", "un"):
                # 中文 token:若是名称则跳过(名称列在 330~700)
                if 320 < it["x"] < 720:
                    continue
            xs.append(it["x"])
    return xs


def cluster_cols(xs, min_gap=42):
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


def build_columns(page_rows, min_gap=42, header_scan=14):
    """返回 [(x, key|None)]。英文表头优先,中文表头兜底。"""
    cols = cluster_cols(data_row_xs(page_rows), min_gap)
    if not cols:
        return []

    # 收集表头区的英文命中
    en_seq = []   # (x, [keys])
    zh_seq = []
    for row in page_rows[:header_scan]:
        for it in row:
            hs = en_hits(it["t"])
            if hs:
                en_seq.append((it["x"], [k for k, _ in hs]))
            else:
                ks = [k for k, _ in hits_in(it["t"])]
                if ks:
                    zh_seq.append((it["x"], ks))

    def flatten(seq):
        flat = []
        for x, ks in sorted(seq, key=lambda t: t[0]):
            for k in sorted(ks, key=lambda k: OIDX.get(k, 999)):
                flat.append((x, k))
        return flat

    en_flat = flatten(en_seq)
    zh_flat = flatten(zh_seq)

    # 英文优先;数量匹配则顺序对齐
    for flat in (en_flat, zh_flat):
        if not flat:
            continue
        if len(flat) == len(cols):
            return [(cx, flat[i][1]) for i, cx in enumerate(cols)]
        # 差距不大(<=2)也尝试顺序对齐
        if 0 < abs(len(flat) - len(cols)) <= 2:
            return [(cx, flat[i][1] if i < len(flat) else None)
                    for i, cx in enumerate(cols)]

    # 兜底:就近配对
    out = []
    used = set()
    for cx in cols:
        best, bi = None, None
        for i, (hx, key) in enumerate(en_flat or zh_flat):
            if i in used:
                continue
            d = abs(hx - cx)
            if best is None or d < best:
                best, bi = d, i
        if best is not None and best <= 110:
            used.add(bi)
            out.append((cx, (en_flat or zh_flat)[bi][1]))
        else:
            out.append((cx, None))
    return out
