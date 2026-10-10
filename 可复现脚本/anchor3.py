"""表头锚定 v3:支持连读表头的内部拆分。

问题:OCR 常把相邻多个表头连读成一个 token,例如
  「总维生素A 胡尊卜素视黄醇 硫胺素」= vit_a + carotene + retinol + thiamin
  「钾钠镁铁锌」= potassium + sodium + magnesium + iron + zinc
仅做整串匹配会漏掉后面的列,导致整行数据左移错位。

方案:对每个表头 token 反复抽取未占用的锚点,直到无新命中;
再用「等间距补齐」推断被完全吞掉的列。
"""
import re

ZH_EN = [
    ("food_code",     r"食物(编码|端码|代吗)",  r"food\s*code"),
    ("food_name",     r"食物名称",               r"food\s*name"),
    ("edible_pct",    r"食部",                   r"edible"),
    ("water_g",       r"水分",                   r"water"),
    ("energy_kcal",   r"能量",                   r"energy"),
    ("energy_kj",     None,                      r"\bkj\b"),
    ("protein_g",     r"蛋白质",                 r"protein(?!\s*%)"),
    ("protein_pct",   None,                      r"protein\s*%"),
    ("fat_g",         r"脂肪",                   r"fat(?!\s*%)"),
    ("fat_pct",       None,                      r"fat\s*%"),
    ("fat_sat_g",     r"饱和脂肪",                r"saturated"),
    ("fat_mono_g",    r"单不饱和脂肪",             r"mono"),
    ("fat_poly_g",    r"多不饱和脂肪",             r"poly"),
    ("carb_g",        r"碳水化合物",               r"\bcho\b|carbo"),
    ("fiber_g",       r"(不溶性)?膳食纤维",        r"fiber"),
    ("cholesterol_mg", r"胆固醇",                 r"cholesterol"),
    ("ash_g",         r"灰分",                    r"ash"),
    ("vit_a_ug",      r"维生素\s*A",               r"vitamin\s*a"),
    ("beta_carotene_ug", r"胡萝卜素",              r"carotene"),
    ("retinol_ug",    r"视黄醇",                   r"retinol"),
    ("thiamin_mg",    r"硫胺素|维生素\s*B1",        r"thiamin"),
    ("riboflavin_mg", r"核黄素|维生素\s*B2",        r"riboflavin"),
    ("niacin_mg",     r"烟酸",                    r"niacin"),
    ("vit_c_mg",      r"维生素\s*C",               r"vitamin\s*c"),
    ("vit_e_mg",      r"维生素\s*E",               r"vitamin\s*e"),
    ("vit_e_total_mg", r"总维生素\s*E",             r"total"),
    ("vit_e_te_mg",   r"生育酚当量|α-?TE",           r"\bte\b"),
    ("vit_e_alpha_g", r"α-生育酚",                 r"α-e"),
    ("vit_e_gamma_g", r"γ-生育酚",                 r"[δ8]-e"),
    ("calcium_mg",    r"钙",                       r"\bca\b|calcium"),
    ("phosphorus_mg", r"磷",                       r"phosphorus"),
    ("potassium_mg",  r"钾",                       r"potassium"),
    ("sodium_mg",     r"钠",                       r"\bna\b|sodium"),
    ("magnesium_mg",  r"镁",                       r"\bmg\b|magnesium"),
    ("iron_mg",       r"铁",                       r"\bfe\b|iron"),
    ("zinc_mg",       r"锌",                       r"\bzn\b|zinc"),
    ("selenium_ug",   r"硒",                       r"\bse\b|selenium"),
    ("copper_mg",     r"铜",                       r"\bcu\b|copper"),
    ("manganese_mg",  r"锰",                       r"\bmn\b|manganese"),
    ("iodine_ug",     r"碘",                       r"iodine"),
    ("folate_ug",     r"叶酸",                     r"folate"),
    ("biotin_ug",     r"生物素",                   r"biotin"),
    ("pantothenic_mg", r"泛酸",                    r"pantothenic"),
    ("choline_mg",    r"胆碱",                     r"choline"),
    ("vit_b6_mg",     r"维生素\s*B6|吡哆醇",        r"pyridoxine|b6"),
    ("vit_b12_ug",    r"维生素\s*B12|钴胺素",        r"cobalamin|b12"),
    ("caox_mg",       r"草酸",                     r"oxalic|oxalate"),
    ("comment",       r"备注",                     r"remark"),
]

# (key, 中文正则, 英文正则, 优先级)—— 优先级高的先匹配,避免误吞
COMP = [(k,
         re.compile(z, re.I) if z else None,
         re.compile(e, re.I))
        for k, z, e in ZH_EN]

# 常见 OCR 形近误识修正(表头专用)
OCR_FIX = [("尊卜", "萝卜"), ("胡萝卜素", "胡萝卜素"), ("白蛋白", None)]


def hits_in(text):
    """在一个 token 内找出所有不同锚点(去重),返回 [(key, start, length)]。"""
    t = text.strip()
    for a, b in OCR_FIX:
        if b and a in t:
            t = t.replace(a, b)
    found = {}
    for k, zc, ec in COMP:
        best = None
        for rx, w in ((zc, 1.0), (ec, 1.2)):
            if rx is None:
                continue
            m = rx.search(t)
            if m:
                sc = len(m.group(0)) * w
                if best is None or sc > best[0]:
                    best = (sc, m.start())
        if best:
            found[k] = best[1]
    return sorted(found.items(), key=lambda t: t[1])


def build_columns(page_rows, header_scan=14, min_hits=3):
    """推导 [(field_key, x_center)] 列映射。"""
    best = (0, [])
    for row in page_rows[:header_scan]:
        hits = []
        for it in row:
            for k, off in hits_in(it["t"]):
                hits.append((k, it["x"], it["y"], it["t"]))
        if len(hits) > best[0]:
            best = (len(hits), hits)
    hits = best[1]
    if len(hits) < min_hits:
        return []

    # 按 y 分层;同层同 key 保留 x 最接近该层中位的
    ys = sorted(set(round(h[2]) for h in hits))
    cols = {}
    for y in ys:
        layer = [h for h in hits if round(h[2]) == y]
        layer.sort(key=lambda h: h[1])
        layer_xs = [h[1] for h in layer]
        med = sorted(layer_xs)[len(layer_xs) // 2]
        chosen = {}
        for k, x, yy, txt in layer:
            if k not in chosen:
                chosen[k] = x
            else:
                # 同层重复:若位置差异大,可能是另一列,保留更近中位的
                pass
        # 处理同层重复 key:按 x 递增分配多实例(仅当间距 > 40)
        byk = {}
        for k, x, yy, txt in layer:
            byk.setdefault(k, []).append(x)
        for k, xs in byk.items():
            if len(xs) > 1:
                # 保留第一个
                chosen[k] = xs[0]
        cols.update(chosen)
    return sorted(((k, v) for k, v in cols.items()), key=lambda t: t[1])
