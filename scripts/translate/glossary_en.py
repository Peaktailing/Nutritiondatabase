#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
英文/拉丁语食物名「实词词典」。

设计说明（改之前请先读）：
  各国数据库的 21,657 条英文名里只有 5,310 个唯一 token，
  且 TOP1200 就覆盖 92% 的词频 —— 所以本方案的性价比远高于逐条 MT：
  一次性给 token 定中文，再按中文语序重组。

三类词条：
  MF  主料本体（beef/potato/chocolate...）    —— 拼到名字核心
  PB  部位补语（short ribs/breast/thigh...）  —— 紧跟主料之后组成「牛短肋」「鸡胸肉」
  SF  后缀（babyfood）                        —— 放全名最后
  其余为修饰类，按 CLS_ORDER 前置，中文语序由权重决定：
  ST 状态(生/冷冻/罐头) → CO 烹饪 → PR 加工保藏 → NU 含量宣称
  → CL 颜色 → CN 国别 → PH 物理形态 → QT 取料部位(瘦/肥/皮)

匹配方式：所有 key 统一把连字符换成空格，按长度降序拼成一个正则 alternation，
一次扫描 —— Python re 对 alternation 取最左成功分支，因此天然「最长短语优先」，
彻底杜绝 whole-wheat 被切成 whole 的问题。

未收录的词不丢弃，原样保留英文，翻译状态记为 partial 以便后续迭代补齐。
"""

# ── 语序权重：数字越小越靠前 ──────────────────────────────────
CLS_ORDER = {"ST": 1, "CO": 2, "PR": 3, "NU": 4, "CL": 5, "CN": 6, "PH": 7, "QT": 8}

# 同类别内部冲突时取 rank 高者（如 "cooked, hard-boiled" → 取水煮不取熟）
WORD_RANK = {
    "raw": 10, "fresh": 4, "frozen": 9, "canned": 9, "dried": 9, "chilled": 3,
    "cooked": 1, "boiled": 5, "hard boiled": 8, "hard boiled egg": 8,
    "soft boiled": 7, "poached": 6, "fried": 7, "deep fried": 8, "pan fried": 7,
    "stir fried": 7, "roasted": 7, "grilled": 7, "broiled": 7, "baked": 6,
    "braised": 6, "stewed": 6, "steamed": 6, "simmered": 6, "sauteed": 6,
    "microwaved": 6, "reheated": 5, "charbroiled": 7, "barbecued": 7,
}

# ── 主料 MF：食物本体 ─────────────────────────────────────────
MF = {
    # 畜肉
    "beef": "牛肉", "veal": "小牛肉", "pork": "猪肉", "lamb": "羊肉",
    "mutton": "羊肉", "goat meat": "山羊肉", "chevon": "山羊肉",
    "horse meat": "马肉", "rabbit meat": "兔肉", "rabbit": "兔肉",
    "venison": "鹿肉", "deer": "鹿肉", "game meat": "野味肉", "bison": "北美野牛肉",
    "buffalo": "水牛肉", "caribou": "驯鹿肉", "elk": "驼鹿肉", "moose": "驼鹿肉",
    "bear": "熊肉", "squirrel": "松鼠肉", "opossum": "负鼠肉", "emu": "鸸鹋肉",
    "kangaroo": "袋鼠肉", "camel": "骆驼肉", "ostrich": "鸵鸟肉", "turtle": "龟肉",
    "frog": "蛙肉", "snail": "蜗牛", "escargot": "蜗牛", "alligator": "短吻鳄肉",
    "crocodile": "鳄鱼肉", "iguana": "鬣蜥肉", "grasshopper": "蚱蜢",
    "silkworm": "蚕蛹", "pigeon": "鸽肉", "squab": "乳鸽肉", "quail": "鹌鹑肉",
    "pheasant": "野鸡肉", "partridge": "鹧鸪肉", "guinea fowl": "珍珠鸡肉",
    "capon": "阉鸡肉", "chicken": "鸡肉", "turkey": "火鸡肉", "duck": "鸭肉",
    "muscovy duck": "番鸭肉", "goose": "鹅肉", "game bird": "野禽肉",
    "stewing chicken": "老母鸡", "giblets": "禽内脏", "meat": "肉",
    "meat substitute": "素肉", "meatless": "素肉", "meat analogue": "素肉",
    "vegetarian": "素食", "mock meat": "素肉", "surimi": "鱼糜",
    "offal": "内脏", "variety meats": "杂碎", "by products": "副产品",

    # 加工肉
    "bacon": "培根", "ham": "火腿", "sausage": "香肠", "salami": "萨拉米肠",
    "pepperoni": "辣香肠", "chorizo": "西班牙辣肠", "bratwurst": "德式烤肠",
    "knockwurst": "德式蒜肠", "frankfurter": "法兰克福肠", "hot dog": "热狗肠",
    "wiener": "维也纳肠", "vienna sausage": "维也纳肠", "bologna": "博洛尼亚肠",
    "mortadella": "摩泰台拉肠", "liverwurst": "肝泥肠", "braunschweiger": "熏肝肠",
    "headcheese": "头肉冻", "scrapple": "玉米肉饼", "kielbasa": "波兰香肠",
    "linguica": "葡萄牙辣肠", "andouille": "安杜耶香肠", "merguez": "梅尔盖兹香肠",
    "pastrami": "烟熏牛肉", "corned beef": "咸牛肉", "jerky": "肉干",
    "pemmican": "肉糜饼", "pate": "肉酱", "terrine": "肉冻糕", "rillettes": "肉酱",
    "luncheon meat": "午餐肉", "deviled ham": "调味火腿", "potted meat": "罐装肉糜",
    "meatballs": "肉丸", "meatloaf": "肉糕", "meat loaf": "肉糕",
    "souse": "肉冻", "blood sausage": "血肠", "chitterlings": "猪小肠",
    "chitlins": "猪小肠", "haslet": "猪内脏糕", "haggis": "羊肚布丁",
    "jowl": "面颊肉", "cheek meat": "面颊肉", "pork rind": "猪皮",
    "cracklings": "油渣", "rashers": "培根片", "lardon": "培根丁",

    # 部位
    "loin": "里脊", "tenderloin": "里脊", "filet": "里脊柳", "fillet steak": "柳",
    "sirloin": "西冷", "porterhouse": "波特豪斯牛排", "t bone": "丁骨排",
    "ribeye": "肋眼", "eye of round": "后腿心", "flank steak": "腹肉牛排",
    "skirt steak": "横膈膜牛排", "hanger steak": "膈柱肌牛排", "flat iron": "平铁牛排",
    "plate": "腹胁肉", "clod": "肩臂肉", "knuckle": "膝圆", "topside": "后腿上部",
    "silverside": "后腿外侧", "rump": "臀肉", "round steak": "后腿肉排",
    "shank": "小腿肉", "oxtail": "牛尾", "tail": "尾", "brisket": "胸肉",
    "carcass": "胴体", "short plate": "短腹胁", "delmonico": "德尔莫尼科牛排",
    "steak": "牛排", "steaks": "牛排", "roast": "烤肉块", "roasts": "烤肉块",
    "chops": "排骨", "chop": "排骨", "cutlet": "肉排", "escalope": "薄肉片",
    "cut": "切块", "cuts": "切块", "joint": "大块肉", "scrag": "颈肉",
    "cannon": "腿部肉", "marrow": "骨髓", "chuck": "肩肉", "blade": "肩胛肉",
    "shoulder": "肩肉", "arm": "前臂肉", "brisket point": "胸尖",

    # 内脏
    "liver": "肝", "heart": "心", "kidney": "腰", "tongue": "舌", "brain": "脑",
    "tripe": "胃", "gizzard": "肫", "spleen": "脾", "lungs": "肺", "lung": "肺",
    "sweetbread": "胰脏", "pancreas": "胰脏", "thymus": "胸腺", "uterus": "子宫",
    "udder": "乳房", "blood": "血", "feet": "蹄", "foot": "蹄", "ears": "耳",
    "snout": "鼻", "neck": "颈", "back": "背", "gizzard": "肫",

    # 水产
    "fish": "鱼", "finfish": "鱼", "seafood": "海鲜", "shellfish": "贝类",
    "crustaceans": "甲壳类", "mollusks": "软体类", "molluscs": "软体类",
    "anchovy": "凤尾鱼", "bass": "鲈鱼", "bluefish": "蓝鲹", "bonito": "鲣鱼",
    "butterfish": "鲳鱼", "carp": "鲤鱼", "catfish": "鲶鱼", "cod": "鳕鱼",
    "croaker": "黄鱼", "drum": "石首鱼", "eel": "鳗鱼", "flounder": "鲆鱼",
    "grouper": "石斑鱼", "haddock": "黑线鳕", "hake": "无须鳕", "halibut": "比目鱼",
    "herring": "鲱鱼", "kingfish": "黄条鰤", "lingcod": "长蛇齿鱼",
    "mackerel": "鲭鱼", "mahimahi": "鲯鳅", "marlin": "枪鱼", "monkfish": "鮟鱇鱼",
    "mullet": "鲻鱼", "orange roughy": "深海鲷", "perch": "鲈鱼", "pike": "梭鱼",
    "plaice": "鲽鱼", "pollock": "狭鳕", "pompano": "鲳鲹", "rockfish": "平鲉",
    "sablefish": "裸盖鱼", "salmon": "三文鱼", "sardine": "沙丁鱼",
    "scup": "尖口鲷", "shad": "鲥鱼", "shark": "鲨鱼", "smelt": "胡瓜鱼",
    "snapper": "笛鲷", "sole": "鳎鱼", "sprat": "黍鲱", "sturgeon": "鲟鱼",
    "swordfish": "剑鱼", "tilapia": "罗非鱼", "tilefish": "方头鱼",
    "trout": "鳟鱼", "tuna": "金枪鱼", "wahoo": "棘鳞蛇鲭", "walleye": "白眼鲈",
    "weakfish": "犬牙石首鱼", "whiting": "牙鳕", "wolffish": "狼鱼",
    "yellowtail": "鰤鱼", "silver hake": "银无须鳕", "bigeye scad": "大眼鲹",
    "horse mackerel": "竹䇲鱼", "blue whiting": "蓝牙鳕", "capelin": "毛鳞鱼",
    "skipjack": "鲣鱼", "yellowfin": "黄鳍金枪鱼", "albacore": "长鳍金枪鱼",
    "bluefin": "蓝鳍金枪鱼", "escolar": "棘鳞蛇鲭", "opah": "月鱼",
    "Spanish mackerel": "大西洋马鲛", "chub mackerel": "鲐鱼", "milkfish": "虱目鱼",
    "pangasius": "巴沙鱼", "basa": "巴沙鱼", "swai": "巴沙鱼",
    "snakehead": "鳢鱼", "gourami": "丝足鲈", "torpedo scad": "圆鲹",
    "shrimp": "虾", "prawn": "对虾", "langoustine": "挪威海螯虾",
    "crayfish": "小龙虾", "lobster": "龙虾", "crab": "蟹", "blue crab": "蓝蟹",
    "dungeness crab": "珍宝蟹", "king crab": "皇帝蟹", "snow crab": "雪蟹",
    "clam": "蛤蜊", "quahog": "圆蛤", "geoduck": "象拔蚌", "oyster": "牡蛎",
    "mussel": "贻贝", "scallop": "扇贝", "abalone": "鲍鱼", "conch": "贝壳螺",
    "whelk": "海螺", "periwinkle": "滨螺", "cockle": "鸟蛤", "squid": "鱿鱼",
    "octopus": "章鱼", "cuttlefish": "乌贼", "sea cucumber": "海参",
    "sea urchin": "海胆", "jellyfish": "海蜇", "roe": "鱼卵", "caviar": "鱼子酱",
    "bottarga": "鱼卵干", "roe deer": "狍肉",
    "fish sticks": "鱼条", "fish fillet": "鱼柳", "fish fillets": "鱼柳",
    "fish cake": "鱼糕", "fish balls": "鱼丸", "fish sauce": "鱼露",
    "fish paste": "鱼酱", "fish roe": "鱼卵",

    # 乳蛋
    "milk": "牛奶", "cow milk": "牛奶", "goat milk": "羊奶", "sheep milk": "绵羊奶",
    "ewe milk": "绵羊奶", "camel milk": "骆驼奶", "dry milk": "奶粉",
    "evaporated milk": "淡奶", "condensed milk": "炼乳", "buttermilk": "酪乳",
    "skim milk": "脱脂奶", "whole milk": "全脂牛奶", "milkfat": "乳脂肪",
    "cream": "奶油", "light cream": "淡奶油", "heavy cream": "重奶油",
    "sour cream": "酸奶油", "whipping cream": "稀奶油", "whipped cream": "搅打奶油",
    "creme fraiche": "法式鲜奶油", "half and half": "半脂奶油", "whey": "乳清",
    "curd": "凝乳", "kefir": "开菲尔", "koumiss": "马奶酒",
    "yogurt": "酸奶", "yoghurt": "酸奶", "labneh": "浓缩酸奶", "lassi": "拉西酸奶饮",
    "egg": "鸡蛋", "eggs": "鸡蛋", "whole egg": "全蛋", "egg white": "蛋清",
    "egg yolk": "蛋黄", "dried egg": "蛋粉", "quail egg": "鹌鹑蛋",
    "duck egg": "鸭蛋", "egg substitute": "代蛋品", "egg nog": "蛋奶酒",
    "butter": "黄油", "margarine": "人造黄油", "butter oil": "乳脂油",
    "clarified butter": "澄清黄油", "ghee": "酥油", "spread": "涂抹酱",
    "cheese": "奶酪", "cheddar cheese": "切达奶酪", "cottage cheese": "白软干酪",
    "cream cheese": "奶油奶酪", "mozzarella cheese": "马苏里拉奶酪",
    "parmesan cheese": "帕玛森奶酪", "swiss cheese": "瑞士奶酪",
    "gouda cheese": "高达奶酪", "brie cheese": "布里奶酪", "feta cheese": "菲达奶酪",
    "blue cheese": "蓝纹奶酪", "provolone cheese": "普罗沃隆奶酪",
    "gruyere cheese": "格鲁耶尔奶酪", "munster cheese": "芒斯特奶酪",
    "ricotta cheese": "里科塔奶酪", "camembert": "卡门贝尔奶酪",
    "emmental": "埃门塔尔奶酪", "roquefort": "洛克福奶酪", "stilton": "斯蒂尔顿奶酪",
    "mascarpone": "马斯卡彭", "quark": "夸克", "cheese food": "再制奶酪",
    "cheese spread": "涂抹奶酪", "processed cheese": "再制奶酪",
    "processed cheese food": "再制奶酪食品", "grana padano": "格拉纳帕达诺奶酪",
    "fromage blanc": "白奶酪", "queso": "奶酪", "queso fresco": "鲜奶酪",

    # 谷物主食
    "rice": "大米", "brown rice": "糙米", "white rice": "白米", "wild rice": "菰米",
    "parboiled rice": "蒸谷米", "glutinous rice": "糯米", "sticky rice": "糯米",
    "basmati rice": "巴斯马蒂米", "jasmine rice": "茉莉香米", "rice noodles": "米粉",
    "rice flour": "米粉", "rice paper": "米纸", "rice bran": "米糠",
    "rice cake": "米糕", "puffed rice": "爆米花米", "rice pilaf": "手抓饭",
    "bread": "面包", "white bread": "白面包", "whole wheat bread": "全麦面包",
    "rye bread": "黑麦面包", "pumpernickel bread": "粗黑麦面包", "pita bread": "皮塔饼",
    "french bread": "法式面包", "italian bread": "意式面包", "sourdough": "酸面包",
    "multigrain bread": "杂粮面包", "raisin bread": "葡萄干面包", "naan": "馕饼",
    "bagel": "贝果", "baguette": "法棍", "bun": "小面包", "roll": "小圆面包",
    "rolls": "小圆面包", "croissant": "牛角包", "english muffin": "英式玛芬",
    "pancakes": "薄煎饼", "pancake": "薄煎饼", "waffle": "华夫饼", "waffles": "华夫饼",
    "french toast": "法式吐司", "muffin": "玛芬", "muffins": "玛芬",
    "melba toast": "薄脆吐司", "toast": "吐司", "brioche": "布里欧修",
    "scone": "司康", "shortbread": "酥饼", "panettone": "潘娜托尼",
    "pasta": "意面", "spaghetti": "意大利细面", "macaroni": "通心粉",
    "penne": "笔管面", "fusilli": "螺旋面", "lasagna": "千层面",
    "fettuccine": "宽条面", "linguine": "扁面", "ravioli": "意式方饺",
    "tortellini": "意式饺", "gnocchi": "土豆团子", "orzo": "米粒面",
    "noodles": "面条", "noodle": "面条", "egg noodles": "鸡蛋面", "ramen": "拉面",
    "vermicelli": "细面", "mein": "面", "chow mein": "炒面", "chop suey": "杂碎",
    "soba": "荞麦面", "udon": "乌冬面", "somen": "素面", "rice stick": "米粉条",
    "couscous": "古斯米", "polenta": "玉米糕", "grits": "玉米糁", "farina": "麦粉",
    "cereal": "谷物片", "cereals": "谷物", "oatmeal": "燕麦粥", "porridge": "粥",
    "oats": "燕麦", "oat": "燕麦", "oat bran": "燕麦麸", "wheat": "小麦",
    "whole wheat": "全麦", "wholemeal": "全麦", "wholegrain": "全谷物",
    "wheat flour": "小麦粉", "whole wheat flour": "全麦粉", "flour": "面粉",
    "semolina": "粗粒小麦粉", "gluten": "面筋", "seitan": "面筋",
    "barley": "大麦", "pearl barley": "珍珠麦", "corn": "玉米", "maize": "玉米",
    "cornmeal": "玉米面", "cornmeal grits": "玉米糁", "cornstarch": "玉米淀粉",
    "corn flour": "玉米粉", "hominy": "碱处理玉米", "rye": "黑麦", "millet": "小米",
    "sorghum": "高粱", "quinoa": "藜麦", "buckwheat": "荞麦", "amaranth": "苋菜籽",
    "matzo": "无酵饼", "stuffing": "填料", "croutons": "面包丁", "crumbs": "面包屑",
    "graham cracker": "全麦消化饼", "popcorn": "爆米花", "granola": "格兰诺拉麦片",
    "muesli": "什锦麦片", "sago": "西米", "tapioca": "木薯淀粉",

    # 蔬菜
    "potato": "马铃薯", "potatoes": "马铃薯", "sweet potato": "甘薯",
    "sweet potatoes": "甘薯", "mashed potato": "土豆泥", "mashed potatoes": "土豆泥",
    "french fries": "炸薯条", "fries": "炸薯条", "potato chips": "薯片",
    "potato salad": "土豆沙拉", "hash brown": "炸薯饼", "home fries": "煎土豆块",
    "yam": "山药", "true yam": "薯蓣", "cassava": "木薯", "yuca": "木薯",
    "taro": "芋头", "dasheen": "芋头", "malanga": "黄肉芋", "tannier": "芋",
    " Jerusalem artichoke": "洋姜", "water chestnut": "荸荠", "lotus root": "藕",
    "arrowroot": "葛粉", "bamboo shoot": "竹笋",
    "tomato": "番茄", "tomatoes": "番茄", "tomato sauce": "番茄酱汁",
    "tomato based": "番茄底", "cherry tomato": "樱桃番茄", "sun dried tomato": "日晒番茄干",
    "onion": "洋葱", "onions": "洋葱", "leek": "韭葱", "garlic": "大蒜",
    "shallot": "小红葱", "scallion": "小葱", "chive": "细香葱", "welsh onion": "大葱",
    "carrot": "胡萝卜", "carrots": "胡萝卜", "celery": "芹菜", "celeriac": "根芹",
    "cabbage": "甘蓝", "chinese cabbage": "大白菜", "bok choy": "小白菜",
    "napa cabbage": "大白菜", "red cabbage": "紫甘蓝", "savoy cabbage": "皱叶甘蓝",
    "cauliflower": "花椰菜", "broccoli": "西兰花", "broccolini": "嫩西兰花",
    "romanesco": "宝塔花菜", "kale": "羽衣甘蓝", "collards": "羽衣甘蓝",
    "spinach": "菠菜", "lettuce": "生菜", "romaine": "罗马生菜", "endive": "菊苣",
    "chicory": "菊苣", "radicchio": "红叶菊苣", "arugula": "芝麻菜",
    "watercress": "西洋菜", "radish": "萝卜", "daikon": "白萝卜",
    "turnip": "芜菁", "beet": "甜菜", "beetroot": "甜菜根", "parsnip": "欧防风",
    "rutabaga": "芜菁甘蓝", "kohlrabi": "苤蓝", "cucumber": "黄瓜",
    "gherkin": "小黄瓜", "zucchini": "西葫芦", "courgette": "西葫芦",
    "squash": "南瓜", "pumpkin": "南瓜", "butternut squash": "奶油南瓜",
    "spaghetti squash": "面条南瓜", "acorn squash": "橡子南瓜", "gourd": "葫芦",
    "chayote": "佛手瓜", "bitter melon": "苦瓜", "okra": "秋葵",
    "eggplant": "茄子", "aubergine": "茄子", "pepper": "辣椒", "peppers": "辣椒",
    "sweet pepper": "甜椒", "bell pepper": "甜椒", "chili pepper": "辣椒",
    "chile": "辣椒", "chilli": "辣椒", "jalapeno": "墨西哥辣椒", "paprika": "红椒粉",
    "mushroom": "蘑菇", "mushrooms": "蘑菇", "portabella": "大褐菇", "shiitake": "香菇",
    "oyster mushroom": "平菇", "enoki": "金针菇", "maitake": "舞茸",
    "morel": "羊肚菌", "truffle": "松露", "wood ear": "木耳", "cloud ear": "木耳",
    "white fungus": "银耳", "morel": "羊肚菌",
    "asparagus": "芦笋", "artichoke": "洋蓟", "celery flakes": "芹菜干片",
    "beans": "豆", "bean": "豆", "green beans": "四季豆", "snap beans": "四季豆",
    "wax beans": "黄荚菜豆", "lima beans": "利马豆", "fava bean": "蚕豆",
    "broad bean": "蚕豆", "yardlong bean": "长豇豆", "winged bean": "四棱豆",
    "peas": "豌豆", "pea": "豌豆", "garden peas": "豌豆", "snow peas": "荷兰豆",
    "sugar snap peas": "甜脆豆", "black eyed pea": "黑眼豆", "pigeon pea": "木豆",
    "chickpeas": "鹰嘴豆", "garbanzo": "鹰嘴豆", "lentils": "小扁豆", "lentil": "小扁豆",
    "mung bean": "绿豆", "adzuki bean": "赤小豆", "kidney bean": "红芸豆",
    "pinto bean": "花斑豆", "navy bean": "白芸豆", "black bean": "黑豆",
    "cowpea": "豇豆", "cowpeas": "豇豆", "bambara groundnut": "班巴拉豆",
    "soybeans": "大豆", "soybean": "大豆", "soya bean": "大豆", "edamame": "毛豆",
    "bean sprouts": "豆芽", "sprouts": "芽菜", "locust bean": "角豆",
    "jackfruit": "菠萝蜜", "breadfruit": "面包果", "succotash": "豆米杂烩",
    "greens": "绿叶菜", "vegetable": "蔬菜", "vegetables": "蔬菜",
    "leafy greens": "叶用绿叶菜", "leafTip": "", "root vegetables": "根菜类",
    "mixed vegetables": "什锦蔬菜", "garden vegetables": "园圃蔬菜",
    "cruciferous vegetables": "十字花科蔬菜", "pod vegetables": "荚果类蔬菜",
    "fruiting vegetables": "果菜类", "stalk vegetables": "茎菜类",
    "winter squash": "冬南瓜", "summer squash": "夏南瓜", "kangkung": "空心菜", "amaranth leaves": "苋菜叶",

    # 水果
    "apple": "苹果", "apples": "苹果", "applesauce": "苹果酱", "banana": "香蕉",
    "bananas": "香蕉", "plantain": "大蕉", "orange": "橙", "mandarin": "柑橘",
    "clementine": "小柑橘", "lemon": "柠檬", "lime": "青柠", "grapefruit": "西柚",
    "tangerine": "橘", "pomelo": "柚", "kumquat": "金橘", "citron": "香橼",
    "strawberry": "草莓", "strawberries": "草莓", "blueberry": "蓝莓",
    "blueberries": "蓝莓", "raspberry": "树莓", "raspberries": "树莓",
    "blackberry": "黑莓", "blackberries": "黑莓", "cranberry": "蔓越莓",
    "gooseberry": "醋栗", "currant": "醋栗粒", "blackcurrant": "黑加仑",
    "redcurrant": "红醋栗", "whitecurrants": "白醋栗", "elderberry": "接骨木果",
    "grape": "葡萄", "grapes": "葡萄", "raisin": "葡萄干", "raisins": "葡萄干",
    "sultana": "无核葡萄干", "currants dried": "葡萄干小粒", "prune": "西梅干",
    "prunes": "西梅干", "peach": "桃", "peaches": "桃", "pear": "梨", "pears": "梨",
    "plum": "李", "plums": "李", "cherry": "樱桃", "cherries": "樱桃",
    "apricot": "杏", "apricots": "杏", "nectarine": "油桃", "mango": "芒果",
    "pineapple": "菠萝", "papaya": "木瓜", "kiwi": "猕猴桃", "kiwifruit": "猕猴桃",
    "watermelon": "西瓜", "melon": "甜瓜", "cantaloupe": "哈密瓜",
    "honeydew": "白兰瓜", "casaba": "卡萨巴甜瓜", "avocado": "牛油果",
    "fig": "无花果", "figs": "无花果", "date": "枣", "dates": "枣",
    "pomegranate": "石榴", "persimmon": "柿子", "loquat": "枇杷", "guava": "番石榴",
    "jambu": "蒲桃", "lychee": "荔枝", "litchee": "荔枝", "longan": "龙眼",
    "rambutan": "红毛丹", "durian": "榴莲", "jackfruit seeds": "菠萝蜜籽",
    "passion fruit": "百香果", "dragon fruit": "火龙果", "star fruit": "杨桃",
    "carambola": "杨桃", "tamarind": "罗望子", "baobab": "猴面包果",
    "sea buckthorn": "沙棘", "rose hip": "玫瑰果", "quince": "榅桲",
    "medlar": "欧楂", "jujube": "枣", "ber": "滇刺枣", "berries mixed": "混合浆果",

    # 坚果种子
    "almond": "杏仁", "almonds": "杏仁", "walnut": "核桃", "walnuts": "核桃",
    "pecan": "碧根果", "cashew": "腰果", "cashews": "腰果", "pistachio": "开心果",
    "hazelnut": "榛子", "peanut": "花生", "peanuts": "花生", "groundnut": "花生",
    "groundnuts": "花生", "chestnut": "栗子", "chestnuts": "栗子",
    "macadamia": "澳洲坚果", "pine nut": "松子", "pinenuts": "松子",
    "sunflower seed": "葵花籽", "sunflower seeds": "葵花籽", "pumpkin seed": "南瓜籽",
    "pumpkin seeds": "南瓜籽", "pumpkin seed": "南瓜籽",
    "sesame seed": "芝麻", "sesame seeds": "芝麻", "flaxseed": "亚麻籽",
    "chia seed": "奇亚籽", "hemp seed": "火麻籽", "poppy seed": "罂粟籽",
    "cottonseed": "棉籽", "melon seed": "瓜子", "watermelon seed": "西瓜籽",
    "lotus seed": "莲子", "ginkgo nut": "白果", "brazil nut": "巴西坚果",
    "nut": "坚果", "nuts": "坚果", "seed": "种子", "seeds": "种子",
    "kernels": "仁", "kernel": "仁", "mixed nuts": "混合坚果", "trail mix": "什锦果仁",
    "peanut butter": "花生酱", "almond butter": "杏仁酱", "tahini": "芝麻酱",
    "melinjo": "melinjo", "kemiri": "石栗",

    # 油脂调味
    "oil": "油", "olive oil": "橄榄油", "corn oil": "玉米油", "soybean oil": "大豆油",
    "sunflower oil": "葵花籽油", "canola oil": "芥花油", "peanut oil": "花生油",
    "coconut oil": "椰子油", "palm oil": "棕榈油", "palm kernel oil": "棕榈仁油",
    "sesame oil": "芝麻油", "rapeseed oil": "菜籽油", "cottonseed oil": "棉籽油",
    "safflower oil": "红花油", "grapeseed oil": "葡萄籽油", "avocado oil": "牛油果油",
    "walnut oil": "核桃油", "mustard oil": "芥子油", "lard": "猪油",
    "tallow": "牛油", "shortening": "起酥油", "dripping": "油渣酱",
    "salad dressing": "沙拉酱", "mayonnaise": "蛋黄酱", "vinaigrette": "油醋汁",
    "vinegar": "醋", "cider vinegar": "苹果醋", "balsamic vinegar": "香醋",
    "sugar": "糖", "brown sugar": "红糖", "confectioners sugar": "糖粉",
    "icing sugar": "糖粉", "honey": "蜂蜜", "syrup": "糖浆", "maple syrup": "枫糖浆",
    "corn syrup": "玉米糖浆", "molasses": "糖蜜", "treacle": "糖蜜",
    "jelly": "果冻", "jam": "果酱", "marmalade": "柑橘果酱", "preserves": "蜜饯",
    "chocolate": "巧克力", "white chocolate": "白巧克力", "dark chocolate": "黑巧克力",
    "cocoa": "可可", "cocoa powder": "可可粉", "carob": "角豆粉",
    "candy": "糖果", "candies": "糖果", "marshmallow": "棉花糖", "nougat": "牛轧糖",
    "caramel": "焦糖", "fudge": "软糖", "toffee": "太妃糖", "lollipop": "棒棒糖",
    "gummi": "软糖", "gelatin dessert": "果冻甜品", "pudding": "布丁",
    "puddings": "布丁", "flan": "焦糖布丁", "popsicle": "冰棍", "sherbet": "果汁冰糕",
    "frozen yogurt": "冻酸奶", "mousse": "慕斯", "sorbet": "雪葩",
    "ice cream": "冰淇淋", "gelato": "意式冰淇淋", "custard": "卡仕达酱",
    "salt": "盐", "peppercorn": "胡椒粒", "spices": "香辛料", "spice": "香辛料",
    "herbs": "香草", "herb": "香草", "seasoning": "调味料", "condiment": "调味品",
    "condiments": "调味品", "yeast": "酵母", "baking powder": "泡打粉",
    "baking soda": "小苏打", "gelatin": "明胶", "soy sauce": "酱油",
    "tamari": "溜酱油", "mustard": "芥末", "prepared mustard": "调味芥末",
    "ketchup": "番茄酱", "catsup": "番茄酱", "barbecue sauce": "烧烤酱",
    "salsa": "莎莎酱", "pesto": "青酱", "relish": "调味酱菜", "pickle": "腌菜",
    "pickles": "腌菜", "olive": "橄榄", "tofu": "豆腐", "tempeh": "天培",
    "nutritional yeast": "营养酵母", "gravy": "肉汁", "white sauce": "白汁",
    "broth": "高汤", "stock": "汤底", "bouillon": "清汤", "worcestershire": "伍斯特郡酱",
    "hoisin sauce": "海鲜酱", "oyster sauce": "蚝油", "prawn sauce": "虾酱",
    "teriyaki sauce": "照烧酱", "tomato ketchup": "番茄沙司",

    # 烘焙零食
    "cake": "蛋糕", "cakes": "蛋糕", "sponge cake": "海绵蛋糕", "pound cake": "磅蛋糕",
    "cheesecake": "芝士蛋糕", "cupcake": "杯子蛋糕", "cookie": "曲奇",
    "cookies": "曲奇", "biscuit": "饼干", "biscuits": "饼干", "cracker": "薄脆饼",
    "crackers": "薄脆饼", "pie": "派", "tart": "塔", "pastry": "酥皮点心",
    "donut": "甜甜圈", "doughnut": "甜甜圈", "brownies": "布朗尼",
    "pretzel": "蝴蝶脆饼", "pretzels": "蝴蝶脆饼", "chips": "薯片", "chip": "薄脆片",
    "crisps": "薯片", "snack": "零食", "snacks": "零食", "strudel": "果馅卷",
    "cinnamon roll": "肉桂卷", "pie crust": "派皮", "tortilla": "玉米饼",
    "taco shell": "塔可壳", "nachos": "玉米片", "twist": "扭结饼", "wafer": "威化饼",
    "graham crackers": "消化饼", "nilla wafers": "香草威化", "oreo": "奥利奥饼干",

    # 饮品
    "coffee": "咖啡", "espresso": "浓缩咖啡", "latte": "拿铁", "cappuccino": "卡布奇诺",
    "mocha": "摩卡", "tea": "茶", "green tea": "绿茶", "black tea": "红茶",
    "oolong tea": "乌龙茶", "herbal tea": "花草茶", "brewed tea": "冲泡茶",
    "beer": "啤酒", "ale": "艾尔啤酒", "stout": "世涛啤酒", "wine": "葡萄酒",
    "red wine": "红葡萄酒", "white wine": "白葡萄酒", "table wine": "佐餐葡萄酒",
    "mead": "蜂蜜酒", "cocoa beverage": "可可饮料", "soda": "汽水", "cola": "可乐",
    "root beer": "根啤", "ginger ale": "姜汁汽水", "lemonade": "柠檬水",
    "juice": "汁", "juices": "汁", "nectar": "果浆", "water": "水",
    "mineral water": "矿泉水", "tap water": "自来水", "spring water": "泉水",
    "beverage": "饮料", "beverages": "饮料", "milkshake": "奶昔",
    "milk shake": "奶昔", "smoothie": "果昔", "alcoholic beverage": "酒精饮料",
    "liqueur": "利口酒", "brandy": "白兰地", "whiskey": "威士忌", "rum": "朗姆酒",
    "gin": "金酒", "vodka": "伏特加", "tequila": "龙舌兰", "sake": "清酒",
    "cider": "苹果酒", "aperitif": "开胃酒", "cocktail": "鸡尾酒",
    "energy drink": "能量饮料", "sports drink": "运动饮料", "soymilk": "豆浆",
    "almond milk": "杏仁奶", "coconut milk": "椰奶", "coconut water": "椰子水",
    "rice milk": "米奶", "oat milk": "燕麦奶", "rice beverage": "米饮",

    # 综合料理
    "soup": "汤", "chowder": "巧达浓汤", "bisque": "浓汤", "gazpacho": "西班牙冷汤",
    "salad": "沙拉", "coleslaw": "凉拌卷心菜", "sandwich": "三明治",
    "submarine sandwich": "潜艇三明治", "wrap": "卷饼", "pizza": "披萨",
    "burger": "汉堡", "hamburger": "汉堡", "cheeseburger": "芝士汉堡",
    "curry": "咖喱", "stew": "炖菜", "casserole": "砂锅菜", "pot pie": "锅派",
    "dumpling": "饺子", "samosa": "咖喱角", "bhaji": "炸蔬菜饼", "pakora": "炸蔬菜饼",
    "tamale": "玉米粽", "burrito": "墨西哥卷饼", "taco": "塔可",
    "enchilada": "卷饼", "quesadilla": "芝士饼", "empanada": "炸馅饼",
    "falafel": "炸豆丸子", "hummus": "鹰嘴豆泥", "baba ghanoush": "茄泥酱",
    "risotto": "意大利烩饭", "paella": "西班牙海鲜饭", "ratatouille": "法式杂菜烩",
    "sushi": "寿司", "moussaka": "希腊茄盒", "kebab": "烤肉串", "doner kebab": "旋转烤肉",
    "lasagna": "千层面", "chili con carne": "辣肉酱", "chili": "辣酱",
    "egg roll": "蛋卷", "spring roll": "春卷", "crepe": "可丽饼", "quiche": "乳蛋饼",
    "rissole": "炸肉饼", "croquette": "炸丸子", "gratin": "焗烤", "au gratin": "焗烤",
    "risotto": "烩饭", "tempura": "天妇罗", "teriyaki": "照烧", "sukiyaki": "寿喜锅",
    "stir fry": "炒菜", "sukiyaki": "寿喜烧", "fondue": "奶酪火锅",
    "chicken nuggets": "鸡块", "chicken tenders": "鸡柳条", "chicken wings": "鸡翅",
    "chicken breast": "鸡胸肉", "chicken thighs": "鸡腿肉", "chicken patty": "鸡肉饼",
    "chicken drumstick": "鸡小腿", "chicken liver": "鸡肝", "buffalo wings": "布法罗鸡翅",
    "patty": "肉饼", "patties": "肉饼", "entree": "主菜", "dinner": "正餐",
    "lunch": "午餐", "breakfast": "早餐", "meal replacement": "代餐", "diet meal": "减重餐",
    "tapas": "下酒菜", "meze": "地中海小菜", "antipasto": "意式前菜",

    # 婴幼儿 / 特医
    "infant formula": "婴儿配方奶粉", "formula": "配方粉", "teething biscuit": "磨牙饼干",
    "baby food": "婴儿食品", "babyfood": "婴儿食品", "toddler food": "幼儿食品",
    "follow on formula": "较大婴儿配方", "infant cereal": "婴儿米粉",

    # 零售餐饮
    "mcdonalds": "麦当劳", "burger king": "汉堡王", "taco bell": "塔可钟",
    "wendys": "温迪汉堡", "subway": "赛百味", "kfc": "肯德基", "pizza hut": "必胜客",
    "dominos": "达美乐", "starbucks": "星巴克", "gerber": "嘉宝", "nestle": "雀巢",
    "similac": "雅培", "enfamil": "美赞臣", "abbott": "雅培", "kraft": "卡夫",
    "quaker": "桂格", "mars": "玛氏", "restaurant": "餐厅", "fast foods": "快餐",
    "fast food": "快餐", "takeaway": "外带", "deli": "熟食店", "crust": "饼皮",
    "thin crust": "薄脆饼底", "deep dish": "深盘底", "pizza crust": "披萨饼底",
    "crouton": "面包丁", "topping": "配料", "frosting": "糖霜", "icing": "糖霜",
    "filling": "馅料", "coating": "外裹层", "breading": "面包屑裹层", "batter": "面糊",
    "dip": "蘸酱", "spread cheese": "涂抹奶酪", "sauce": "酱汁", "dressing": "调味酱",
    "white sauce": "白汁", "gravy sauce": "肉汁",

    # 藻类与菌藻
    "spirulina": "螺旋藻", "seaweed": "海藻", "kombu": "海带", "nori": "海苔",
    "wakame": "裙带菜", "hijiki": "羊栖菜", "dulse": "掌状红皮藻", "agar": "琼脂",
    "irish moss": "爱尔兰苔",

    # 其他蛋白
    "yuba": "腐竹", "bean curd": "豆腐", "tofu skin": "腐竹", "natto": "纳豆",
    "wheat gluten": "面筋", "single cell protein": "单细胞蛋白",
}

# ── 部位补语 PB：跟「主料」之后，构成「牛短肋 / 羊肩 / 鸡 leg」 ──
PB = {
    # 「牛短肋 / 羊腿 / 鸡胸肉」——紧贴主料之后，且主料会去掉重复的「肉」字
    "breast": "胸肉", "breasts": "胸肉", "thigh": "腿肉", "thighs": "腿肉",
    "drumstick": "小腿", "drumsticks": "小腿", "wing": "翅", "wings": "翅",
    "short ribs": "短肋", "spare ribs": "小排", "back ribs": "背肋",
    "country style ribs": "乡村式肋排", "rib roast": "肋排",
    "top loin": "上腰脊", "bottom loin": "下腰脊", "top round": "后腿上部",
    "bottom round": "后腿下部", "top sirloin": "上腰脊", "bottom sirloin": "下腰脊",
    "top blade": "上肩胛", "top rib": "上肋", "short loin": "短腰",
    "tenderloin tips": "里脊尖", "tri tip": "三角肉",
    "shoulder roast": "肩肉", "arm roast": "前臂", "blade roast": "肩胛",
    "rump roast": "臀肉", "round roast": "后腿", "sirloin tip": "西冷尖",
    "brisket flat": "胸平板", "brisket point": "胸尖",
    "fore shank": "前小腿", "hind shank": "后小腿", "cross rib": "横肋",
    "leg meat": "腿肉", "thigh meat": "腿肉", "dark meat": "深色肉",
    "light meat": "白肉", "white meat": "白肉", "wing meat": "翅肉",
    "breast meat": "胸肉", "breast quarter": "四分胸", "leg quarter": "四分腿",
    "rabbit loin": "兔腰", "whole chicken": "整鸡", "whole turkey": "整火鸡",
    "ground patty": "肉饼", "rib eye": "肋眼", "porterhouse steak": "波特豪斯牛排",
    " flank steak": "腹肉牛排", "bavette": "腹膜肌", "skirt": "横膈膜",
}

# ── 后缀 SF：放全名最后 ───────────────────────────────────
SF = {"baby food": "婴儿食品", "babyfood": "婴儿食品",
      "baby food junior": "较大婴儿食品", "junior": "较大婴儿",
      "baby food toddler": "幼儿食品", "toddler": "幼儿",
      "snackfood": "休闲零食", "strained": "过筛", "infant": "婴儿",
      "baby": "婴儿", "stage 1": "一段", "stage 2": "二段", "stage 3": "三段"}

# ── 状态 ST ───────────────────────────────────────────────
ST = {
    "raw": "生", "uncooked": "生", "fresh": "新鲜", "frozen": "冷冻",
    "chilled": "冷藏", "refrigerated": "冷藏", "canned": "罐头", "bottled": "瓶装",
    "dried": "干制", "fresh raw": "生鲜", "immature": "未成熟", "ripe": "成熟",
    "unripe": "未熟", "mature": "成熟", "overripe": "过熟", "rotten": "腐烂",
    "live": "活", "wild caught": "野生捕捞", "farmed": "养殖", "wild": "野生",
    " aquacultured": "养殖", "captive": "圈养", "grass fed": "草饲", "battery": "笼养",
    "free range": "散养", "organic": "有机", "not fried": "非油炸",
    "green": "青", "young": "幼嫩", "sprouted": "发芽",
}

# ── 烹饪 CO ───────────────────────────────────────────────
CO = {
    "cooked": "熟", "boiled": "水煮", "hard boiled": "水煮", "soft boiled": "半熟水煮",
    "poached": "低温煮", "simmered": "煨", "steamed": "蒸", "double steamed": "隔水蒸",
    "braised": "焖", "stewed": "炖", "casseroled": "砂锅炖", "pot roasted": "锅烤",
    "fried": "油炸", "deep fried": "油炸", "shallow fried": "浅炸", "pan fried": "煎",
    "pan broiled": "平锅炙烤", "stir fried": "炒", "sauteed": "嫩煎",
    "scrambled": "炒散", "roasted": "烤", "baked": "烤", "oven roasted": "烤箱烤",
    "grilled": "炙烤", "broiled": "炙烤", "charbroiled": "炭烤", "barbecued": "烧烤",
    "charcoal grilled": "炭火烤", "toasted": "烘烤", "pan toasted": "干焙",
    "microwaved": "微波加热", "reheated": "复热", "heated": "加热", "unheated": "未加热",
    "blanched": "焯水", "parboiled": "半熟焯水", "steam cooked": "蒸熟",
    "rotisserie": "旋转烤", "slow cooked": "慢炖", "pressure cooked": "高压烹",
    "air fried": "空气炸", "flash fried": "速炸", "dry roasted": "干焙烤",
    "oil roasted": "油炒", "stir grilled": "爆炒", "flame broiled": "明火炙烤",
}

# ── 加工保藏 PR ────────────────────────────────────────────
PR = {
    "canned goods": "罐藏", "smoked": "熏制", "cured": "腌腊", "pickled": "腌渍",
    "salted": "盐渍", "brined": "盐水渍", "fermented": "发酵", "marinated": "腌泡",
    "reconstituted": "复水还原", "dehydrated": "脱水", "freeze dried": "冻干",
    "sun dried": "日晒干", "dried elaborately": "精制干", "sulfured": "硫熏",
    "pasteurized": "巴氏杀菌", "pasteurised": "巴氏杀菌", "ultra pasteurized": "超高温杀菌",
    "sterilized": "灭菌", "homogenized": "均质", "irradiated": "辐照",
    "fortification processed": "营养强化加工", "refined": "精制", "unrefined": "未精制",
    "bleached": "漂白", "unbleached": "未漂白", "degermed": "脱胚",
    "decorticated": "脱壳", "defatted": "脱脂加工", "hydrogenated": "氢化",
    "partially hydrogenated": "部分氢化", "extruded": "挤压膨化", "puffed": "膨化",
    "instant": "即食", "precooked": "预熟", "pre cooked": "预熟", "unprepared": "未调制",
    "prepared": "预制", "home prepared": "家常制作", "commercial prepared": "市售",
    "commercially prepared": "市售", "prepackaged": "预包装", "packaged": "包装",
    "prepackaged or bottled": "预包装或瓶装", "ready to cook": "即烹",
    "ready to serve": "即食", "ready to eat": "即食", "ready to heat": "即热",
    "ready to drink": "即饮", "ready to feed": "即哺", "ready to use": "即用",
    "from concentrate": "浓缩还原", "not from concentrate": "非浓缩还原",
    " concentrated": "浓缩", "diluted": "稀释", "reconstituted juice": "还原汁",
    "homemade": "自制", "home made": "自制", "industrially made": "工业化生产",
    "imported": "进口", "domestic": "国产", "no preservative": "无防腐剂",
    "processing": "加工", "processed": "加工", "unprocessed": "未加工",
    "raw packed": "生装罐", "hot packed": "热装罐", "vacuum packed": "真空包装",
    "dry heat": "干热", "moist heat": "湿热",
    "prepared from granules": "颗粒还原", "prepared from concentrate": "浓缩还原",
    "prepared from frozen": "冻品调制", "prepared with water": "加水调制",
    "summer and autumn": "", "winter and spring": "", "early season": "",
    "late season": "", "as purchased": "", "as consumed": "", "purchased yield": "",
    "ripened": "后熟", "curing": "腌渍", "chopped shaped": "成型",
    "starch added": "加淀粉", "boned": "去骨处理", "trimmed": "修整",
    "prepared from recipe": "按配方制作", "as part of a recipe": "入菜用",
    "prepared from frozen": "由冷冻品制作", "commercial": "商品化",
    "double creamed": "双倍奶油", "whipped topping": "植脂鲜奶油",
    "unspecified if": "未注明", "not further specified": "未进一步说明",
}

# ── 含量/宣称 NU ───────────────────────────────────────────
NU = {
    "reduced fat": "减脂", "lower fat": "减脂", "less fat": "减脂", "low fat": "低脂",
    "lowfat": "低脂", "nonfat": "脱脂", "fat free": "脱脂", "skim": "脱脂",
    "skimmed": "脱脂", "part skim": "部分脱脂", "semi skimmed": "半脱脂",
    "defatted milk": "脱脂", "whole fat": "全脂", "full fat": "全脂",
    "extra rich": "特浓", "heavy": "浓厚", "reduced calorie": "减热量",
    "low calorie": "低热量", "reduced sugar": "减糖", "no sugar added": "无添加糖",
    "sugar free": "无糖", "unsweetened": "无糖", "lightly sweetened": "低糖",
    "sweetened": "加糖", "pre sweetened": "预加糖", "artificially sweetened": "人工增甜",
    "reduced sodium": "减钠", "low sodium": "低钠", "very low sodium": "极低钠",
    "no salt added": "无添加盐", "salt added": "加盐", "added salt": "加盐",
    "unsalted": "无盐", "lightly salted": "轻盐", "salt free": "无盐",
    "fortified": "强化", "unfortified": "未强化", "enriched": "强化",
    "unenriched": "未强化", "restored": "复原强化", "high protein": "高蛋白",
    "high fiber": "高纤维", "more fiber": "高纤维", "whole grain": "全谷物",
    "multigrain": "多谷物", "gluten free": "无麸质", "lactose free": "无乳糖",
    "reduced lactose": "低乳糖", "dairy free": "无乳", "low cholesterol": "低胆固醇",
    "vitamin added": "添加维生素", "mineral added": "添加矿物质",
    "calcium added": "添加钙", "vitamin fortified": "维生素强化",
    "calcium fortified": "钙强化", "iron fortified": "铁强化", "diet": "减重",
    "dietetic": "食疗用", "light": "清淡", "lite": "清淡", "plus": "加强型",
    "with fiber": "含膳食纤维", "with vitamin": "含维生素", "with iron": "含铁",
    "high in omega": "高ω-3", "omega enriched": "ω-3强化", "dha added": "添加DHA",
    "probiotic": "益生菌", "with probiotics": "含益生菌", "extra virgin": "特级初榨",
    "virgin": "初榨", "cold pressed": "冷榨", "expeller pressed": "压榨",
    "refined oil": "精炼", "no caffeine": "无咖啡因", "decaffeinated": "脱咖啡因",
    "caffeinated": "含咖啡因", "regular flavor": "常规味", "classic": "经典",
    "original": "原味", "natural": "天然", "pure": "纯", "imitation": "仿制",
    "artificial flavor": "人工香料", "artificially flavored": "人工调味",
    "flavored": "调味", "flavoured": "调味", "seasoned": "调味",
    "old fashioned": "老式", "old fashion": "老式", "country style": "乡村风味",
    "home style": "家常风味", "southern style": "南方风味", "deluxe": "精选",
    "special": "特制", "club": "大号", "family size": "家庭装",
    "jumbo": "特大", "petite": "小号", "small": "小", "medium": "中", "large": "大",
    "thick": "浓稠", "thin": "稀薄", "extra lean": "极瘦", "leanest": "极瘦",
}

# ── 颜色 CL ───────────────────────────────────────────────
CL = {
    "white": "白", "red": "红", "green": "绿", "black": "黑", "yellow": "黄",
    "brown": "棕", "blue": "蓝", "pink": "粉红", "golden": "金黄", "orange": "橙色",
    "purple": "紫", "purple hull": "紫荚", "gray": "灰", "grey": "灰",
    "dark green": "深绿", "light green": "浅绿", "dark red": "深红",
    "dark": "深色", "pale": "浅色", "creamy": "奶油色", "ivory": "象牙白",
    "ruby": "宝石红", "scarlet": "猩红", "violet": "紫罗兰", "burgundy": "勃艮第红",
    "skinless and boneless": "去皮去骨", "rainbow": "彩虹", "striped": "条纹",
}

# ── 国别风格 CN ────────────────────────────────────────────
CN = {
    "french": "法式", "italian": "意式", "mexican": "墨西哥式", "chinese": "中式",
    "japanese": "日式", "greek": "希腊式", "spanish": "西班牙式", "german": "德式",
    "swiss": "瑞士式", "russian": "俄式", "thai": "泰式", "indian": "印度式",
    "korean": "韩式", "vietnamese": "越南式", "middle eastern": "中东式",
    "mediterranean": "地中海式", "cajun": "卡真", "creole": "克里奥尔",
    "tex mex": "德州墨西哥式", "latin american": "拉美式", "caribbean": "加勒比式",
    "american": "美式", "english": "英式", "irish": "爱尔兰式", "scotch": "苏格兰式",
    "belgian": "比利时式", "dutch": "荷兰式", "polish": "波兰式", "hungarian": "匈牙利式",
    "austrian": "奥地利式", "portuguese": "葡萄牙式", "brazilian": "巴西式",
    "moroccan": "摩洛哥式", "lebanese": "黎巴嫩式", "turkish": "土耳其式",
    "african": "非洲式", "west african": "西非式", "east african": "东非式",
    "australian": "澳式", "new zealand": "新西兰产", "hawaiian": "夏威夷式",
    "alaska": "阿拉斯加产", "atlantic": "大西洋", "pacific": "太平洋",
    "new england": "新英格兰式", "southern": "南方风味", "northern": "北方",
    "boston": "波士顿式", "chicago": "芝加哥式", "new york": "纽约式",
    "puerto rican": "波多黎各式", "island": "海岛式", "oriental": "东方风味",
    "martinique": "马提尼克", "benin": "贝宁", "burkina faso": "布基纳法索",
    "nigeria": "尼日利亚", "ghana": "加纳", "mali": "马里", "senegal": "塞内加尔",
    "guinea": "几内亚", "togo": "多哥", "cameroon": "喀麦隆", "niger": "尼日尔",
    "chad": "乍得", "gambia": "冈比亚", "sierra leone": "塞拉利昂",
}

# ── 物理形态 PH ────────────────────────────────────────────
PH = {
    "ground": "绞碎", "chopped": "切碎", "diced": "切丁", "minced": "剁碎",
    "sliced": "切片", "slivers": "薄片", "strips": "切条", "shredded": "切丝",
    "grated": "磨碎", "crumbled": "捏碎", "crumbles": "酥粒", "crumbed": "裹面包屑",
    "mashed": "捣泥", "puree": "泥", "pureed": "打成泥", "pulverized": "粉碎",
    "powdered": "粉状", "powder": "粉", "flakes": "薄片干", "flake": "薄片干",
    "granules": "颗粒", "crushed": "压碎", "cubed": "方块", "chunky": "大块",
    "chunks": "大块", "pieces": "块", "bits": "小块", "halved": "对半",
    "halves": "对半", "quartered": "四等分", "quarter": "四分",
    "whole pieces": "整块", "small pieces": "小块", "thin sliced": "薄切",
    "julienne": "细丝", "cubes": "小方块", "diced small": "小丁", "stuffed": "酿制",
    "twisted": "扭结", "puffed shape": "膨化造型", "shaped": "成型",
    "extruded shape": "挤压成型", "creamed": "奶油状", "whipped": "搅打",
    "emulsified": "乳化", "foamed": "泡沫状", "gelled": "凝胶状",
    "whole peeled": "整只去皮", "sectioned": "分瓣", "sections": "分瓣",
    "canned solids and liquid": "罐头连汁", "solids and liquids": "固形物与汤汁",
    "solids and liquid": "固形物与汤汁", "liquid only": "仅液体", "drained solids": "沥干固形物",
    "drained": "沥干", "undrained": "未沥干", "packed in water": "水浸",
    "packed in oil": "油浸", "water pack": "水浸", "oil pack": "油浸",
    "juice pack": "果汁浸", "syrup pack": "糖水浸", "heavy syrup": "浓糖水浸",
    "light syrup": "淡糖水浸", "extra heavy syrup": "特浓糖水浸",
    "vacuum pack": "真空装", "bulk": "散装", "loose": "散装",
    "reconstituted with water": "加水复水", "diluted juice": "稀释汁",
    "not packed": "非罐藏", "rinsed": "漂洗", "soaked": "浸泡", "not soaked": "未浸泡",
    "cold": "冷", "hot": "热", "warm": "温", "iced": "冰镇", "chilled served": "冰镇食用",
    "melted": "融化", "softened": "软化", "hard": "硬质", "soft": "软质",
    "firm": "紧实", "smooth": "细腻", "crispy": "酥脆", "crunchy": "脆",
    "chewy": "耐嚼", "moist": "湿润", "dry roasted": "干焙", "crumbly": "松散",
    "slurried": "浆化", "lump": "团块", "puffed grain": "膨化谷粒",
}

# ── 取料部位 QT：放名称最后 ────────────────────────────────
QT = {
    "lean": "瘦肉", "lean only": "仅瘦肉", "lean and fat": "带肥瘦肉",
    "separable lean": "可分离瘦肉", "separable lean only": "可分离瘦肉",
    "separable fat": "可分离脂肪", "fat": "脂肪", "visible fat": "可见脂肪",
    "with added fat": "添加脂肪", "skin": "皮", "with skin": "带皮",
    "skin only": "仅皮", "skinless": "去皮", "skin eaten": "连皮食用",
    "skin not eaten": "去皮食用", "boneless": "去骨", "bone in": "带骨",
    "boneless meat only": "仅去骨肉", "meat only": "仅肉", "flesh only": "仅果肉",
    "with bone": "带骨", "with peel": "带皮", "peeled": "去皮",
    "peel": "果皮", "rind": "外皮", "pitted": "去核", "stoned": "去核",
    "cored": "去芯", "seeded": "去籽", "seedless": "无籽", "hulled": "去壳",
    "shelled": "去壳", "without shells": "去壳", "shell": "壳", "husked": "脱壳",
    "trimmed to": "修整至", "trimmed fat": "修整脂肪", "trimmed lean": "修整瘦肉",
    "defatted solids": "脱脂固形物", "lean flesh": "瘦肉", "dark flesh": "深色肉",
    "white flesh": "白色鱼肉", "light flesh": "浅色鱼肉", "trimmed": "修整",
    "with refuse": "含废弃部分", "refuse": "废弃部分", "edible portion": "可食部",
    "外层": "外层", "giblet": "内脏", "marrow": "骨髓", "gristle": "软骨",
    "外层": "外层", "connective tissue": "结缔组织", "drippings": "滴油",
}

# ── 纯噪声 STOP：不进中文名 ───────────────────────────────
STOP = set("""
and or with without as to from in on of the a an only s plus includes include
not no make made type types kind varieties variety all each per contents weighed
purchase purchased yield approximate approximately average averagely retail
trimmed wise adjusted based described based serving ns nfs usda ref out up off
choice select grade grades canner cutter utility prime standard commercial
distribution program toppings for served serve serving use used using any than
that this other others more less equal vs un uma im cm mm sized size about
plain regular native common mixed combination combination total product products
prepared when such part parts percent past low old new freshness uns sp cf bq
dressing ITEM unit cup bowl container pkg package packaging pm de la le el du
additional brands diet ssp Docosahexaenoic mcg ctrl premium gold silver
""".split())

# ── 复配补充：以上各类之外的常见词条 ───────────────────────────
_EXTRA_NU = {
    "vitamin": "维生素", "minerals": "矿物质", "mineral": "矿物质",
    "vitamin a": "维生素A", "vitamin d": "维生素D", "vitamin c": "维生素C",
    "vitamin e": "维生素E", "vitamin k": "维生素K", "vitamin b6": "维生素B6",
    "vitamin b12": "维生素B12", "vitamin a palmitate": "维生素A棕榈酸酯",
    "added vitamin": "添加维生素", "added minerals": "添加矿物质",
    "added sugars": "添加糖", "added fiber": "添加膳食纤维",
    "added calcium": "添加钙", "added iron": "添加铁", "added protein": "添加蛋白",
    "added omega": "添加ω-3", "added enzyme": "添加酶",
    "sweetener": "甜味剂", "artificial sweetener": "人工甜味剂",
    "nonnutritive sweetener": "非营养性甜味剂", "aspartame": "阿斯巴甜",
    "sucralose": "三氯蔗糖", "sorbitol": "山梨糖醇", "stevia": "甜菊糖苷",
    "yeast type": "酵母发酵", "sourdough starter": "酸面团酵头",
    "acerola": "针叶樱桃", "acerola juice": "针叶樱桃汁",
    "high fructose corn syrup": "高果糖玉米糖浆", "invert syrup": "转化糖浆",
    "whey protein": "乳清蛋白", "soy protein": "大豆蛋白", "casein": "酪蛋白",
    "caseinate": "酪蛋白酸盐", "albumen": "卵清蛋白",
    "omega 3": "ω-3", "dha": "DHA", "epa": "EPA", "ara": "ARA",
    "tocopherol": "生育酚", "ascorbic acid": "抗坏血酸", "retinol": "视黄醇",
    "niacin": "烟酸", "riboflavin": "核黄素", "thiamin": "硫胺素",
    "folic acid": "叶酸", "cobalamin": "钴胺素", "choline": "胆碱",
    "amino acid": "氨基酸", "lysine": "赖氨酸", "taurine": "牛磺酸",
    "carnitine": "肉碱", "inositol": "肌醇", "biotin": "生物素",
    "lactose reduced": "低乳糖", "galactose": "半乳糖",
    "acesulfame": "安赛蜜", "acesulfame potassium": "安赛蜜钾",
}
NU.update(_EXTRA_NU)

# ── 美式倒装：数据库惯用「主料, 修饰」书写，跨逗号的短语须单独收录 ──
# 引擎在整条归一化串上一次扫描，跨逗号只是空格，故这些 key 能被正常命中。
MF_INVERTED = {
    "egg whole": "全蛋", "egg whole cooked": "熟全蛋", "egg dried": "蛋粉",
    "egg scrambled": "炒蛋", "milk dry": "奶粉", "milk dry whole": "全脂奶粉",
    "milk dry nonfat": "脱脂奶粉", "milk evaporated": "淡奶",
    "milk condensed": "炼乳", "milk fluid": "液态奶", "milk canned": "罐装奶",
    "milk reduced fat": "减脂奶", "milk lowfat": "低脂奶", "milk human": "母乳",
    "milk whole": "全脂牛奶", "milk skimmed": "脱脂奶", "milk semi skimmed": "半脱脂奶",
    "milk buttermilk": "酪乳", "milk goat": "羊奶", "milk coconut": "椰奶",
    "milk evaporated whole": "全脂淡奶", "milk based": "乳基",
    "cheese white": "白奶酪", "cheese blue veined": "蓝纹奶酪",
    "oil salad or cooking": "食用油", "oil cooking": "食用油",
    "oil industrial": "工业用油", "oil partly hydrogenated": "部分氢化油",
    "cream sour": "酸奶油", "cream whipped": "搅打奶油", "cream light": "淡奶油",
    "cheese cottage": "白软干酪", "cheese cream": "奶油奶酪",
    "bean soy": "大豆", "beans soy": "大豆", "fruit bread": "面包果",
    "rice wild": "菰米", "wheat durum": "硬粒小麦", "corn sweet": "甜玉米",
    "potato sweet": "甘薯", "peanut valencia": "瓦伦西亚花生",
    "pepper sweet": "甜椒", "plantain ripe": "成熟大蕉",
    "apple golden delicious": "金冠苹果", "banana plantain": "大蕉",
    "oil olive": "橄榄油", "oil corn": "玉米油", "oil soybean": "大豆油",
    "oil peanut": "花生油", "oil palm": "棕榈油", "oil sunflower": "葵花籽油",
    "oil sesame": "芝麻油", "oil canola": "芥花油", "oil wheat germ": "小麦胚芽油",
    "oil cod liver": "鱼肝油", "oil salad or cooking": "食用油",
    "powder baking": "泡打粉", "powder cocoa": "可可粉", "powder curry": "咖喱粉",
    "powder chili": "辣椒粉", "powder garlic": "大蒜粉", "powder onion": "洋葱粉",
    "flour wheat": "小麦粉", "flour soy": "大豆粉", "flour potato": "马铃薯粉",
    "flour corn": "玉米粉", "flour rye": "黑麦粉", "flour cassava": "木薯粉",
    "flour buckwheat": "荞麦粉", "flour rice": "米粉", "flour barley": "大麦粉",
    "juice apple": "苹果汁", "juice orange": "橙汁", "juice grape": "葡萄汁",
    "juice lemon": "柠檬汁", "juice tomato": "番茄汁", "juice lime": "青柠汁",
    "juice pineapple": "菠萝汁", "juice cranberry": "蔓越莓汁",
    "juice grapefruit": "西柚汁", "juice carrot": "胡萝卜汁",
    "sauce tomato": "番茄酱汁", "sauce soy": "酱油", "sauce apple": "苹果酱",
    "sauce pasta": "意面酱", "sauce pepper": "胡椒酱", "sauce worcestershire": "伍斯特郡酱",
    "sauce cranberry": "蔓越莓酱", "sauce barbecue": "烧烤酱",
    "cereal rice": "米粉糊", "milk powdered whole": "全脂奶粉",
}
MF.update(MF_INVERTED)

NU.update({
    "whole wheat": "全麦", "wholemeal": "全麦", "wholegrain": "全谷物",
    "multigrain bread": "杂粮面包", "whole durum": "全硬粒",
})
# 归并到「含量宣言」后，这些不再由主料承担，否则会后置到名字核心之后
for _k in ("whole wheat", "wholemeal", "wholegrain", "babyfood", "baby food"):
    MF.pop(_k, None)
ST.update({"dry": "干制"})
MF.update({"fluid": "液态", "liquids": "液体", "solids": "固形物"})

# 备注：'Milk, whole' 会命中 MF 的 whole milk；'Egg, whole' 会命中 MF 的 egg whole。
# 归一化后跨逗号只是空格，长 key 优先，所以倒装短语能被正确吃掉。
ZZ = {
    "added": "", "broiler": "", "fryer": "", "roaster": "", "hen": "", "cock": "",
    "capon": "", "stewing": "", "fryers": "", "broilers": "", "roasters": "",
    "hens": "", "cocks": "", "capons": "", "unspecified": "", "unspec": "",
    "summer": "", "autumn": "", "winter": "", "spring": "", "ripeness": "",
    "fruit": "", "salad or cooking": "", "or cooking": "", "cooking": "",
    "cooking or salad": "", "table ready": "", "and product": "", "out": "",
    "up": "", "off": "", "someone": "", "sometimes": "",
    "described": "", "further": "", "specified": "", "nfs": "", "ns": "",
    "style": "", "eaten": "", "end": "", "center": "", "species": "",
    "sampled": "", "volume": "", "johnson": "", "different": "", "certain": "",
    "lip": "", "non": "", "varied": "", "assume": "", "medallion": "",
    "day": "", "days": "", "weeks": "", "months": "", "years": "",
    "old el paso": "", "cheerios": "", "nis içeri": "", "part Total": "",
    "percent": "", "all purpose": "", "purposes": "", "purpose": "",
    "similar": "", "analogous": "", "composite": "", "miscellaneous": "",
    "unknown": "", "unidentified": "", "assorted": "", "including": "",
    "excluding": "", "plus": "", "contains": "", "containing": "",
    "vitamin supplemented": "", "supplemented": "", "supplement": "",
    "dishes": "", "dish": "", "preparations": "", "preparation": "",
}

# ── PH 中这些「成品形态」挂在主料之后（土豆泥/罐头连汁/水浸）──
PH_SUFFIX = {
    "mashed", "mashed potato", "mashed potatoes", "puree", "pureed",
    "powder", "powdered", "flakes", "granules", "crumbs", "crumbles",
    "crushed", "cubes", "cubed", "pulp", "whole pieces",
    "sections", "sectioned", "juice pack", "water pack", "oil pack",
    "solids and liquids", "solids and liquid", "drained solids",
    "packed in water", "packed in oil", "heavy syrup", "light syrup",
    "extra heavy syrup", "vacuum pack", "undrained", "drained",
    "liquid only", "bulk", "loose", "not packed", "reconstituted with water",
    "seedless", "softened", "melted", "whipped",
}

# 需要作为整体处理、不拆分的组合（仅记录，实际由上面各 dict 的长 key 承担）
KEEP_PHRASES = [
    "lean and fat", "separable lean", "separable fat", "lean only", "meat only",
    "skin eaten", "skin not eaten", "solids and liquids", "solids and liquid",
    "dark green", "light green", "dark red", "whole wheat", "wholegrain",
    "french fries", "ice cream", "hot dog", "peanut butter", "olive oil",
    "no salt added", "reduced fat", "low fat", "fat free", "part skim",
    "gluten free", "lactose free", "sugar free", "salt free", "dairy free",
    "ready to eat", "ready to serve", "ready to drink", "ready to cook",
    "ready to heat", "ready to feed", "from concentrate", "not from concentrate",
    "fast foods", "not further specified", "as part of a recipe",
    "prepared from recipe", "canned solids and liquid", "with added salt",
    "vitamin a and vitamin d", "prepared from granules", "whole milk",
    "mineral still water", "canned or bottled", "total dietary fiber",
]

# ════════════════════════════════════════════════════════════════
#  第二批词条：全量 26,958 条扫描后，依据「未收录高频词」补齐。
#  补到这里而非散落各处，便于和第一批区分、后续继续增量追加。
# ════════════════════════════════════════════════════════════════

MF.update({
    "vegetable": "蔬菜", "vegetables": "蔬菜", "leafy greens": "叶用绿叶菜",
    "root vegetables": "根菜类", "mixed vegetables": "什锦蔬菜",
    "winter squash": "冬南瓜", "summer squash": "夏南瓜",
    "mix": "混合料", "cake mix": "蛋糕预拌粉", "brownie mix": "布朗尼预拌粉",
    "pudding mix": "布丁粉", "soup mix": "汤料", "biscuit mix": "饼干预拌粉",
    "pancake mix": "煎饼预拌粉", "muffin mix": "玛芬预拌粉",
    "bread mix": "面包预拌粉", "noodle mix": "面预拌料",
    "flesh": "肉", "drink": "饮料", "drinks": "饮料", "grain": "谷物",
    "grains": "谷物粒", "fillet": "鱼柳", "fillets": "鱼柳",
    "omelet": "煎蛋饼", "omelette": "煎蛋饼", "coconut": "椰子",
    "concentrate": "浓缩物", "condensed": "浓缩", "liquid": "液体",
    "poultry": "禽肉", "dairy": "乳制品", "dessert": "甜点",
    "soy": "大豆", "soya": "大豆", "sour": "酸味", "iron": "铁",
    "goat": "山羊", "cow": "牛", "leaves": "叶", "leaf": "叶",
    "vanilla": "香草", "concentrate juice": "浓缩汁",
    "still": "静止", "pack": "包装", "half": "半份", "center cut": "中段",
    "solution": "溶液", "moisture": "水分", "pie filling": "派馅",
    "cream puff": "泡芙", "potato puff": "薯泥球", "cheese puff": "奶酪球",
    "fruit leather": "果丹皮", "fruit roll": "果丹皮", "fruit bar": "果条",
    "breakfast bar": "早餐棒", "granola bar": "麦片棒",
    "energy bar": "能量棒", "protein bar": "蛋白棒",
    "snack bar": "零食棒", "cereal bar": "谷物棒", "chocolate bar": "巧克力条",
    "topping Whipped": "", "egg substitute": "代蛋品",
    "meal": "粉粕", "gravy mix": "肉汁粉", "sauce mix": "酱粉",
    "milk substitute": "代乳品", " coffee substitute": "代咖啡",
    "sugar substitute": "代糖", "salt substitute": "代盐",
    "diet soft drink": "无糖饮料", "fruit drink": "果味饮料",
    "rice drink": "米饮料", "soy drink": "豆饮料",
})

PB.update({
    "round": "后腿", "rib": "肋排", "ribs": "肋排", "leg": "腿",
    "shoulder arm": "前肩", "leg whole": "整只腿", "center slice": "中段切片",
    "eye round": "后腿心", "fillet center": "中段鱼柳",
})

PH.update({
    "filled": "夹馅", "coated": "裹衣", "breaded": "裹面包屑",
    "carbonated": "碳酸化", "double": "双倍", "half and half": "一半半",
    "stick": "棒状", "sticks": "条状", "ring": "圈状", "rings": "圈状",
    "shaped piece": "成型块", "screened": "过筛", "rinsed drained": "漂洗沥干",
})

NU.update({
    "leafy": "叶用", "mineralized": "含矿物质", "flavor": "风味",
    "flavors": "风味", "sweet": "甜味", "whole total": "",
    "carbonated water": "碳酸水", "with vitamins": "含多种维生素",
    "with minerals": "含矿物质", "mineral rich": "富含矿物质",
})
NU.pop("whole total", None)

PR.update({"prepacked": "预包装", "pasteurised whole": "巴氏杀菌全脂",
           "reconstituted from": "还原", "churned": "搅制", "ripened cheese": "成熟奶酪"})

ST.update({"whole Total": ""})
ST.pop("whole Total", None)

QT.update({"bone": "骨", "bones": "骨", "flesh skin": "肉和皮",
           "skinless bone": "去皮去骨", "center bone": "中心骨"})

# ════════════════════════════════════════════════════════════════
#  第三批词条：再次全量扫描后的剩余高频缺口
# ════════════════════════════════════════════════════════════════
ZZ.update({
    "recipe": "", "recipes": "", "home": "", "pot": "", "content": "",
    "school": "", "table": "", "ingredient": "", "fast": "", "pan": "",
    "pre": "", "tip": "", "under": "", "cap": "", "removed": "", "like": "",
    "nutrition": "", "sub": "", "form": "", "good": "", "start": "",
    "there": "", "their": "", "current": "", "prepared from recipe Total": "",
    "garnish": "", "liquid Total": "", "liquid added": "", "added liquid": "",
})

MF.update({
    "bar": "棒", "bars": "棒", "cinnamon": "肉桂", "tuber": "块茎",
    "malt": "麦芽", "blend": "混合料", "dough": "面团", "bran": "麸皮",
    "paste": "酱", "sesame": "芝麻", "alcohol": "酒精", "creme": "奶油",
    "cone": "蛋筒", "loaf": "条包", "loaves": "条包", "potato tuber": "块茎",
    "protein": "蛋白质", "calcium": "钙", "sodium": "钠", "iron Total": "",
    "soup base": "汤底", "salad dressing Total": "", "chewing gum": "口香糖",
    "yeast extract": "酵母提取物", "marmite": "马麦酱", "egg white dried": "干蛋清",
    "dairy dessert": "乳制甜点", "fruit yogurt": "果味酸奶", "coffee substitute": "代咖啡",
    "milk chocolate Total": "", "chocolate candy": "巧克力糖",
    "cocoa butter": "可可脂", "whey protein": "乳清蛋白",
    "sesame paste": "芝麻酱", "sunflower butter": "葵花籽酱",
    "liquid smoke": "烟熏液", "baking chocolate": "烘焙巧克力",
    "carob Total": "", "gelatin powder": "明胶粉",
})
MF.pop("iron Total", None); MF.pop("salad dressing Total", None)
MF.pop("milk chocolate Total", None); MF.pop("carob Total", None)

NU.update({
    "whole Total": "", "extra": "特级", "lightly": "轻度", "high": "高",
    "nutritional": "营养强化", "tender": "嫩化", "barbecue": "烧烤味",
    "sparkling": "气泡", "perl": "", "pearl": "珍珠状", "quick": "速成",
    "semi": "半", "long": "长形", "lean Total": "", "rich Total": "",
    "highly": "高度", "no Total": "", "low Total": "", "with Total": "",
})
NU.pop("whole Total", None); NU.pop("perl", None); NU.pop("lean Total", None)
NU.pop("rich Total", None); NU.pop("no Total", None); NU.pop("low Total", None)
NU.pop("with Total", None)
NU["lean"] = NU.get("lean", "瘦肉")

PR.update({"brewed": "冲泡", "spray dried": "喷雾干燥", "post": "早餐谷物",
           "bakery": "烘焙房制", "bake": "烘烤", "cooked Total": ""})
PR.pop("cooked Total", None)

CN.update({"european": "欧式"})

PH.update({"slice": "片", "covered": "裹", "split": "剖开", "round slice": "圆片"})

# ════════════════════════════════════════════════════════════════
#  第四批：收尾补充（含 USDA 品牌词、构造词）
# ════════════════════════════════════════════════════════════════
NU.update({"whole": "整只", "single": "单一", "combined": "混合", "ready": "即食",
           "frosted": "挂糖霜", "strongly": "重", "stable": "常温", "salty": "咸味",
           "food Total": ""})
NU.pop("food Total", None)
MF.update({
    "plant": "植物", "plant based": "植物基", "stones": "核", "seed stone": "核",
    "garden": "园圃", "sea": "海", "citrus": "柑橘类", "shake": "奶昔",
    "base": "基底", "chick": "雏鸡", "mince": "肉糜", "cheddar": "切达",
    "palm": "棕榈", "caffeine": "咖啡因", "tub": "桶装", "sponge": "海绵蛋糕",
    "pinto": "花斑豆", "rack": "肋排整扇", "marble": "大理石纹", "process": "再制",
    "silk": "丝滑", "blended": "调和", "brine": "盐水", "tubers": "块茎",
    "pulp juice": "果肉汁", "specialty": "特制", "food": "食品", "foods": "食品",
    "bird": "鸟肉", "archway": "Archway", "chobani": "Chobani",
    "ocean": "海洋", "outside": "外侧", "inside": "内侧", "crunch": "脆粒",
    "brussels sprouts": "抱子甘蓝", "sprout brussels": "抱子甘蓝",
    "industrial": "工业化", "latino": "拉丁风味", "frenched": "法切",
    "dahl": "扁豆糊", "lintel": "", "seaweed Nori": "海苔", "puff": "泡芙",
    "shea": "乳木果", "groats": "去壳谷粒", "beluga": "白鲸",
    "millet flour": "小米粉", "flaking": "压片", "shelf stable": "常温保存",
    "shelf": "常温货架", "navajo": "纳瓦霍式", "king mackerel": "国王鲭",
    "olive green": "青橄榄", "rind citrus": "柑橘皮",
})
MF.pop("lintel", None)
PB.update({"eye": "眼肉", "rack of lamb": "羊肋扇"})
PR.update({"uht": "超高温瞬时灭菌", "microwave": "微波", "mince ground": "绞制",
           "freeze": "冻结", "chilled display": "冷藏陈列"})
ZZ.update({"cook": "", "brand": "", "classes": "", "spray": "", "snap": "",
           "100g": "", "some waters": "", "the type": ""})

# ==== 批次 5：收尾补词（未译记录残留英文词） ====
STOP.update({"and": "", "with": "", "or": "", "from": "", "of": "", "in": "",
             "on": "", "nfs": "", "de": "", "en": "", "pats": "", "own": "",
             "equivalents": "", "volume": "", "similar": "", "standard": "",
             "premium": "", "average": "", "made": "", "only": "", "way": "",
             "products": "", "topic": "", "up": "", "big": "", "at": "",
             "retail": "", "plain": ""})
MF.update({
    "fruit": "水果", "dulce": "甜奶", "leche": "奶", "eggnog": "蛋酒",
    "saveloy": "萨维罗香肠", "cervelat": "色拉米肠", "blackcurrant": "黑加仑",
    "liqueur": "利口酒", "baklava": "果仁蜜饼", "pastry": "酥皮点心",
    "almonds": "杏仁", "syrup": "糖浆", "breadsticks": "面包棒",
    "breadstick": "面包棒", "trifle": "松糕", "tiramisu": "提拉米苏",
    "sauerkraut": "酸菜", "savouries": "咸味小食", "savoury": "咸味小食",
    "lager": "拉格啤酒", "hotcakes": "热香饼", "berry": "浆果",
    "fritter": "油炸饼", "pina": "菠萝", "colada": "椰香", "atole": "玉米糊",
    "punch": "潘趣酒", "rusk": "面包干", "rusks": "面包干",
    "breadcrumbs": "面包糠", "coppa": "卡帕火腿", "pancetta": "意式培根",
    "galantine": "肉冻卷", "ox": "牛", "muzzle": "口鼻", "bresaola": "风干牛肉",
    "crustacean": "甲壳类", "mollusc": "软体类", "brousse": "布鲁斯奶酪",
    "cheese": "奶酪", "milk": "奶", "whisky": "威士忌", "sangria": "桑格利亚",
    "wine": "葡萄酒", "fructose": "果糖", "calisson": "卡利松糖",
    "marzipan": "杏仁膏", "melon": "甜瓜", "confiture": "果酱", "lait": "奶",
    "meringue": "蛋白霜", "meringues": "蛋白霜", "horn": "角", "crescent": "新月",
    "eclair": "闪电泡芙", "charlotte": "夏洛特蛋糕", "lolly": "冰棍",
    "tapenade": "橄榄酱", "puree": "泥", "capers": "刺山柑", "olives": "橄榄",
    "anchovy": "鳀鱼", "herbs": "香草", "nutmeg": "肉豆蔻", "cloves": "丁香",
    "crumble": "酥皮馅饼", "flapjacks": "燕麦方块", "flapjack": "燕麦方块",
    "oatcakes": "燕麦饼", "wheatgerm": "小麦胚芽", "gajjeralla": "印度胡萝卜布丁",
    "torte": "圆形蛋糕", "tzatziki": "酸奶黄瓜酱", "houmous": "鹰嘴豆泥",
    "asafoetida": "阿魏", "garam": "印度", "masala": "马萨拉", "amla": "余甘子",
    "physalis": "酸浆", "tigernuts": "油莎豆", "laverbread": "紫菜饼",
    "quorn": "素肉", "korma": "咖喱", "khadhi": "酸奶咖喱", "khatiyu": "印度豆糊",
    "pastichio": "希腊千层面", "tabouleh": "塔布勒沙拉", "taramasalata": "鱼子酱泥",
    "peppermints": "薄荷糖", "gelatine": "明胶", "maltesers": "麦丽素",
    "milky": "奶味", "snickers": "士力架", "twiglets": "脆麦条",
    "piccalilli": "酸辣腌菜", "lucozade": "运动饮料", "mincemeat": "果馅",
    "liquorice": "甘草糖", "allsorts": "什锦甘草糖", "pastilles": "软糖",
    "brawn": "肉冻", "cornish": "康沃尔", "pasty": "馅饼", "papad": "印度薄饼",
    "triticale": "小黑麦", "poi": "芋泥", "mac": "麦当劳", "zwieback": "烤面包片",
    "wasabi": "芥末", "okara": "豆渣", "margarine": "人造黄油",
    "licuado": "果昔", "batido": "奶昔", "creamsicle": "冰淇淋棒",
    "fudgesicle": "巧克力冰棒", "welsh": "威尔士", "rarebit": "奶酪吐司",
    "groundhog": "土拨鼠", "beaver": "河狸", "raccoon": "浣熊",
    "armadillo": "犰狳", "hog": "猪", "maws": "胃", "thuringer": "图林根香肠",
    "spam": "午餐肉", "ceviche": "酸橘汁腌鱼", "moo": "牛", "goo": "酱",
    "gai": "鸡", "pig": "猪", "blanket": "卷", "huevos": "鸡蛋",
    "rancheros": "牧场式", "dal": "扁豆糊", "dahl": "扁豆糊",
    "bruschetta": "意式烤面包", "pannetone": "潘妮朵尼", "cornbread": "玉米面包",
    "champagne": "香槟", "candied": "蜜饯", "miso": "味噌", "kir": "基尔酒",
    "oriental": "东方风味", "saffron": "藏红花", "yakitori": "日式烤串",
    "rostis": "瑞士薯饼", "blinis": "俄式薄饼", "lau": "捞",
    "mcdonald's": "麦当劳", "kacang": "豆", "sepat": "豆",
})
CO.update({"grilled": "烤", "skewers": "串烤", "puree": "打成泥"})
ZZ.update({"japanese-style": "日式", "aix": "艾克斯", "provence": "普罗旺斯",
           "obernai": "奥贝奈", "alsace": "阿尔萨斯", "uncured": "未腌制",
           "sweet": "甜", "icing": "糖霜", "tap": "", "black": "黑",
           "shaped": "形状", "covered": "包覆", "seven": "七种",
           "alcoholic": "含酒精", "royal": "皇家", "white": "白",
           "ewes'": "羊", "cornish": "康沃尔", "meat": "肉", "sauce": "酱汁",
           "gazelle": "羚羊角", "ice": "冰", "sugar": "糖",
           "spirits": "烈酒", "port": "波特酒"})

# ==== 批次 6：单字民族菜名收尾 ====
MF.update({
    "hush puppy": "玉米炸丸", "johnnycake": "玉米饼", "spoonbread": "勺舀玉米面包",
    "arepa": "玉米饼", "popover": "膨松饼", "pocky": "百奇饼干棒",
    "basbousa": "粗麦蜜糕", "churros": "吉事果", "beignet": "法式炸甜甜圈",
    "idli": "印度蒸米糕", "dosa": "印度薄饼", "congee": "粥",
    "chilaquiles": "墨西哥玉米片", "fajita": "墨西哥烤肉卷",
    "bacalaitos": "鳕鱼炸饼", "pierogi": "波兰饺子", "knish": "犹太馅饼",
    "spanakopita": "希腊菠菜派", "upma": "印度粗麦粥", "vada": "印度炸豆饼",
    "tabbouleh": "塔布勒沙拉", "rhubarb": "大黄", "ambrosia": "仙果沙拉",
    "guacamole": "牛油果酱", "chutney": "酸辣酱", "lefse": "挪威薄饼",
    "fufu": "非洲木薯糊", "palak paneer": "菠菜奶酪", "channa saag": "鹰嘴豆菠菜",
    "pimiento": "甜椒", "kimchi": "泡菜", "horseradish": "辣根",
    "yokan": "羊羹", "haupia": "夏威夷椰奶糕", "freezer pop": "冰棒",
    "cough drops": "润喉糖", "shirley temple": "秀兰邓波儿鸡尾酒",
    "frescavena": "燕麦饮", "port": "波特酒",
})
ZZ.update({"fritos": "油炸", "dominicana": "多米尼加", "nfs": ""})

# ==== 批次 7：常见营养学词汇收尾 ====
MF.update({
    "mozzarella": "马苏里拉", "parmesan": "帕尔马干酪", "ginger": "姜",
    "fennel": "茴香", "dill": "莳萝", "mint": "薄荷", "wagyu": "和牛",
    "fonio": " fonio 小米", "creamer": "奶精", "infusion": "浸提液",
    "sundae": "圣代", "turnover": "酥角", "multifruit": "什锦水果",
    "novelties": "花样制品", "spreadable": "涂抹型", "pips": "籽",
    "starch": "淀粉", "malted": "麦芽", "popped": "膨化", "fritter": "油炸饼",
    "root": "根茎", "globe": "球茎", "rib": "肋排", "mbs": "大理石纹",
    "domesticated": "家养", "cracked": "碎粒", "ewe": "母羊", "goat": "山羊",
    "stout": "烈性黑啤", "pilsner": "比尔森啤酒", "hard liquor": "烈酒",
})
PB.update({"cob": "棒", "link": "串", "top": "上部", "score": "刻痕",
           "covering": "淋面", "layer": "夹层"})
CL.update({"asian": "亚洲", "aust": "澳洲", "ranch": "牧场",
           "green": "绿", "red": "红", "white": "白", "black": "黑"})
NU.update({"free": "无", "lightened": "减脂", "mild": "淡味", "rich": "浓味",
           "lite": "低脂", "lean": "瘦", "low": "低", "reduced": "减量",
           "partially": "部分", "fully": "全"})
CO.update({"oven": "烤", "hand": "手工", "formulated": "配制",
           "moderately": "中火", "malted": "麦芽制"})
ZZ.update({"gram": "", "usa": "", "vitasoy": "维他奶", "con": "",
           "splash": "", "store": "", "cafe": "", "best": "", "short": "",
           "rock": "", "mock": "", "buffalo": "水牛", "king": ""})
