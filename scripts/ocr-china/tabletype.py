"""表类型识别 —— 区分「营养成分表」与其他附录表,避免张冠李戴。

原书除主营养成分表外,还有多种附录表:
  - 食物氨基酸含量表(mg/100g)   ← 含水分/蛋白质字样,极易误判
  - 食物脂肪酸含量表(g/100g)
  - 食物样品描述表(编码+名称+采样信息)
  - 维生素/元素含量表(部分分类单独成表)

误判后果严重:氨基酸表的「异亮氨酸 900」会被当成某个营养字段。
因此必须**先判表类型,再决定是否抽取**。

判据(按可靠性排序):
1. 标题行含「氨基酸」「脂肪酸」等特征词 → 非主表
2. 表头中非营养字段占比过高 → 非主表
3. 单位标记为 mg/100g 且出现氨基酸名 → 非主表
"""
import re

# 非主表的特征词(出现即判定为附录表)
# ⚠ 注意:不能用宽泛的「脂肪酸」—— 主营养表表头本身就有
#   「饱和脂肪/单不饱和脂肪/多不饱和脂肪」,会误伤主表(实测把 vol1 主表
#   从 196 页砍到 84 页)。必须用**整表标题级**的特征词。
NON_MAIN_PATTERNS = [
    # 氨基酸表:标题级特征
    r"食物氨基酸含量", r"氨基酸含量",
    r"含硫氨基酸", r"芳香族氨基酸",
    r"异亮氨酸", r"亮氨酸", r"赖氨酸", r"蛋氨酸", r"胱氨酸",
    r"苯丙氨酸", r"酪氨酸", r"苏氨酸", r"色氨酸", r"缬氨酸",
    r"谷氨酸", r"天冬氨酸", r"丝氨酸", r"甘氨酸", r"组氨酸",
    r"精氨酸", r"丙氨酸", r"脯氨酸",
    # 脂肪酸表:标题级特征(具体碳链脂肪酸名,非"饱和脂肪"这种泛称)
    r"食物脂肪酸含量", r"脂肪酸含量",
    r"月桂酸", r"肉豆蔻酸", r"棕榈酸", r"硬脂酸", r"亚油酸", r"亚麻酸",
    r"花生四烯酸", r"\bSFA\b", r"\bMUFA\b", r"\bPUFA\b",
    # 样品描述表
    r"样品描述", r"采样日期", r"采样地点", r"数据来源", r"食物描述",
]

# 主营养表应有的核心字段(至少要命中几个)
CORE_FIELDS = {
    "energy_kcal", "energy_kj", "protein_g", "fat_g", "carb_g",
    "water_g", "fiber_g", "ash_g", "cholesterol_mg",
    "calcium_mg", "iron_mg", "vit_a_ug", "thiamin_mg", "niacin_mg",
}

NON_MAIN_C = [re.compile(p, re.I) for p in NON_MAIN_PATTERNS]


def is_non_main_table(page_rows, header_scan=14):
    """判断该页是否为附录表(氨基酸/脂肪酸/样品描述等)。

    返回 (是否附录表, 命中的特征词或 None)
    """
    texts = []
    for row in page_rows[:header_scan]:
        for it in row:
            t = it["t"].strip()
            if t:
                texts.append(t)
    blob = " ".join(texts)
    for rx in NON_MAIN_C:
        m = rx.search(blob)
        if m:
            return True, m.group(0)
    return False, None


def main_table_confidence(page_rows, header_scan=14):
    """主表置信度:表头区命中的核心营养字段数。"""
    from anchor3 import hits_in
    from anchor6 import en_hits
    from vote import page_tokens
    toks = page_tokens(page_rows, header_scan=header_scan)
    fields = set()
    for _, ks in toks:
        fields.update(ks)
    return len(fields & CORE_FIELDS)


def should_process(page_rows, header_scan=14, min_core=2):
    """最终判定:该页是否应作为主营养表抽取。

    规则:
    1. 命中附录表特征词 → 不处理
    2. 核心营养字段命中数 < min_core → 不处理(表头不可信)
    """
    non_main, hit = is_non_main_table(page_rows, header_scan)
    if non_main:
        return False, f"附录表({hit})"
    conf = main_table_confidence(page_rows, header_scan)
    if conf < min_core:
        return False, f"核心字段不足({conf})"
    return True, f"主表(conf={conf})"
