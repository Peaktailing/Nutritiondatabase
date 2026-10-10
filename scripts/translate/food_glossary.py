#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
英文名食物「短语词典」：整词/词组直接命中，优先级高于逐词组合。
翻译 engine 用「单次正则全词盆匹配」，天然保证最长短语优先
（修掉了此前贪心逐条查找导致 whole wheat 被切出 whole 的问题）。
"""
# 主料固定说法（小写 key，可含空格/连字符）
FOOD_PHRASES = {
    # ---- 肉类
    "beef": "牛肉", "pork": "猪肉", "lamb": "羊肉", "mutton": "羊肉",
    "chicken": "鸡肉", "turkey": "火鸡肉", "veal": "小牛肉", "duck": "鸭肉",
    "goose": "鹅肉", "rabbit": "兔肉", "horse": "马肉", "game meat": "野味肉",
    "venison": "鹿肉", "offal": "内脏", "sweetbread": "胰脏", "meat": "肉",
    "bacon": "培根", "ham": "火腿", "sausage": "香肠",
    "frankfurter": "法兰克福香肠", "salami": "萨拉米肠", "pepperoni": "辣香肠",
    "chorizo": "西班牙辣肠", "pate": "肉酱", "meatballs": "肉丸",
    "meat loaf": "肉糕", "meatloaf": "肉糕", "scrapple": "玉米肉饼",
    "hot dog": "热狗肠", "hotdog": "热狗肠", "braunschweiger": "熏肝肠",
    "bologna": "博洛尼亚香肠", "knockwurst": "德式蒜肠", "bratwurst": "德式烤肠",
    "liverwurst": "肝泥肠", "headcheese": "头肉冻", "kielbasa": "波兰香肠",
    "leberkase": "肝酪饼", "ground beef": "绞牛肉",

    # ---- 部位（作主料出现，如 "Beef, short ribs" 里 ribs 单独成段）
    "rib": "肋排", "ribs": "肋排", "short ribs": "短肋",
    "breast": "胸肉", "thigh": "腿肉", "drumstick": "小腿",
    "wing": "翅", "wings": "翅", "loin": "里脊", "chuck": "肩肉",
    "round": "后腿肉", "sirloin": "西冷", "tenderloin": "里脊",
    "flank": "腹肉", "shank": "小腿肉", "shoulder": "肩肉", "rump": "臀肉",
    "brisket": "胸肉", "plate": "腹胁肉", "carcass": "胴体",
    "variety meats": "杂肉", "liver": "肝", "heart": "心", "kidney": "腰",
    "tongue": "舌", "brain": "脑", "tripe": "肚", "gizzard": "肫",
    "spleen": "脾", "lungs": "肺", "tail": "尾", "feet": "蹄",
    "oxtail": "牛尾", "leg": "腿", "neck": "颈", "belly": "腹",
    "pork ribs": "猪肋排", "beef ribs": "牛肋排", "pork chop": "猪排",

    # ---- 水产
    "fish": "鱼", "shrimp": "虾", "prawn": "对虾", "crab": "蟹",
    "lobster": "龙虾", "crayfish": "小龙虾", "clam": "蛤蜊", "oyster": "牡蛎",
    "mussel": "贻贝", "scallop": "扇贝", "squid": "鱿鱼", "octopus": "章鱼",
    "eel": "鳗鱼", "salmon": "三文鱼", "tuna": "金枪鱼", "cod": "鳕鱼",
    "haddock": "黑线鳕", "halibut": "比目鱼", "trout": "鳟鱼", "mackerel": "鲭鱼",
    "herring": "鲱鱼", "sardine": "沙丁鱼", "anchovy": "凤尾鱼", "perch": "鲈鱼",
    "bass": "鲈鱼", "catfish": "鲶鱼", "tilapia": "罗非鱼", "swordfish": "剑鱼",
    "monkfish": "鮟鱇鱼", "pollock": "狭鳕", "plaice": "鲽鱼", "sole": "鳎鱼",
    "sturgeon": "鲟鱼", "roe": "鱼卵", "caviar": "鱼子酱", "surimi": "鱼糜",
    "fish sticks": "鱼条", "fish fillet": "鱼柳", "fish cake": "鱼糕",
    "carp": "鲤鱼", "croaker": "黄鱼", "rockfish": "平鲉",
    "sablefish": "裸盖鱼", "smelt": "胡瓜鱼",

    # ---- 乳蛋制品
    "milk": "牛奶", "dry milk": "奶粉", "condensed milk": "炼乳",
    "evaporated milk": "淡奶", "buttermilk": "酪乳", "whey": "乳清",
    "cream": "奶油", "sour cream": "酸奶油", "whipped cream": "搅打奶油",
    "whipping cream": "稀奶油", "ice cream": "冰淇淋", "custard": "卡仕达酱",
    "yogurt": "酸奶", "yoghurt": "酸奶", "kefir": "开菲尔",
    "egg": "鸡蛋", "eggs": "鸡蛋", "egg white": "蛋清", "egg yolk": "蛋黄",
    "whole egg": "全蛋", "dried egg": "蛋粉", "egg substitute": "代蛋品",
    "butter": "黄油", "margarine": "人造黄油", "butter oil": "奶油脂肪",
    "quiche": "乳蛋饼", "cheese": "奶酪",
    "cheddar cheese": "切达奶酪", "cottage cheese": "白软干酪",
    "cream cheese": "奶油奶酪", "mozzarella cheese": "马苏里拉奶酪",
    "parmesan cheese": "帕玛森奶酪", "swiss cheese": "瑞士奶酪",
    "gouda cheese": "高达奶酪", "brie cheese": "布里奶酪",
    "ricotta cheese": "里科塔奶酪", "feta cheese": "菲达奶酪",
    "blue cheese": "蓝纹奶酪", "provolone cheese": "普罗沃隆奶酪",
    "gruyere cheese": "格鲁耶尔奶酪", "munster cheese": "芒斯特奶酪",
    "cheese food": "再制奶酪", "cheese spread": "涂抹奶酪",

    # ---- 谷物主食（复合词必须整条收录，否则被切错）
    "rice": "大米", "brown rice": "糙米", "white rice": "白米",
    "wild rice": "菰米", "rice noodles": "米粉", "rice flour": "米粉",
    "bread": "面包", "white bread": "白面包", "whole wheat bread": "全麦面包",
    "whole-wheat bread": "全麦面包", "rye bread": "黑麦面包",
    "pumpernickel bread": "粗黑麦面包", "pita bread": "皮塔饼",
    "french bread": "法式面包", "italian bread": "意式面包",
    "naan": "馕饼", "bagel": "贝果", "bun": "小面包", "roll": "小圆面包",
    "croissant": "牛角包", "english muffin": "英式玛芬",
    "english muffins": "英式玛芬", "pancakes": "薄煎饼", "waffles": "华夫饼",
    "french toast": "法式吐司", "muffin": "玛芬", "muffins": "玛芬",
    "melba toast": "薄脆吐司", "pasta": "意面", "spaghetti": "意大利面",
    "macaroni": "通心粉", "noodles": "面条", "noodle": "面条",
    "egg noodles": "鸡蛋面", "ramen": "拉面", "couscous": "古斯米",
    "polenta": "玉米糕", "lasagna": "千层面", "toast": "吐司",
    "cereal": "谷物片", "cereals ready-to-eat": "即食谷物",
    "cereals": "谷物", "oatmeal": "燕麦粥", "oats": "燕麦", "oat": "燕麦",
    "wheat": "小麦", "whole wheat": "全麦", "whole-wheat": "全麦",
    "wheat flour": "小麦粉", "whole wheat flour": "全麦粉",
    "flour": "面粉", "barley": "大麦", "corn": "玉米", "maize": "玉米",
    "cornmeal": "玉米面", "cornstarch": "玉米淀粉", "rye": "黑麦",
    "millet": "小米", "sorghum": "高粱", "quinoa": "藜麦",
    "buckwheat": "荞麦", "amaranth": "苋菜籽", "semolina": "粗粒小麦粉",
    "farina": "麦粉", "matzo": "无酵饼", "grits": "玉米糁", "stuffing": "填料",

    # ---- 蔬菜
    "potato": "马铃薯", "potatoes": "马铃薯", "sweet potato": "甘薯",
    "sweet potatoes": "甘薯", "mashed potato": "土豆泥",
    "mashed potatoes": "土豆泥", "french fries": "炸薯条",
    "potato chips": "薯片", "potato salad": "土豆沙拉", "hash brown": "炸薯饼",
    "tomato": "番茄", "tomatoes": "番茄", "onion": "洋葱", "onions": "洋葱",
    "leek": "韭葱", "garlic": "大蒜", "shallot": "小红葱",
    "carrot": "胡萝卜", "carrots": "胡萝卜", "celery": "芹菜",
    "celeriac": "根芹", "cabbage": "甘蓝", "chinese cabbage": "大白菜",
    "red cabbage": "紫甘蓝", "cauliflower": "花椰菜", "broccoli": "西兰花",
    "kale": "羽衣甘蓝", "spinach": "菠菜", "lettuce": "生菜",
    "romaine": "罗马生菜", "endive": "菊苣", "chicory": "菊苣",
    "arugula": "芝麻菜", "radish": "萝卜", "turnip": "芜菁",
    "beet": "甜菜", "beetroot": "甜菜根", "parsnip": "欧防风",
    "rutabaga": "芜菁甘蓝", "kohlrabi": "苤蓝", "cucumber": "黄瓜",
    "zucchini": "西葫芦", "courgette": "西葫芦", "squash": "南瓜",
    "pumpkin": "南瓜", "eggplant": "茄子", "aubergine": "茄子",
    "pepper": "辣椒", "peppers": "辣椒", "sweet pepper": "甜椒",
    "chili pepper": "辣椒", "mushroom": "蘑菇", "mushrooms": "蘑菇",
    "asparagus": "芦笋", "artichoke": "洋蓟", "beans": "豆", "bean": "豆",
    "green beans": "四季豆", "snap beans": "四季豆", "lima beans": "利马豆",
    "peas": "豌豆", "pea": "豌豆", "garden peas": "豌豆",
    "chickpeas": "鹰嘴豆", "lentils": "小扁豆", "lentil": "小扁豆",
    "soybeans": "大豆", "bean sprouts": "豆芽", "okra": "秋葵",
    "snow peas": "荷兰豆", "succotash": "玉米豆",

    # ---- 水果
    "apple": "苹果", "apples": "苹果", "banana": "香蕉", "orange": "橙",
    "lemon": "柠檬", "lime": "青柠", "grapefruit": "西柚", "tangerine": "橘",
    "strawberry": "草莓", "strawberries": "草莓", "blueberry": "蓝莓",
    "raspberry": "树莓", "blackberry": "黑莓", "cranberry": "蔓越莓",
    "grape": "葡萄", "grapes": "葡萄", "raisin": "葡萄干", "raisins": "葡萄干",
    "peach": "桃", "pear": "梨", "plum": "李", "cherry": "樱桃",
    "apricot": "杏", "nectarine": "油桃", "mango": "芒果",
    "pineapple": "菠萝", "papaya": "木瓜", "kiwi": "猕猴桃",
    "watermelon": "西瓜", "melon": "甜瓜", "cantaloupe": "哈密瓜",
    "honeydew": "白兰瓜", "avocado": "牛油果", "fig": "无花果",
    "date": "枣", "pomegranate": "石榴", "persimmon": "柿子",
    "plantain": "大蕉", "passion fruit": "百香果", "guava": "番石榴",
    "lychee": "荔枝", "clementine": "小柑橘",

    # ---- 坚果种子
    "almond": "杏仁", "walnut": "核桃", "pecan": "碧根果",
    "cashew": "腰果", "pistachio": "开心果", "hazelnut": "榛子",
    "peanut": "花生", "peanuts": "花生", "chestnut": "栗子",
    "macadamia": "澳洲坚果", "pine nut": "松子", "sunflower seed": "葵花籽",
    "pumpkin seed": "南瓜籽", "sesame seed": "芝麻", "flaxseed": "亚麻籽",
    "chia": "奇亚籽", "nut": "坚果", "nuts": "坚果", "seeds": "种子",
    "seed": "种子", "mixed nuts": "混合坚果", "trail mix": "什锦果仁",
    "poppy seed": "罂粟籽", "peanut butter": "花生酱",

    # ---- 油脂糖
    "oil": "油", "olive oil": "橄榄油", "corn oil": "玉米油",
    "sunflower oil": "葵花籽油", "canola oil": "芥花油",
    "peanut oil": "花生油", "soybean oil": "大豆油", "coconut oil": "椰子油",
    "palm oil": "棕榈油", "sesame oil": "芝麻油", "lard": "猪油",
    "shortening": "起酥油", "salad dressing": "沙拉酱",
    "mayonnaise": "蛋黄酱", "vinaigrette": "油醋汁", "vinegar": "醋",
    "sugar": "糖", "honey": "蜂蜜", "syrup": "糖浆", "molasses": "糖蜜",
    "jelly": "果冻", "jam": "果酱", "chocolate": "巧克力",
    "candy": "糖果", "candies": "糖果", "marshmallow": "棉花糖",
    "nougat": "牛轧糖", "caramel": "焦糖", "fudge": "软糖",
    "gelatin dessert": "果冻甜品", "pudding": "布丁", "puddings": "布丁",
    "popsicle": "冰棍", "sherbet": "果汁冰糕", "frozen yogurt": "冻酸奶",

    # ---- 烘焙零食
    "cake": "蛋糕", "cookie": "曲奇", "cookies": "曲奇", "biscuit": "饼干",
    "cracker": "薄脆饼", "crackers": "薄脆饼", "pie": "派", "tart": "塔",
    "pastry": "酥皮点心", "donut": "甜甜圈", "doughnut": "甜甜圈",
    "brownies": "布朗尼", "cupcake": "杯子蛋糕", "cheesecake": "芝士蛋糕",
    "pretzel": "蝴蝶脆饼", "pretzels": "蝴蝶脆饼", "popcorn": "爆米花",
    "snack": "零食", "snacks": "零食", "chips": "薯片", "scone": "司康",
    "strudel": "果馅卷", "cinnamon roll": "肉桂卷", "pie crust": "派皮",
    "tortilla": "玉米饼", "gravy": "肉汁", "white sauce": "白汁",

    # ---- 饮品
    "coffee": "咖啡", "tea": "茶", "beer": "啤酒", "wine": "葡萄酒",
    "cocoa": "可可", "soda": "汽水", "cola": "可乐", "lemonade": "柠檬水",
    "juice": "汁", "water": "水", "beverage": "饮料", "beverages": "饮料",
    "milkshake": "奶昔", "milk shake": "奶昔", "smoothie": "果昔",
    "egg nog": "蛋奶酒", "alcoholic beverage": "酒精饮料",
    "liqueur": "利口酒", "brandy": "白兰地", "whiskey": "威士忌",
    "rum": "朗姆酒", "gin": "金酒", "vodka": "伏特加",
    "mineral still water": "静止矿泉水", "energy drink": "能量饮料",
    "sports drink": "运动饮料",

    # ---- 零售/餐饮品牌
    "mcdonald's": "麦当劳", "mcdonalds": "麦当劳", "burger king": "汉堡王",
    "taco bell": "塔可钟", "wendy's": "温迪汉堡", "subway": "赛百味",
    "kfc": "肯德基", "pizza hut": "必胜客", "domino's": "达美乐",
    "starbucks": "星巴克", "restaurant": "餐厅", "fast foods": "快餐",
    "fast food": "快餐", "crust": "饼皮",

    # ---- 综合料理
    "soup": "汤", "salad": "沙拉", "sandwich": "三明治", "pizza": "披萨",
    "burger": "汉堡", "curry": "咖喱", "stew": "炖菜", "casserole": "砂锅菜",
    "dumpling": "饺子", "bhaji": "炸洋葱饼", "samosa": "咖喱角",
    "tamale": "玉米粽", "burrito": "墨西哥卷饼", "taco": "塔可",
    "enchilada": "卷饼", "quesadilla": "芝士饼", "chili": "辣酱",
    "chili con carne": "辣肉酱", "chow mein": "炒面", "chop suey": "杂碎",
    "egg roll": "蛋卷", "empanada": "炸馅饼", "falafel": "炸豆丸子",
    "hummus": "鹰嘴豆泥", "risotto": "意大利烩饭", "paella": "西班牙海鲜饭",
    "ratatouille": "法式杂菜烩", "sushi": "寿司", "granola": "格兰诺拉麦片",
    "nachos": "玉米片", "bruschetta": "意式烤面包",
    "coleslaw": "凉拌卷心菜", "moussaka": "希腊茄盒", "kebab": "烤肉串",
    "chicken nuggets": "鸡块", "chicken tenders": "鸡柳条",
    "chicken wings": "鸡翅", "chicken breast": "鸡胸肉",
    "chicken patty": "鸡肉饼", "chicken thigh": "鸡腿肉",
    "chicken drumstick": "鸡小腿", "chicken liver": "鸡肝",

    # ---- 婴幼儿
    "babyfood": "婴儿食品", "baby food": "婴儿食品",
    "infant formula": "婴儿配方奶粉", "teething biscuit": "磨牙饼干",
    "baby food junior": "较大婴儿食品", "baby food toddler": "幼儿食品",

    # ---- 调味料与其他
    "salt": "盐", "spices": "香辛料", "herbs": "香草", "seasoning": "调味料",
    "yeast": "酵母", "baking powder": "泡打粉", "gelatin": "明胶",
    "cocoa powder": "可可粉", "soy sauce": "酱油", "mustard": "芥末",
    "ketchup": "番茄酱", "catsup": "番茄酱", "tomato sauce": "番茄酱汁",
    "barbecue sauce": "烧烤酱", "salsa": "莎莎酱", "pesto": "青酱",
    "relish": "调味酱菜", "pickle": "腌菜", "pickles": "腌菜",
    "olive": "橄榄", "tofu": "豆腐", "tempeh": "天培", "seitan": "面筋",
    "nutritional yeast": "营养酵母",
}

# 修饰词：状态/加工/含量/形态
MODIFIERS = {
    # ---- 状态（生/加工）—— 最前置
    "raw": "生", "fresh": "新鲜", "canned": "罐头", "frozen": "冷冻",
    "dried": "干制", "dehydrated": "脱水", "boiled": "水煮",
    "hard-boiled": "水煮", "fried": "油炸", "deep fried": "油炸",
    "baked": "烤", "oven-roasted": "烤", "grilled": "炙烤",
    "broiled": "炙烤", "roasted": "烘烤", "stewed": "炖", "braised": "焖",
    "steamed": "蒸", "toasted": "烘烤", "cooked": "熟", "simmered": "煨",
    "poached": "水煮", "sauteed": "嫩煎", "pan fried": "煎",
    "stir fried": "炒", "smoked": "熏制", "cured": "腌制",
    "pickled": "腌渍", "salted": "盐渍", "prepared": "预制",
    "commercial": "商品", "commercially prepared": "市售",
    "homemade": "自制", "home prepared": "家常制作",
    "prepackaged": "预包装", "refrigerated": "冷藏", "bottled": "瓶装",
    "canned or bottled": "罐装或瓶装", "drained solids": "沥干固形物",
    "overcooked": "过熟",

    # ---- 含量/版本
    "reduced fat": "减脂", "reduced calorie": "减热量", "low fat": "低脂",
    "nonfat": "脱脂", "fat free": "脱脂", "fat-free": "脱脂",
    "less fat": "减脂", "skim": "脱脂", "part skim": "部分脱脂",
    "light": "清淡", "whole milk": "全脂", "full fat": "全脂",
    "whole": "整个", "fortified": "强化", "unfortified": "未强化",
    "enriched": "强化", "unbleached": "未漂白", "unsalted": "无盐",
    "low sodium": "低钠", "no salt added": "无添加盐",
    "with added salt": "加盐", "unsweetened": "无糖",
    "sweetened": "加糖", "low calorie": "低热量", "sugar free": "无糖",
    "dietetic": "食疗用", "plain": "原味", "flavored": "调味",
    "artificially flavored": "人工调味", "high protein": "高蛋白",
    "high fiber": "高纤维", "regular": "常规", "from concentrate": "浓缩还原",
    "ready-to-eat": "即食", "instant": "即食", "self-rising": "自发",
    "self rising": "自发", "un": "",

    # ---- 部位/取材
    "lean only": "仅瘦肉", "lean": "瘦肉", "separable lean": "可分离瘦肉",
    "separable fat": "可分离脂肪", "skinless": "去皮", "with skin": "带皮",
    "skin only": "仅皮", "boneless": "去骨", "with bone": "带骨",
    "meat only": "仅肉", "flesh only": "仅果肉", "with peel": "带皮",
    "peeled": "去皮", "pitted": "去核", "seeded": "去籽", "cored": "去核",
    "pieces": "块", "chunks": "块", "slices": "片", "diced": "丁",
    "chopped": "碎", "crumbled": "碎屑", "ground": "绞碎",
    "minced": "剁碎", "shredded": "切丝", "grated": "磨碎",
    "julienne": "切丝", "halves": "半块", "cooked meat only": "仅熟肉",

    # ---- 风味/国别
    "french": "法式", "italian": "意式", "mexican": "墨西哥式",
    "chinese": "中式", "japanese": "日式", "greek": "希腊式",
    "spanish": "西班牙式", "german": "德式", "swiss": "瑞士",
    "russian": "俄式", "thousand island": "千岛", "ranch": "牧场",
    "caesar": "凯撒",
}

# 纯噪声词：直接丢弃，不进中文名
STOP = {
    "and", "or", "with", "without", "as", "to", "from", "in", "on", "of",
    "the", "a", "an", "only", "s", "plus", "includes", "not", "no",
    "make", "made", "type", "all", "each", "per", "contents", "weighed",
    "purchase", "yield", "approximate", "average", "retail", "trimmed",
    "separable", "wise", "adjusted", "based", "usda", "lbs", "mg", "iu",
    "choice", "select", "grade", "commercial", "prepared", "weighed.",
    "raw", "cooked", "native", "regular", "plain", "whole",
}

# 已提炼	elsewhere(修饰段里命中 FOOD_PHRASES 时用 getEMEdit避免在 lcdAGAIN 重复 masterskieh
IGNORE_DUP = set()
