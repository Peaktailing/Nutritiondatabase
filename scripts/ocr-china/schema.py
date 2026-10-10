"""《中国食物成分表(标准版)第6版》31 项营养字段定义 —— 依据绪论「食物成分分析」表整理。

原书表头(以每 100g 可食部计):
食物编码 Food code | 食物名称 Food name | 食物分类 Food category
能量kcal | 蛋白质g | 能量kJ | 蛋白质% | 脂肪g | 脂肪%
饱和脂肪g | 单不饱和脂肪g | 多不饱和脂肪g
碳水化合物g | 膳食纤维g | 胆固醇mg | 灰分g
维生素A μgRAE | β-胡萝卜素μg | 硫胺素mg | 核黄素mg | 烟酸mg | 维生素C mg | 维生素E mg
α-生育酚当量mg | 钙mg | 磷mg | 钾mg | 钠mg | 镁mg | 铁mg | 锌mg | 硒μg | 铜mg | 锰mg | 碘μg
"""

# key, 中文名, 英文名, 单位, 数据类型, 分组
NUTRIENT_FIELDS = [
    # —— 能量 ——
    ("energy_kcal",      "能量",             "Energy",        "kcal", "number", "能量"),
    ("energy_kj",        "能量",             "Energy",        "kJ",   "number", "能量"),
    # —— 蛋白质 ——
    ("protein_g",        "蛋白质",           "Protein",       "g",    "number", "蛋白质"),
    ("protein_pct",      "蛋白质",           "Protein",       "%",    "number", "蛋白质"),
    # —— 脂肪 ——
    ("fat_g",            "脂肪",             "Fat",           "g",    "number", "脂肪"),
    ("fat_pct",          "脂肪",             "Fat",           "%",    "number", "脂肪"),
    ("fat_sat_g",        "饱和脂肪",         "SFA",           "g",    "number", "脂肪"),
    ("fat_mono_g",       "单不饱和脂肪",     "MUFA",          "g",    "number", "脂肪"),
    ("fat_poly_g",       "多不饱和脂肪",     "PUFA",          "g",    "number", "脂肪"),
    # —— 碳水化合物 ——
    ("carb_g",           "碳水化合物",       "Carbohydrate",  "g",    "number", "碳水化合物"),
    ("fiber_g",          "膳食纤维",         "Dietary fiber", "g",    "number", "碳水化合物"),
    # —— 脂质 / 矿物质相关 ——
    ("cholesterol_mg",   "胆固醇",           "Cholesterol",   "mg",   "number", "其他"),
    ("ash_g",            "灰分",             "Ash",           "g",    "number", "其他"),
    # —— 维生素 ——
    ("vit_a_ug",         "维生素A",          "Vitamin A",     "μgRAE", "number", "维生素"),
    ("beta_carotene_ug", "β-胡萝卜素",       "β-Carotene",    "μg",   "number", "维生素"),
    ("thiamin_mg",       "维生素B1(硫胺素)", "Thiamin",       "mg",   "number", "维生素"),
    ("riboflavin_mg",    "维生素B2(核黄素)", "Riboflavin",    "mg",   "number", "维生素"),
    ("niacin_mg",        "烟酸",             "Niacin",        "mg",   "number", "维生素"),
    ("vit_c_mg",         "维生素C",          "Vitamin C",     "mg",   "number", "维生素"),
    ("vit_e_mg",         "维生素E",          "Vitamin E",     "mg",   "number", "维生素"),
    ("vit_e_te_mg",      "α-生育酚当量",     "α-TE",          "mg",   "number", "维生素"),
    # —— 矿物质 ——
    ("calcium_mg",       "钙",               "Calcium",       "mg",   "number", "矿物质"),
    ("phosphorus_mg",    "磷",               "Phosphorus",    "mg",   "number", "矿物质"),
    ("potassium_mg",     "钾",               "Potassium",     "mg",   "number", "矿物质"),
    ("sodium_mg",        "钠",               "Sodium",        "mg",   "number", "矿物质"),
    ("magnesium_mg",     "镁",               "Magnesium",     "mg",   "number", "矿物质"),
    ("iron_mg",          "铁",               "Iron",          "mg",   "number", "矿物质"),
    ("zinc_mg",          "锌",               "Zinc",          "mg",   "number", "矿物质"),
    ("selenium_ug",      "硒",               "Selenium",      "μg",   "number", "矿物质"),
    ("copper_mg",        "铜",               "Copper",        "mg",   "number", "矿物质"),
    ("manganese_mg",     "锰",               "Manganese",     "mg",   "number", "矿物质"),
    ("iodine_ug",        "碘",               "Iodine",        "μg",   "number", "矿物质"),
]

# 数据符号含义(原书「数据符号及缩写说明」)
SYMBOL_MEANING = {
    "x":  "代表值,几条相同食物数据计算的中位数值或均数",
    "Tr": "未检出或微量,低于目前应用的检测方法的检出线或未检出",
    "(0)": "估计值,理论上为0但测不到,或测定后为0",
    "*":  "参考相应食物或原料数据计算而得或参考值",
    "—":  "未检测,理论上食物中应该存在一定量的该种成分,但未实际检测",
    "un": "不能计算,或未测定",
}

# 食物大类(第一册 植物性食物)
VOL1_CATEGORIES = [
    "谷薯类", "豆类及豆制品", "薯类", "坚果、种子类",
    "蔬菜类", "水果类", "菌藻类", "油脂类",
]

# 第二册 动物性食物
VOL2_CATEGORIES = [
    "畜禽肉及制品", "蛋类及制品", "鱼虾蟹贝类",
]
