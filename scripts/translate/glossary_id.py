#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
印尼语（TKPI 2017 / 东南亚）食物名 → 中文词典。

印尼语的书写结构是「主料在前，修饰/部位/烹饪在后」，逗号分段：
    Ikan Patin, bakar          → 鲶鱼，烤        → 烤鲶鱼
    Telur ayam ras, bagian kuning, segar → 鸡蛋，蛋黄部分，生鲜 → 生鲜蛋黄
    Kacang mekah, polong, segar → 刀豆，豆荚，生鲜 → 生鲜豆荚刀豆
即头部是主料，后续段全是修饰 —— 这点恰与英语相反，
所以本模块负责把「后置修饰」翻转成中文语序，再复用英语的组装逻辑。
"""
import re, collections

# ── 主料（具体食物本体）──────────────────────────────────────
MF = {
    # 谷物薯类
    "beras": "大米", "nasi": "米饭", "ketan": "糯米", "padi": "稻谷",
    "jagung": "玉米", "ubi": "甘薯", "ubi jalar": "甘薯", "singkong": "木薯",
    "ketela": "木薯", "kasbi": "木薯", "kaspe": "木薯", "talas": "芋头",
    "bentul": "芋头", "suweg": "魔芋", "gadung": "甘薯", "ganyong": "蕉芋",
    "kentang": "马铃薯", "sagu": "西米", "arek": "西米", "aren": "棕榈糖",
    "terigu": "小麦粉", "tepung": "面粉", "beras ketan": "糯米",
    "emping": "脆片", "kerupuk": "脆饼", "kemplang": "鱼脆饼",
    "bihun": "粉丝", "mi": "面", "mie": "面", "kwetiau": "河粉",
    "roti": "面包", "biskuit": "饼干", "kue": "糕点", "cake": "蛋糕",
    "dodol": "椰糖糕", "getuk": "木薯糕", "tiwul": "木薯饭",
    "bubur": "粥", "ketupat": "马来粽", "lontong": "米糕卷",
    "putu": "蒸糕", "ontbijtkoek": "荷式早餐糕", "bagea": "西米饼",
    "srikaya": "番荔枝酱", "geplak": "椰糖饼", "gelang": "圈饼",
    "martabak": "印尼煎饼", "onde": "麻团", "rempeyek": "脆片饼",
    "keripik": "脆片", "kripik": "脆片", "kerupuk kulit": "皮脆饼",
    "tapai": "发酵糕", "tempe": "天培", "oncom": "发酵豆饼",
    "bungkil": "豆粕", "tauco": "豆酱", "koya": "米粉酥",

    # 蔬菜
    "sayur": "蔬菜", "bayam": "苋菜", "kangkung": "空心菜", "sawi": "小白菜",
    "kol": "甘蓝", "kubis": "甘蓝", "sawi putih": "大白菜", "labu": "南瓜",
    "waluh": "南瓜", "labu siam": "佛手瓜", "jipang": "佛手瓜",
    "oyong": "丝瓜", "gambas": "丝瓜", "terung": "茄子", "terong": "茄子",
    "tomat": "番茄", "wortel": "胡萝卜", "bawang": "葱", "bawang merah": "红葱",
    "bawang putih": "大蒜", "seledri": "芹菜", "selada": "生菜",
    "kucai": "韭菜", "cabai": "辣椒", "rica": "辣椒", "cabe": "辣椒",
    "jahe": "姜", "kunyit": "姜黄", "kencur": "山柰", "lengkuas": "高良姜",
    "sereh": "香茅", "daun": "叶", "kacang": "豆", "komak": "豆",
    "kecipir": "四棱豆", "buncis": "四季豆", "kapri": "豌豆",
    "polong": "豆荚", "kacang panjang": "长豇豆", "kacang tanah": "花生",
    "kedelai": "大豆", "koro": "豆", "tolo": "豇豆", "gude": "木豆",
    "tunggak": "豆", "kacang bogor": "班巴拉豆", "lamtoro": "银合欢豆",
    "kacang mede": "腰果", "kacang mete": "腰果", "kacang kenari": "核桃",
    "kacang mekah": "刀豆", "kacang merah": "红豆", "kacang hijau": "绿豆",
    "kacang ijo": "绿豆", "kacang kedelai": "大豆", "benguk": "巴豆",
    "gembus": "豆腐渣", "tahu": "豆腐", "jamur": "蘑菇", "jamur kuping": "木耳",
    "jamur merang": "草菇", "rebung": "竹笋", "umbut": "笋尖",
    "pakis": "蕨菜", "paku": "蕨菜", "kelor": "辣木叶", "katuk": "守宫木",
    "gendola": "青葙", "leunca": "龙葵", "tekokak": "龙葵",
    "paria": "苦瓜", "pare": "苦瓜", "oyong ": "丝瓜", "belimbing": "杨桃",
    "kedondong": "沙梨", "jengkol": "狗豆", "petai": "臭豆",
    "bunga": "花", "bunga kol": "花椰菜", "kembang kol": "花椰菜",
    "brokoli": "西兰花", "wortel ": "胡萝卜", "bawang goreng": "炸葱酥",
    "daun bawang": "小葱", "daun salam": "月桂叶", "daun jeruk": "柠檬叶",
    "daun kemangi": "罗勒", "daun singkong": "木薯叶", "daun pepaya": "木瓜叶",
    "daun talas": "芋叶", "daun labu": "南瓜叶", "daun melinjo": "melinjo叶",
    "kelor ": "辣木叶", "batang": "茎", "umbi": "块茎",

    # 水果
    "buah": "水果", "pisang": "香蕉", "pepaya": "木瓜", "mangga": "芒果",
    "jeruk": "橙", "apel": "苹果", "anggur": "葡萄", "semangka": "西瓜",
    "melon": "甜瓜", "nanas": "菠萝", "salak": "蛇皮果", "sawo": "人心果",
    "rambutan": "红毛丹", "duku": "龙眼杜古", "langsat": "兰撒",
    "durian": "榴莲", "nangka": "菠萝蜜", "sukun": "面包果",
    "sirsak": "刺果番荔枝", "markisa": "百香果", "jambu": "番石榴",
    "jambu biji": "番石榴", "jambu air": "蒲桃", "jambu monyet": "腰果果",
    "kesemek": "柿子", "gandaria": "杏李", "mengkudu": "诺丽果",
    "kurma": "枣", "kismis": "葡萄干", "kelapa": "椰子", "alpukat": "牛油果",
    "advokat": "牛油果", "kweni": "芒果", "bacang": "芒果",
    "kedondong ": "沙梨", "buah naga": "火龙果", "sirsat": "刺果番荔枝",
    "matoa": "马托阿果", "buni": "蒲桃", "kawista": "木橘",

    # 肉蛋
    "daging": "肉", "sapi": "牛", "daging sapi": "牛肉", "kerbau": "水牛",
    "kambing": "山羊", "domba": "绵羊", "babi": "猪", "ayam": "鸡",
    "itik": "鸭", "bebek": "鸭", "burung": "鸟", "kuda": "马",
    "penyu": "龟", "kalkun": "火鸡", "puyuh": "鹌鹑",
    "telur": "蛋", "telur ayam": "鸡蛋", "telur bebek": "鸭蛋",
    "telur puyuh": "鹌鹑蛋", "telur itik": "鸭蛋",
    "ikan": "鱼", "udang": "虾", "cumi": "鱿鱼", "cumi cumi": "鱿鱼",
    "sotong": "乌贼", "kerang": "贝", "tiram": "牡蛎", "kepiting": "蟹",
    "rajungan": "梭子蟹", "lobster": "龙虾", "teripang": "海参",
    "jantung": "心", "hati": "肝", "ginjal": "腰", "paru": "肺",
    "limpa": "脾", "otak": "脑", "usus": "肠", "babat": "瘤胃",
    "jeroan": "内脏", "kulit": "皮", "darah": "血", "tulang": "骨",
    "dada": "胸", "paha": "腿", "sayap": "翅", "kepala": "头",
    "ekor": "尾", "lidah": "舌", "kaki": "脚", "lemak": "脂肪",
    "sosis": "香肠", "abon": "肉松", "dendeng": "肉干", "sate": "沙嗲",
    "bakso": "肉丸", "pempek": "鱼糕", "otak otak": "鱼卷",
    "gelondongan": "整只", "sosis sapi": "牛肉肠",

    # 水产细分
    "bandeng": "遮目鱼", "mujahir": "罗非鱼", "nila": "罗非鱼",
    "lele": "鲶鱼", "patin": "巴沙鱼", "baung": "鲿鱼", "lais": "鲿鱼",
    "gabus": "鳢鱼", "betok": "攀鲈", "belut": "黄鳝", "sidat": "鳗鲡",
    "cakalang": "鲣鱼", "tongkol": "鲔鱼", "tuna": "金枪鱼",
    "kembung": "鲭鱼", "selar": "鲹鱼", "layang": "鲹鱼", "teri": "鳀鱼",
    "peda": "咸鱼", "pindang": "腌鱼", "terubuk": "鲥鱼",
    "kerapu": "石斑鱼", "kakap": "笛鲷", "kakap merah": "红笛鲷",
    "tenggiri": "马鲛鱼", "hiu": "鲨鱼", "pari": "鳐鱼", "belida": "刀鱼",
    "bawal": "鲳鱼", "gurame": "丝足鲈", "betutu": "黑鱼",
    "salmon": "三文鱼", "mujair": "罗非鱼", "jambal": "鲶鱼",
    "papuyu": "攀鲈", "saluang": "鲿鱼", "gete": "鲹鱼",
    "kepiting ": "蟹", "udang ": "虾", "rumput laut": "海藻",
    "rumput": "草", "agar": "琼脂",

    # 乳制品与油
    "susu": "牛奶", "susu bubuk": "奶粉", "susu kental": "炼乳",
    "mentega": "黄油", "margarin": "人造黄油", "keju": "奶酪",
    "yoghurt": "酸奶", "es krim": "冰淇淋", "krim": "奶油",
    "minyak": "油", "minyak kelapa": "椰子油", "minyak goreng": "食用油",
    "minyak sawit": "棕榈油", "santan": "椰浆", "kelapa ": "椰子",
    "gula": "糖", "gula merah": "红糖", "gula pasir": "白砂糖",
    "madu": "蜂蜜", "garam": "盐", "kecap": "酱油", "kecap manis": "甜酱油",
    "kecap asin": "咸酱油", "cuka": "醋", "saus": "酱", "sambal": "辣椒酱",
    "bumbu": "调味料", "rempah": "香辛料", "kayu manis": "肉桂",
    "cengkeh": "丁香", "pala": "肉豆蔻", "kemiri": "石栗",
    "wijen": "芝麻", "ketumbar": "香菜籽", "merica": "胡椒",
    "hineka": "香辛料", "hinela": "香辛料", "rasa": "风味",
    "teh": "茶", "kopi": "咖啡", "coklat": "巧克力", "cokelat": "巧克力",
    "sirup": "糖浆", "jus": "果汁", "es": "冰", "air": "水",
    "air kelapa": "椰子水", "minuman": "饮料",
    "bir": "啤酒", "anggur merah": "红葡萄酒", "arak": "白酒",
    "sirup gula": "糖浆", "susu kental manis": "甜炼乳",
    "gula kelapa": "椰糖", "gula aren": "棕榈糖",
    "bawang putih ": "大蒜", "jahe ": "姜",
}

# ── 部位/形态（放主料前）────────────────────────────────────
PB = {
    "daun": "叶", "batang": "茎", "umbi": "块茎", "akar": "根", "biji": "籽",
    "buah": "果", "bunga": "花", "polong": "荚", "kulit": "皮",
    "daging": "肉", "isi": "肉", "bagian": "", "potongan": "切块",
    "tulang": "带骨", "utuh": "整只", "paha": "腿", "dada": "胸",
    "sayap": "翅", "kepala": "头", "ekor": "尾", "kaki": "脚",
    "ginjal": "腰", "hati": "肝", "jantung": "心", "otak": "脑",
    "mata": "眼", "perut": "肚", "usus": "肠", "lidah": "舌",
    "kuning": "蛋黄", "putih": "蛋清", "merah": "红", "hijau": "绿",
    "hitam": "黑", "besar": "大", "sedang": "中", "kecil": "小",
    "muda": "嫩", "tua": "老", "panjang": "长", "pendek": "短",
    "tebal": "厚", "tipis": "薄", "kurus": "瘦", "gemuk": "肥",
    "manis": "甜", "asam": "酸", "asin": "咸", "pahit": "苦",
    "pedas": "辣", "gurih": "鲜香", "hutan": "野生", "pohon": "树生",
}

# ── 状态/加工/烹饪 ─────────────────────────────────────────
ST = {
    "segar": "生鲜", "mentah": "生", "matang": "熟", "setengah matang": "半熟",
    "kering": "干制", "basah": "湿", "beku": "冷冻", "dingin": "冷藏",
    "kaleng": "罐装", "instan": "即食", "murni": "纯", "olahan": "加工",
    "tradisional": "传统", "modern": "现代",
}
CO = {
    "masak": "熟", "masakan": "烹制", "goreng": "油炸", "bakar": "烤",
    "panggang": "烘烤", "rebus": "水煮", "kukus": "蒸", "tumis": "炒",
    "sangrai": "干炒", "sangan": "干炒", "giling": "碾磨", "tumbuk": "捣碎",
    "pipil": "脱粒", "kukus ": "蒸", "bacem": "卤", "pepes": "蕉叶蒸",
    "pindang ": "腌煮", "ungkep": "香卤", "semur": "炖", "tongseng": "炖",
    "rendang": "仁当", "gulai": "咖喱汤", "kalio": "咖喱收汁",
    "sop": "汤", "coto": "牛肉汤", "soto": "汤", "lawar": "凉拌",
    "pallu": "姜黄炖", "nasu": "炖", "dideh": "汤", "kohu": "烤竹筒",
    "kabobs": "烤肉串", "kebab": "烤肉串", "shabu": "涮煮",
    "tapai ": "发酵", "fermentasi": "发酵", "asap": "烟熏", "asin ": "盐渍",
    "gorengan": "油炸品", "kukus": "蒸",
}
PH = {
    "bubuk": "粉状", "halus": "细磨", "kasar": "粗磨", "potong": "切块",
    "iris": "切片", "serut": "刨丝", "parut": "磨碎", "gepuk": "捶打",
    "suwir": "撕裂", "utuh ": "整只", "lembar": "片", "butir": "粒",
    "cair": "液态", "kental": "浓稠", "encer": "稀薄", "tebal ": "厚",
    "ampal": "碎块", "gumpalan": "团块", "tepung ": "粉",
}
CN = {
    "bali": "巴厘式", "padang": "巴东式", "banjar": "班贾尔式",
    "madura": "马都拉式", "sunda": "巽他式", "jawa": "爪哇式",
    "manado": "万鸦老式", "aceh": "亚齐式", "palembang": "巨港式",
    "bogor": "茂物式", "sukabumi": "苏卡布米式", "pasundan": "巽他式",
    "lampung": "楠榜式", "belitung": "勿里洞式", "ambon": "安汶式",
    "mangkasara": "望加锡式", "china": "中式", "tionghoa": "中式",
    "europe": "欧式", "belanda": "荷式", "texas": "德州式",
    "kentucky": "肯塔基式", "church": "Church", "kfc": "肯德基",
    "teriyaki": "照烧", "korea": "韩式", "jepang": "日式",
}
SF = {
    "var": "变种", "varietas": "变种", "jenis": "品种",
    "ras": "品种", "spesies": "品种",
}
ZZ = {
    "bagian": "", "dengan": "", "tanpa": "", "dan": "", "atau": "",
    "dalam": "", "yang": "", "untuk": "", "dari": "", "di": "", "ke": "",
    "ada": "", "tidak": "", "cap": "", "biasa": "", "lain": "",
    "sejenis": "", "sebagai": "", "merupakan": "", "hasil": "",
}

NU = {}
PR = {}
QT = {}
DICTS = [("MF", MF), ("PB", PB), ("SF", SF), ("ST", ST), ("CO", CO),
         ("PH", PH), ("CN", CN), ("ZZ", ZZ)]
CLS_ORDER = {"ST": 1, "CO": 2, "PH": 3, "CN": 4}
WORD_RANK = {"segar": 4, "mentah": 6, "matang": 3, "kering": 5, "goreng": 7,
             "bakar": 7, "rebus": 6, "kukus": 6, "tumis": 6, "masak": 1}
_EMPTY = ()


def _nm(s):
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', str(s).lower())).strip()


POOL_ID = {}
for _c, _d in DICTS:
    for _k, _v in _d.items():
        _n = _nm(_k)
        if _n and _n not in POOL_ID:
            POOL_ID[_n] = (_c, _v)
        if _n:
            for _p in (_n + "s",):
                POOL_ID.setdefault(_p, (_c, _v))

RX = re.compile(r'(?<![a-z0-9])(?:'
                + "|".join(re.escape(k) for k in sorted(POOL_ID, key=len, reverse=True))
                + r')(?![a-z0-9])')


def translate(name):
    """印尼语名 → (中文, 状态, 方法, 未识别词)。

    注意：复用英文引擎的 scan/assemble，但需要「先切句再扫描」——
    因为印尼语的 scan 必须走自己的码表，故本函数自带扫描循环。
    """
    if not name or not str(name).strip():
        return None, "empty", "id_dict", []
    s = re.sub(r'\([^)]*\)', ' ', str(name))
    s = re.sub(r'[^A-Za-z0-9,\s]', ' ', s)
    parts = [p.strip() for p in re.split(r'[,;]', s) if p.strip()]
    if not parts:
        return None, "untranslated", "id_dict", []

    import translate_names as T
    norm_parts = [_nm(p) for p in parts]
    norm_parts = [p for p in norm_parts if p]
    if not norm_parts:
        return None, "untranslated", "id_dict", []

    # 逐段扫描，坐标落在「拼接串」上，便于区分头段 / 修饰段
    whole, spans, pos = [], [], 0
    for p in norm_parts:
        whole.append(p)
        spans.append((pos, pos + len(p)))
        pos += len(p) + 1
    whole = " ".join(whole)

    hits_all = []
    for (s0, s1) in spans:
        hits_all += T.scan(whole[s0:s1], s0, lang="id")
    head_end = spans[0][1]
    head_hits = [h for h in hits_all if h[3] < head_end]
    mod_hits = [h for h in hits_all if h[3] >= head_end]

    cn = re.sub(r'\s+', '', T.assemble(head_hits, mod_hits, lang="id"))
    unk = T.unknown_tokens(whole, hits_all)
    if not cn:
        return None, "untranslated", "id_dict", unk
    return cn, ("partial" if unk else "ok"), "id_dict", unk
