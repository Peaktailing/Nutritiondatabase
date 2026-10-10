#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
建立「并排式」跨库视图层 —— 不合并任何食物实体，各来源独立成列，统一到公制。

设计原则（2026-10-04 用户决策）：
  1. **不合并**：不做跨库食物实体匹配。各国食物保持各自独立的记录，
     只在「同一分类分段」内按名称排列展示，绝不假设「苹果=Apple」。
  2. **统一公制**：所有质量类单位统一到 g / mg / μg（1 mg = 0.001 g）。
     非质量单位（IU / kJ / pH 等）保留原值并显式标注，不做伪换算。
  3. **来源可溯**：每行都带 source 与 source_id，能追回原始记录。

产出表：
  norm_food        各库食物的「并排索引」条目（统一分类分段 + 名称 + 状态）
  norm_nutrient    营养素主数据（统一 key / 中文名 / 公制单位）
  norm_value       长表事实：norm_food_id + nut_key + 数值 + 单位（已公制换算）
  v_source_by_cat  按分类分段 × 来源 并排展示视图
"""
import sqlite3
import re
import os
import os as _os
import sys as _sys

# 仓库根目录（本文件位于 <root>/scripts/normalize/build_norm.py）
ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(
    _os.path.abspath(__file__))))

DB = _os.environ.get("FDC_DB", _os.path.join(ROOT, "nutrition.db"))
SEA = os.path.join(ROOT, "intl_sea")

# ---------------------------------------------------------------- 公制换算
# 质量单位 → 以 g 为基准
MASS_TO_G = {
    "g": 1.0, "G": 1.0, "mg": 0.001, "MG": 0.001,
    "ug": 1e-6, "μg": 1e-6, "mcg": 1e-6, "UG": 1e-6, "MCG": 1e-6,
    "ng": 1e-9,
}
# 能量单位（单独归一，不与质量混用）
ENERGY_MJ = {"kcal": 1.0, "KCAL": 1.0, "kj": 1.0, "kJ": 1.0}

# ---------------------------------------------------------------- 营养素主数据
# nut_key, 中文名, 公制单位, 类型
NUTRIENTS = [
    ("water",        "水分",       "g",  "macro"),
    ("energy",       "能量",       "kcal","energy"),
    ("protein",      "蛋白质",     "g",  "macro"),
    ("fat",          "脂肪",       "g",  "macro"),
    ("saturated_fat","饱和脂肪",   "g",  "macro"),
    ("carbohydrate", "碳水化合物", "g",  "macro"),
    ("fiber",        "膳食纤维",   "g",  "macro"),
    ("sugar",        "糖",         "g",  "macro"),
    ("cholesterol",  "胆固醇",     "mg", "lipid"),
    ("calcium",      "钙",         "mg", "mineral"),
    ("phosphorus",   "磷",         "mg", "mineral"),
    ("potassium",    "钾",         "mg", "mineral"),
    ("sodium",       "钠",         "mg", "mineral"),
    ("magnesium",    "镁",         "mg", "mineral"),
    ("iron",         "铁",         "mg", "mineral"),
    ("zinc",         "锌",         "mg", "mineral"),
    ("selenium",     "硒",         "μg", "trace"),
    ("copper",       "铜",         "mg", "trace"),
    ("manganese",    "锰",         "mg", "trace"),
    ("vitamin_c",    "维生素C",    "mg", "vitamin"),
    ("vitamin_a",    "维生素A",    "μg", "vitamin"),
    ("vitamin_e",    "维生素E",    "mg", "vitamin"),
    ("thiamin",      "硫胺素",     "mg", "vitamin"),
    ("riboflavin",   "核黄素",     "mg", "vitamin"),
    ("niacin",       "烟酸",       "mg", "vitamin"),
    ("folate",       "叶酸",       "μg", "vitamin"),
    ("vitamin_b12",  "维生素B12",  "μg", "vitamin"),
    ("vitamin_d",    "维生素D",    "μg", "vitamin"),
    ("vitamin_k",    "维生素K",    "μg", "vitamin"),
]

# ---------------------------------------------------------------- 分类分段映射
# 统一分段（跨库并列展示的「货架」）。各库分类 → 统一分段
CANON_CAT = [
    ("dairy_egg",  "乳蛋类"),
    ("meat",       "肉类"),
    ("fish",       "水产"),
    ("vegetable",  "蔬菜"),
    ("fruit",      "水果"),
    ("grain",      "谷类"),
    ("legume",     "豆类"),
    ("nut_seed",   "坚果种子"),
    ("oil_fat",    "油脂"),
    ("sugar",      "糖类"),
    ("beverage",   "饮料"),
    ("seasoning",  "调味品"),
    ("snack",      "零食"),
    ("baby",       "婴幼儿"),
    ("other",      "其他"),
]

# 各库分类关键词 → 统一分段（关键词小写匹配）
CAT_RULES = {
    # CN 有两套分类词表（同一版书、整理路径不同）：
    #   早期整理版 细分三级：「畜肉类及其制品-猪」「蔬菜类及其制品-茄果瓜菜类」
    #   OCR 抽取版 粗分二级：「畜禽肉及制品」「蔬菜类」「谷薯类」
    # 两套都必须能命中，否则合并后 1,831 条里会有一批掉进 other。
    "CN": [
        ("dairy_egg",  ["乳类", "蛋类"]),
        ("meat",       ["畜禽肉", "畜肉", "禽肉", "羊肉", "猪肉", "牛肉",
                        "兔肉", "马肉", "驴肉"]),
        ("fish",       ["鱼虾", "鱼、虾", "蟹贝", "贝类"]),
        ("vegetable",  ["蔬菜", "菌藻", "野葱", "水生蔬菜"]),
        ("fruit",      ["水果"]),
        ("grain",      ["谷薯", "谷类", "薯类"]),
        ("legume",     ["干豆", "鲜豆", "豆类"]),
        ("nut_seed",   ["坚果", "种子", "瓜子"]),
        ("oil_fat",    ["植物油", "动物油脂", "油脂"]),
        ("snack",      ["其他类", "药食两用", "其他("]),
    ],
    "UK": [],   # 特殊：group 是纯字母码，走 UK_GROUP_MAP
    # 印尼 TKPI：原始表无分类字段，全部按名称判定（印尼语）
    # 注意规则表按优先级从上到下匹配，粒度必须由细到粗：
    # 「tahu」（豆腐）必须先于「biji」等被 legume 命中，故豆类放在坚果之前。
    "ID": [
        ("legume",     ["kacang", "kedelai", "tauge", "tempe", "oncom", "tahu"]),
        ("nut_seed",   ["kacang tanah", "bijiapis", "biji kencur", "wijen"]),
        ("dairy_egg",  ["susu", "telur", "mentega", "keju", "krim", "yoghurt",
                        "baksosusu", "santan"]),
        ("meat",       ["daging", "ayam", "bebek", "sapi", "kambing", "babi",
                        "rusuk", "sosis", "bakso", "dok", "tetris", "buntut"]),
        ("fish",       ["ikan", "udang", "kepiting", "kerang", "cumi", "squid",
                        "lobster", "kakap", "tenggiri", "kembung", "layur"]),
        ("vegetable",  ["sayur", "bayam", "kangkung", "wortel", "kentang", "bawang",
                        "tomat", "timun", "terong", "labu", "brokoli", "kol",
                        "selada", "pakis", "buncis", "kaktus", "petai"]),
        ("fruit",      ["buah", "apel", "jeruk", "pisang", "mangga", "semangka",
                        "melon", "anggur", "pir", "salak", "rambutan", "duku",
                        "nanas", "pepaya", "jambu", "belimbing"]),
        ("grain",      ["beras", "nasi", "lontong", "bubur", "roti", "mie",
                        "spaghetti", "pasta", "biskuit", "kue", "porridge",
                        "singkong", "ketan", "jagung", "gandum", "terigu"]),
        ("oil_fat",    ["minyak", "lemak", "margarin", "goreng", "santan"]),
        ("sugar",      ["gula", "manis", "cokelat", "permen"]),
        ("beverage",   ["minuman", "air", "teh", "kopi", "jus", "sari buah",
                        "bir", "anggur jamur"]),
        ("seasoning",  ["bumbu", "garam", "kecap", "saus", "cuka", "merica"]),
    ],
    # 注：CIQUAL 的 alim_grp_nom_eng 字段是**英文**，故关键词用英文
    "FR": [
        ("dairy_egg",  ["milk", "cheese", "egg", "cream", "butter", "yoghurt", "dairy"]),
        ("meat",       ["meat", "beef", "pork", "poultry", "chicken", "ham", "bacon",
                        "charcuterie", "lamb", "veal", "offal", "game"]),
        ("fish",       ["fish", "seafood", "crustacean", "mollusc", "tuna", "salmon",
                        "cod", "anchov", "sardine"]),
        ("vegetable",  ["vegetable", "vegetal", "carrot", "potato", "onion", "garlic",
                        "salad", "spinach", "tomato", "soup"]),
        ("fruit",      ["fruit", "orange", "apple", "banana", "lemon", "apricot",
                        "raisin", "grape"]),
        ("grain",      ["cereal", "bread", "pasta", "rice", "flour", "oat", "corn",
                        "maize", "biscuit", "pasta", "semolina"]),
        ("legume",     ["legume", "bean", "pea", "lentil", "pigeon", "soya", "soy"]),
        ("nut_seed",   ["nut", "seed", "almond", "cashew", "pistachio", "hazelnut",
                        "walnut", "peanut"]),
        ("oil_fat",    ["fat", "oil", "margarine"]),
        ("sugar",      ["sugar", "confectionery", "chocolate", "sweet", "jam"]),
        ("beverage",   ["beverage", "drink", "juice", "water", "coffee", "tea", "wine",
                        "beer", "alcohol", "liqueur"]),
        ("seasoning",  ["spice", "herb", "condiment", "sauce", "bouillon", "salt", "vinegar"]),
        ("snack",      ["biscuit", "cake", "pastry", "snack", "chocolate", "sweet",
                        "ice cream", "sorbet", "crisp"]),
        ("baby",       ["baby"]),
        ("other",      ["miscellaneous", "starters", "dishes", "prepared"]),
    ],
    "USDA": None,   # 用 food_category.code 直接映射
    "ASEAN": [
        ("dairy_egg",  ["milk", "dairy", "egg"]),
        ("meat",       ["meat", "pork", "beef", "chicken", "turkey", "lamb", "bacon", "ham", "sausage", "duck"]),
        ("fish",       ["fish", "shellfish", "aquatic", "finfish", "crustacean", "mollusc"]),
        ("vegetable",  ["vegetable", "potato", "tomato", "onion", "carrot", "cabbage", "leaf"]),
        ("fruit",      ["fruit", "banana", "apple", "mango", "melon", "guava",
                        "pineapple", "papaya", "orange", "lemon", "pear", "plum",
                        "grape", "peach", "rambutan", "durian", "lychee"]),
        ("grain",      ["cereal", "grain", "rice", "pasta", "noodle", "bread", "flour", "oat", "corn", "wheat"]),
        ("legume",     ["legume", "bean", "pea", "soy", "lentil", "pulse"]),
        ("nut_seed",   ["nut", "seed", "kernel"]),
        ("oil_fat",    ["fat", "oil", "butter", "margarine", "ghee"]),
        ("sugar",      ["sugar", "confection", "sweet", "syrup", "jelly"]),
        ("beverage",   ["beverage", "drink", "juice", "water", "coffee", "tea", "alcohol", "wine", "beer"]),
        ("seasoning",  ["spice", "condiment", "sauce", "seasoning", "gravy"]),
        ("snack",      ["snack", "biscuit", "cake", "confection", "cra "]),
        ("baby",       ["baby"]),
    ],
    "WAFCT": [
        ("dairy_egg",  ["milk", "dairy", "cheese", "egg", "yoghurt"]),
        ("meat",       ["meat", "beef", "pork", "chicken", "lamb", "goat", "liver", "offal", "steak"]),
        ("fish",       ["fish", "shrimp", "crab", "prawn", "tuna", "ma el", "sardine"]),
        ("vegetable",  ["vegetable", "leafy", "root", "tomato", "onion", "pepper", "cassava", "yam", "plantain"]),
        ("fruit",      ["fruit", "mango", "banana", "orange", "papaw", "guava", "pineapple",
                        "apple", "mangosteen", "soursop", "pawpaw", "tamarind",
                        "lemon", "lime", "grape", "peach", "pear",
                        "plum", "fig", "date", "custard apple", "passion fruit",
                        "pomegranate", "baobab", "cherimoya", "rose apple"]),
        ("grain",      ["cereal", "grain", "rice", "maize", "millet", "sorghum", "bread", "wheat", "pasta", "couscous"]),
        ("legume",     ["legume", "bean", "pea", "groundnut", "soy", "cowpea", "lentil"]),
        ("nut_seed",   ["nut", "seed", "kernel", "groundnut"]),
        ("oil_fat",    ["oil", "fat", "butter", "ghee", "margarine"]),
        ("sugar",      ["sugar", "honey", "syrup"]),
        ("beverage",   ["beverage", "drink", "juice", "beer", "wine", "water", "tea", "coffee"]),
        ("seasoning",  ["spice", "condiment", "sauce", "bouillon", "salt", "seasoning"]),
    ],
    # MEXT 第2章为谷类，其分类词写在名称的［］内（如「 」「水稲穀粒」）
    "JP": [
        ("dairy_egg",  ["乳", "卵", "チーズ", "バター", "ヨーグルト", "練乳"]),        ("meat",       ["肉", "鶏", "豚", "牛", "レバー", "ハム", "ソーセージ",
                        "大型種", "中型種", "乳用肥育", "和牛", "輸入牛", "交雑牛", "ラム", "鹿肉"]),
        ("fish",       ["魚", "イカ", "エビ", "貝", "海産", "タラ", "サケ", "マグロ",
                        "あじ", "さんま", "いか", "えび", "さば", "はまぐり"]),
        ("vegetable",  ["野菜", "葉菜", "根菜", "果菜", "きゅうり", "トマト", "にんじん",
                        "だいこん", "キャベツ", "ほうれん", "レタス", "とうもろこし", "茄子",
                        "白菜", "菠菜", "ねぎ", "じゃがいも"]),
        ("fruit",      ["果物", "フルーツ", "りんご", "みかん", "柑橘", "ぶどう", "桃",
                        "西瓜", "梨", "いちご", "バナナ", "柿", "キウイ", "パイナップル"]),
        ("grain",      ["穀類", "米", "麺", "パン", "麦", "そば", "ごはん", "玄穀",
                        "水稲", "小麦", "大麦", "小麦粉", "即席めん", "中華めん",
                        "うどん", "そうめん", "全粒", "もち米", "きび", "あわ", "ひえ",
                        "キヌア", "アマランサス", "米粉", "マカロニ", "スパゲッティ", "couscous"]),
        ("legume",     ["豆", "大豆", "豌豆", "とうふ", "豆腐", "油揚げ", "豆乳",
                        "落花生", "いんげん", "小豆", "枝豆"]),
        ("nut_seed",   ["堅果", "種子", "ナッツ", "ごま", "アーモンド", "核桃", "かやの実"]),
        ("oil_fat",    ["油脂", "油", "マーガリン", "ラード", "ドレッシング"]),
        ("sugar",      ["砂糖", "甘味", "ショコア", "蜂蜜", "メープル", "キャンディ"]),
        ("beverage",   ["飲料", "酒", "ビール", "茶水", "ソフトドリンク", "ジュース",
                        "サイダー", "ウーロン茶", "緑茶", "コーヒー", "紅茶"]),
        ("seasoning",  ["調味", "香辛料", "塩", "ソース", "味噌", "醤油", "酢", "香辛"]),
        ("snack",      ["零食", "スナック", "菓子", "せんべい", "菓子類"]),
    ],

}

# 英国 CoFID 的 group 列是纯字母码（McCance & Widdowson's 分类体系）
# 实测首字母语义：
UK_GROUP_MAP = {
    "A": "grain",      # 谷物与谷制品
    "B": "oil_fat",    # 烘焙油脂与人造黄油
    "C": "dairy_egg",  # 蛋与蛋制品 / 乳制品
    "D": "vegetable",  # 蔬菜与蔬菜制品
    "E": "vegetable",
    "F": "fruit",      # 水果与果制品
    "G": "nut_seed",   # 坚果与种子
    "H": "seasoning",  # 香辛料与调味品
    "J": "fish",       # 鱼与水产
    "K": "fish",
    "L": "grain",
    "M": "meat",       # 肉类
    "N": "meat",
    "O": "oil_fat",    # 油脂
    "P": "beverage",   # 饮料
    "Q": "snack",      # 复合/即食食品
    "R": "vegetable",
    "S": "sugar",      # 糖与糖制品
    "T": "snack",
    "U": "vegetable",
    "V": "vegetable",
    "W": "seasoning",   # Miscellaneous: 酱料/烘焙粉等（实测样例 Apple sauce、Baking powder、Barbecue sauce）
    "X": "other",
    "Y": "other",
    "Z": "other",
}

# USDA food_category.description → 统一分段
USDA_CAT = {
    100: "dairy_egg", 200: "seasoning", 300: "baby", 400: "oil_fat",
    500: "meat", 600: "seasoning", 700: "meat", 800: "grain",
    900: "fruit", 1000: "meat", 1100: "vegetable", 1200: "nut_seed",
    1300: "meat", 1400: "beverage", 1410: "beverage", 1500: "fish",
    1600: "legume", 1700: "meat", 1800: "grain", 1900: "sugar",
    2000: "grain", 2100: "snack", 2200: "snack", 2500: "snack",
    2600: "other", 3500: "other", 3600: "snack", 4500: "snack",
}

# 东盟 ASEAN FCD 的 group 形如 "D Vegetables and products (continued)"，
# 首字母是 INFOODS 食物组码。字母码比描述更稳定（描述有 "(continued)" 等变体），
# 故优先用字母映射，未命中再退回描述关键词匹配。
ASEAN_GROUP_MAP = {
    "A": "grain",      # Cereals and products
    "B": "vegetable",  # Starchy roots, tubers and products
    "C": "legume",     # Legumes, nuts, seeds and products
    "D": "vegetable",  # Vegetables and products
    "E": "fruit",      # Fruits and products
    "F": "meat",       # Meat, other animals and products
    "G": "fish",       # Finfish, shellfish, other aquatic animals
    "H": "dairy_egg",  # Eggs and products
    "J": "dairy_egg",  # Milk and products
    "K": "oil_fat",    # Fats and oils
    "M": "sugar",      # Sugar, syrup and confectionery
    "N": "seasoning",  # Spices and condiments
    "P": "beverage",   # Beverages, alcoholic
    "Q": "beverage",   # Beverages, nonalcoholic
    "S": "snack",      # Fast foods: franchise foods
    "T": "other",      # Mixed food dishes
    "U": "other",      # Miscellaneous
}

# 印尼 TKPI 无分类字段，按名称不可得 → 全部标 other（诚实标注）
CANON_CAT_NAME = {k: n for k, n in CANON_CAT}


def _kw_hit(s, kw):
    """词边界关键词匹配。

    不能用裸 `kw in s`：实测会踩两类子串陷阱——
      pear(梨) 含 pea(豌豆) → 果蔬组把梨误判成豆类
      bayam(菠菜) 含 ayam(鸡) → 印尼把菠菜误判成肉类
    故对拉丁字母关键词要求左右是非字母字符。
    """
    kw = kw.lower()
    if not kw[0].isascii() or not kw[-1].isascii():
        return kw in s                      # 非拉丁文（中文/日文）无此问题
    i = s.find(kw)
    while i != -1:
        before = s[i - 1] if i > 0 else " "
        after = s[i + len(kw)] if i + len(kw) < len(s) else " "
        if not before.isalpha() and not after.isalpha():
            return True
        i = s.find(kw, i + 1)
    return False


def canon_cat(source, raw_cat, food_name=None):
    """把各库原始分类映射到统一分段。无法判定返回 'other'。"""
    # 英国 CoFID：group 是纯字母码，走专用映射
    if source == "UK":
        if not raw_cat:
            return "other"
        return UK_GROUP_MAP.get(str(raw_cat)[0].upper(), "other")
    # 东盟：group 是「字母码 + 描述」，字母码更稳定，优先用字母
    if source == "ASEAN":
        if raw_cat:
            hit = ASEAN_GROUP_MAP.get(str(raw_cat).strip()[0].upper())
            if hit:
                return hit
        if not raw_cat:
            raw_cat = food_name
    if not raw_cat:
        raw_cat = food_name        # 无分类字段的库退化为按名称判定
    if not raw_cat:
        return "other"
    # CIQUAL 只有 11 个粗粒度大组，其中两组把多个大类混在一起，必须组内按名称细分
    if source == "FR" and food_name:
        grp = str(raw_cat).lower()
        if grp.startswith("meat, egg and fish"):
            return _fr_sub_meat_egg_fish(food_name)
        if grp.startswith("fruits, vegetables, legumes and nuts"):
            return _fr_sub_fruit_veg_legume_nut(food_name)
    s = str(raw_cat).lower()
    rules = CAT_RULES.get(source, [])
    for cat, kws in rules:
        for kw in kws:
            if _kw_hit(s, kw):
                return cat
    return "other"


def _fr_sub_meat_egg_fish(name):
    """CIQUAL「meat, egg and fish」组内细分（791 条）。
    该组把水产/肉/蛋混在一起，只能按英文名称判定。"""
    s = name.lower()
    for kw in FR_FISH_KW:
        if _kw_hit(s, kw):
            return "fish"
    for kw in FR_EGG_KW:
        if _kw_hit(s, kw):
            return "dairy_egg"
    return "meat"          # 组内主体确为肉类


def _fr_sub_fruit_veg_legume_nut(name):
    """CIQUAL「fruits, vegetables, legumes and nuts」组内细分（653 条）。"""
    s = name.lower()
    for kw in FR_NUT_KW:
        if _kw_hit(s, kw):
            return "nut_seed"
    for kw in FR_LEGUME_KW:
        if _kw_hit(s, kw):
            return "legume"
    for kw in FR_VEG_KW:
        if _kw_hit(s, kw):
            return "vegetable"
    return "fruit"         # 组内主体确为水果


# CIQUAL 组内细分关键词（按细分优先级排列，不依赖原规则表的顺序）
FR_FISH_KW = [
    "fish", "salmon", "mackerel", "herring", "sardine", "pilchard", "anchov",
    "tuna", "cod", "sole", "haddock", "halibut", "trout", "bass", "bream",
    "shrimp", "prawn", "crab", "lobster", "crayfish", "mussel", "oyster",
    "squid", "octopus", "cuttlefish", "eel", "monkfish", "tilapia",
    "shark", "ray", "surimi", "roe", "caviar", "anchovy",
]
FR_EGG_KW = ["egg", "mayonnaise", "meringue", "mousse", "omelette", "omelet"]
FR_NUT_KW = [
    "almond", "cashew", "walnut", "hazelnut", "pistachio", "pecan", "macadamia",
    "chestnut", "brazil", "peanut", "sunflower seed", "pumpkin seed", "sesame",
    "poppy seed", "mixed nuts", "dried fruit", "fruit, dried", "candied",
]
FR_LEGUME_KW = [
    "bean", "pea", "lentil", "chickpea", "pigeon", "soya", "soy", "broad bean",
    "flageolet", "haricot", "kidney bean", "green bean", "french bean",
]
FR_VEG_KW = [
    "potato", "tomato", "carrot", "onion", "garlic", "leek", "celery", "cucumber",
    "courgette", "zucchini", "pepper", "cabbage", "cauliflower", "broccoli",
    "sprout", "spinach", "lettuce", "endive", "chicory", "watercress",
    "radish", "turnip", "parsnip", "carrot", "beetroot", "swede", "kohlrabi",
    "artichoke", "cardoon", "celeriak", "celeriac", "salsify", "chayote",
    "asparagus", "squash", "pumpkin", "marrow", "okra", "mushroom",
    "shallot", "chicory", "dandelion", "corn salad", "seaweed", "olive",
    "french fries", "chips", "mashed potato", "baked potato", "boiled potato",
]


# 印尼语状态词：TKPI 名称格式为「名称, 加工状态」，后段直接给出状态
# （如 "Ikan bader, segar"=新鲜、"Beras merah,_INST"=生米、"Ketan, pulen"=煮熟）
ID_RAW = re.compile(r'\b(segar|mentah|raw|alami)\b', re.I)
ID_COOK = re.compile(
    r'\b(matang|cooked|dimasak|rebus|goreng|bakar|tinggal\s*air|'
    r'siap\s*dikonsumsi|pulen|nasi\s*putih\s*panen)\b', re.I)
ID_PROC = re.compile(
    r'\b(kering|_INST|instan|gandum|serbuk|bubuk|konserv|asin|dalam\s*kalenteng|'
    r'roti\s*bakar|biskuit|nugget|sosis)\b', re.I)


def id_state(name):
    """印尼语名称的状态判定。返回 (state, basis)。"""
    if not name:
        return "unknown", "no_name"
    if ID_PROC.search(name):
        return "processed", "name:id_processing"
    if ID_COOK.search(name):
        return "cooked", "name:id_cooking"
    if ID_RAW.search(name):
        return "raw", "name:id_raw"
    return "unknown", "name:id_unparsed"


def to_metric(val, unit):
    if val is None:
        return None, None
    u = (unit or "").strip()
    if u in MASS_TO_G:
        return float(val) * MASS_TO_G[u], "g"
    return None, None


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    # 关键：先脱离事务设 PRAGMA，再插入；否则 synchronous=OFF 不生效于已有事务
    con.isolation_level = None
    cur.execute("PRAGMA journal_mode=MEMORY")
    cur.execute("PRAGMA synchronous=OFF")
    cur.execute("PRAGMA cache_size=-200000")

    # ---------------- 清理旧版
    # 必须先查 sqlite_master 判类型：SQLite 的 `DROP VIEW IF EXISTS x` 在 x
    # 实际是 TABLE 时会直接抛 "use DROP TABLE to delete table"，不会像
    # `DROP TABLE IF EXISTS` 那样兼容 VIEW。norm_value 早期是视图、后改为
    # 实表，所以这里显式分流。
    for t in ("norm_value", "norm_food", "norm_nutrient", "v_source_by_cat"):
        typ = cur.execute(
            "SELECT type FROM sqlite_master WHERE name=?", (t,)).fetchone()
        if typ:
            cur.execute(f"DROP {typ[0].upper()} IF EXISTS {t}")
        else:
            cur.execute(f"DROP VIEW IF EXISTS {t}")
            cur.execute(f"DROP TABLE IF EXISTS {t}")

    # ---------------- 1. 营养素主数据
    cur.execute("""
        CREATE TABLE norm_nutrient (
            nut_key  TEXT PRIMARY KEY,
            nut_cn   TEXT,
            unit     TEXT,          -- 统一后的公制单位
            ntype    TEXT,
            sort_order INTEGER
        )""")
    cur.executemany(
        "INSERT INTO norm_nutrient VALUES (?,?,?,?,?)",
        [(k, cn, u, t, i) for i, (k, cn, u, t) in enumerate(NUTRIENTS)])
    print(f"norm_nutrient: {len(NUTRIENTS)} 个统一营养素")

    # ---------------- 2. 并排食物索引
    cur.execute("""
        CREATE TABLE norm_food (
            norm_food_id INTEGER PRIMARY KEY,
            source       TEXT NOT NULL,     -- CN/UK/FR/USDA/ASEAN/WAFCT/JP/ID
            source_id    TEXT,              -- 该库原始编码
            name_local   TEXT,              -- 本地语言名称
            name_en      TEXT,              -- 英文名（若有）
            canon_cat    TEXT,              -- 统一分类分段
            cat_raw      TEXT,              -- 该库原始分类
            state        TEXT,              -- raw/cooked/dried/concentrated/canned/salted/unknown
            state_basis  TEXT,              -- 状态判定依据
            kcal         REAL,              -- 常用指标冗余（便于排序浏览）
            protein      REAL,
            fat          REAL,
            carb          REAL,
            note         TEXT
        )""")

    COOK = re.compile(r'(烤|烧|炒|煮|蒸|炸|炖|焯|煎|卤|熏|烩|煲|熘)')
    PROC = re.compile(r'(腊|咸肉|咸蛋|盐渍|腌渍|蜜饯|罐头|糖水|干制|脱水|油炸|熏制|酱菜|榨菜|菜干|笋干)')
    # 中国库名称用全角括号显式标注状态：「栗子（熟）」「核桃（干）」「裙边（干）」
    # 这些是明确标记，必须优先于含水量兜底判定，否则「栗子（熟）」会被当成生食。
    CN_BRACKET_STATE = {
        "熟": "cooked", "煮": "cooked", "烤": "cooked", "蒸": "cooked",
        "炒": "cooked", "炸": "cooked", "煎": "cooked", "炖": "cooked",
        "卤": "cooked", "熏": "cooked", "脍": "cooked",
        "干": "dried_or_concentrated", "脱水": "dried_or_concentrated",
        "鲜": "raw", "生": "raw", "冻": "raw",
        "咸": "processed", "腊": "processed", "腌": "processed",
        "酱": "processed", "糖": "processed",
    }

    # 西式烹饪动作词：CoFID / CIQUAL / USDA 的名称是英文，烹饪状态直接写在名字里
    # （如 "Beef, sirloin, grilled"、 "Chicken, boiled"、 "Apple, dried"）
    EN_COOK = re.compile(
        r'\b(grilled?|grilling|roasted?|roasting|baked?|baking|fried|frying|'
        r'boiled|steamed|poached|braised|stewed|simmered|sauteed?|sauted|'
        r'pan[- ]fried|stir[- ]fried|deep[- ]fried|barbecued|bbq|roast|'
        r'canned|tinned|vacuum|dried|dehydrated|smoked|salted|pickled|'
        r'marmalade|jam|jelly|toast|biscuit|cake|pasteuris\w+|sterilis\w+|'
        r'UHT|concentrat\w+|powder|extract|concentrate)\b', re.I)
    EN_RAW = re.compile(r'\b(raw|fresh|uncooked|plain|unprepared|lean|skinless)\b', re.I)
    EN_PROC = re.compile(
        r'\b(canned|tinned|smoked|salted|pickled|marmalade|jam|jelly|'
        r'toast|biscuit|cake|pasteuris\w+|sterilis\w+|UHT|concentrat\w+|powder)\b', re.I)

    def en_state(name):
        """英文名的状态判定。返回 (state, basis)，无法判定为 unknown。"""
        if not name:
            return "unknown", "no_name"
        if EN_PROC.search(name):
            return "processed", "name:en_processing"
        if EN_COOK.search(name):
            return "cooked", "name:en_cooking"
        if EN_RAW.search(name):
            return "raw", "name:en_raw"
        return "unknown", "name:en_unparsed"

    def cn_state(name, water):
        # 优先级：名称括号内显式状态 > 烹饪动作词 > 加工保藏词 > 含水量兜底
        if name:
            m = re.findall(r'[（(]([^（()）]{1,4})[)）]', name)
            for tok in m:
                for k, st in CN_BRACKET_STATE.items():
                    if k in tok:
                        return st, f"name:bracket[{tok}]"
            if COOK.search(name):
                return "cooked", "name:cooking"
            if PROC.search(name):
                return "processed", "name:processing"
        if water is not None and water <= 15:
            return "dried_or_concentrated", "water<=15%"
        return "raw", "default:raw"

    rows = []

    # --- 中国 FCT（两版合并表，见 scripts/import/merge_china_ocr.py）
    # 1,831 条 = OCR 抽取 1,810 + 早期整理版补缺 21。
    # 早期整理版独有的 39 条「代表值估算」不进并排层（隔离在
    # china_food_synthetic），它们是整理时合成的估算值，不是原书条目。
    for code, name, en, cat, water, kcal, pro, fat, cho in cur.execute("""
        select food_code, food_name, english_name, category, water_g,
               energy_kcal, protein_g, fat_g, carb_g
        from china_food_merged"""):
        st, basis = cn_state(name, water)
        rows.append(("CN", code, name, en,
                     canon_cat("CN", cat), cat, st, basis, kcal, pro, fat, cho,
                     None))

    # --- 英国 CoFID
    # 注意：CoFID 表是「每食物 × 每 sheet 一行」，34,644 行但仅 2,886 个唯一
    # food_code。并排层必须按 food_code 去重（取并集），否则同一食物重复出现。
    for code, name, grp, kcal, pro, fat, cho in cur.execute("""
        select food_code,
               max(food_name), max("group"),
               max(energy_kcal__kcal), max(protein__g), max(fat__g), max(carbohydrate__g)
        from uk_cofid_food group by food_code"""):
        st, basis = en_state(name)
        rows.append(("UK", code, name, None,
                     canon_cat("UK", grp), grp, st, basis, kcal, pro, fat, cho, None))

    # --- 法国 CIQUAL
    for code, name, grp, kcal, pro, fat, cho in cur.execute("""
        select alim_code, alim_nom_eng, alim_grp_nom_eng,
               energy_regulation_eu_no_1169_2011__kcal_100g,
               protein__g_100g, fat__g_100g, carbohydrate__g_100g
        from ciqual_food"""):
        st, basis = en_state(name)
        rows.append(("FR", code, name, None,
                     canon_cat("FR", grp, name), grp, st, basis,
                     kcal, pro, fat, cho, None))

    # --- USDA（用 food_category.code 分段；只取可与单食材比对的类型）
    # 注意：data_type 无索引，直接 join 210 万行的 food 会极慢（全表扫描）。
    # 实测：先取 fdc_id 列表再批量查营养素 = 3.3s；直接 4 表 join > 100s。
    _ids = [r[0] for r in cur.execute(
        "select fdc_id from food where data_type in "
        "('foundation_food','sr_legacy_food','survey_fndds_food')")]
    _nut = {}
    if _ids:
        _q = ("select fdc_id, nutrient_id, amount from food_nutrient "
              f"where fdc_id in ({','.join('?' * len(_ids))}) "
              "and nutrient_id in (1003,1004,1005,1008)")
        for _fid, _nid, _amt in cur.execute(_q, _ids):
            _nut.setdefault(_fid, {})[_nid] = _amt
    for fid, desc, catcode in cur.execute("""
        select f.fdc_id, f.description, fc.code
        from food f left join food_category fc on f.food_category_id = fc.id
        where f.data_type in ('foundation_food','sr_legacy_food','survey_fndds_food')"""):
        n = _nut.get(fid, {})
        cc = USDA_CAT.get(catcode, "other") if catcode else "other"
        st, basis = en_state(desc)
        rows.append(("USDA", str(fid), desc, desc, cc, str(catcode), st,
                     basis, n.get(1008), n.get(1003), n.get(1004),
                     n.get(1005), "USDA 基础层（单食材）"))

    # --- 东盟 FCD
    for code, name, grp, kcal, pro, fat, cho in cur.execute("""
        select food_code, food_name, "group", energy_kcal, PROCNT, FAT, CHOAVLDF
        from asean_fcd_2014"""):
        st, basis = en_state(name)
        rows.append(("ASEAN", code, name, None,
                     canon_cat("ASEAN", grp), grp, st, basis, kcal, pro, fat, cho, None))

    # --- FAO 西非（无分类字段，按食物名判定；名字含菜谱描述的归 other）
    for code, name, kcal, pro, fat, cho in cur.execute("""
        select Code, Food_name_in_English, ENERC, PROTCNT, FAT, CHOAVLDF
        from fao_wafct_food where _is_food=1"""):
        st, basis = en_state(name)
        rows.append(("WAFCT", code, name, name, canon_cat("WAFCT", None, name),
                     None, st, basis, kcal, pro, fat, cho, None))

    # --- 日本 MEXT
    for num, name, kcal, pro, fat, cho in cur.execute("""
        select food_number, food_name, "ENERC_KCAL", "PROT-", "FAT-", "CHOAVLDF-"
        from jp_mext_food"""):
        st = "cooked" if re.search(r'(煮|焼|揚|炒|蒸|Fried|Boiled|grilled)', name) else "raw"
        rows.append(("JP", num, name, None, canon_cat("JP", None, name), None, st,
                     "jp:heuristic", kcal, pro, fat, cho, None))

    # --- 印尼 TKPI：原始表无名称，已补入名称表（1146/1146 全覆盖）
    _id_name = {}
    try:
        import pandas as _pd
        _nm = _pd.read_csv(os.path.join(SEA, "id_tkpi_2017_names.csv"))
        # 编码格式容错：TKPI 原始码可能有 AP01 / AP001 两种写法
        def _nk(s):
            s = str(s).strip()
            return s[:2] + s[2:].lstrip("0") if len(s) > 2 else s
        _id_name = {_nk(k): v for k, v in zip(_nm["KODE"], _nm["NAMA_BAHAN"])}
        print(f"  印尼名称表: {len(_id_name):,} 条")
    except Exception as e:
        print(f"  [警告] 印尼名称表读取失败（{e}），名称将为空")
    for code, kcal, pro, fat, cho in cur.execute("""
        select food_code, energy_kcal, protein_g, fat_g, carbohydrate_g from id_tkpi_food"""):
        nm = _id_name.get(_nk(code))
        st, basis = id_state(nm)
        rows.append(("ID", code, nm, None, canon_cat("ID", None, nm), None, st, basis,
                     kcal, pro, fat, cho,
                     None if nm else "TKPI 原始数据无食物名与分类"))

    cur.execute("BEGIN")
    cur.executemany("""INSERT INTO norm_food
        (source, source_id, name_local, name_en, canon_cat, cat_raw, state,
         state_basis, kcal, protein, fat, carb, note)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
    # 注意：不能在 COMMIT 之后读 cur.rowcount —— COMMIT 会把 rowcount 重置为
    # 0（曾经因此打印出「norm_food: -1 条」，真实值 27,112）。改用
    # total_changes 差值，这个计数器不受 COMMIT 影响。
    n_food = cur.execute("SELECT count(*) FROM norm_food").fetchone()[0]
    print(f"norm_food: {n_food:,} 条并排食物条目")

    # 插入完成后再建索引（快得多）
    cur.execute("CREATE INDEX idx_nf_src ON norm_food(source)")
    cur.execute("CREATE INDEX idx_nf_cat ON norm_food(canon_cat)")
    cur.execute("CREATE INDEX idx_nf_name ON norm_food(name_local)")
    print("  索引已建立")

    from collections import Counter
    cs = Counter(r[4] for r in rows)
    print("  统一分类分段分布:")
    for k, v in cs.most_common():
        print(f"    {k:<12} {CANON_CAT_NAME.get(k,k):<8} {v:>8,}")
    ss = Counter(r[6] for r in rows)
    print("  状态分布:", dict(ss))

    con.commit()
    con.close()
    print("\n完成。")


if __name__ == "__main__":
    main()
