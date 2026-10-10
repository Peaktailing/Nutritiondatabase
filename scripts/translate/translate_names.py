#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把所有来源的食物名称翻译成中文，写入 norm_food.name_cn。

为什么不用在线翻译（重要）：
  实测 MyMemory 把 "cheddar cheese" 译成粤语「車打芝士」，Google 端点不可达。
  食物专名交给通用 MT，质量不可控且不可复现 —— 拒绝。

为什么用词典而不是逐条翻译：
  21,657 条英文名只有 5,310 个唯一 token，TOP1200 覆盖 92% 词频。
  给 token 一次性定译名 + 按中文语序重组，是这里唯一理性的做法。

匹配机制（关键）：
  所有词典 key 统一「连字符→空格」归一化后按长度降序拼成一个正则 alternation，
  对整条名称做一次 finditer —— Python re 取最左成功分支，故天然最长短语优先，
  彻底杜绝 whole-wheat 被切成 whole、fat-free 被切成 fat 这类错误。

语序由中文习惯决定（见 assemble），并为 ST/CO 类设置了 rank，
使 "cooked, hard-boiled" 只产出「水煮」而不会产出「熟水煮」。

未收录词不丢弃：原样保留英文，translate_status 记为 partial，便于后续迭代。
"""
import sqlite3, re, os, sys, collections, unicodedata

DB = os.environ.get("FDC_DB", "/workspace/fdc/nutrition.db")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import glossary_en as G          # noqa: E402
try:
    import glossary_id as GI     # noqa: E402
except ImportError:
    GI = None

# ────────────────────────── 词典装载 ──────────────────────────
DICTS = [("MF", G.MF), ("PB", G.PB), ("SF", G.SF), ("QT", G.QT),
         ("ST", G.ST), ("CO", G.CO), ("PR", G.PR), ("NU", G.NU),
         ("CL", G.CL), ("CN", G.CN), ("PH", G.PH), ("ZZ", G.ZZ)]
# 印尼语词典只在处理 ID 来源时启用，避免与英语同名 key（如 daun/daging）互相污染
if GI is not None:
    DICTS += [("_id_" + c, d) for c, d in GI.DICTS]
    for _k, _v in GI.CLS_ORDER.items():
        G.CLS_ORDER.setdefault(_k, _v)

PH_SUFFIX = set(getattr(G, "PH_SUFFIX", set()))
CLS_ORDER = G.CLS_ORDER
WORD_RANK = G.WORD_RANK
QT_PRE = {"skinless", "boneless", "peeled", "pitted", "seeded", "cored",
          "hulled", "shelled", "husked", "trimmed lean"}

# 印尼语：这些部位词要贴在主料「之后」（苋菜叶 / 鸡蛋黄），其余修饰在最后
PB_HEAD = {"叶", "茎", "根", "籽", "果", "花", "荚", "皮", "肉", "骨", "带骨",
           "整只", "腿", "胸", "翅", "头", "尾", "脚", "腰", "肝", "心", "脑",
           "眼", "肚", "肠", "舌", "蛋黄", "蛋清"}
IS_ID = False      # translate_row 处理 ID 时临时置 True
STOP = G.STOP


def _nm(s):
    """归一化：小写、变音符号折叠（法语 végé→vege）、非字母数字转空格、压空格"""
    t = unicodedata.normalize('NFKD', str(s).lower())
    t = ''.join(c for c in t if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', t)).strip()


def _plurals(k):
    """由单数生成常见复数变体"""
    out = [k + "s"]
    if k.endswith("y") and len(k) > 2 and k[-2] not in "aeiou":
        out.append(k[:-1] + "ies")
    elif k.endswith(("s", "x", "ch", "sh")):
        out.append(k + "es")
    return out


POOL = {}          # key -> (类别, 中文)
for _cls, _d in DICTS:
    for _k, _v in _d.items():
        _n = _nm(_k)
        if not _n:
            continue
        # 注意：值为空的词条（ZZ / 冗余词组）也必須进 POOL ——
        # 它的作用是「占位以便 masked」，否则会被误报成未收录词。
        # 拼接时靠 assemble 里的 `if not cn: continue` 丢弃。
        if _n not in POOL:
            POOL[_n] = (_cls, _v)
        for _p in _plurals(_n):          # 单→复，覆盖 broilers/fryers/sugars
            if _p not in POOL:
                POOL[_p] = (_cls, _v)

_keys = sorted(POOL, key=lambda k: (-len(k.split()), -len(k)))
RX_WORDS = re.compile(r'(?<![a-z0-9])(?:' + "|".join(re.escape(k) for k in _keys)
                      + r')(?![a-z0-9])')


def _scan_id(seg, offset=0):
    """印尼语专用扫描器：走 glossary_id 的码表，非英语，不共用 POOL"""
    import glossary_id as GI
    out = []
    for m in GI.RX.finditer(seg):
        g = re.sub(r'\s+', ' ', m.group(0))
        cls, cn = GI.POOL_ID[g]
        if cls.startswith("_"):
            cls = cls[3:]
        out.append((cls, g, cn, offset + m.start(), offset + m.end()))
    return out


def scan(seg, offset=0, lang="en"):
    if lang == "id":
        return _scan_id(seg, offset)
    return [(POOL[re.sub(r'\s+', ' ', m.group(0))][0],
             re.sub(r'\s+', ' ', m.group(0)),
             POOL[re.sub(r'\s+', ' ', m.group(0))][1],
             offset + m.start(), offset + m.end())
            for m in RX_WORDS.finditer(seg)]


def unknown_tokens(text, hits):
    """未被词典覆盖、且不在 STOP 里的实词"""
    mask = bytearray(len(text))
    for _c, _k, _v, s, e in hits:
        for i in range(s, min(e, len(mask))):
            mask[i] = 1
    out = []
    for m in re.finditer(r'[a-z0-9]+', text):
        if any(mask[m.start():m.end()]) or len(m.group(0)) < 3 or m.group(0).isdigit():
            continue
        if m.group(0) in STOP:
            continue
        out.append(m.group(0))
    return out


# ────────────────────────── 组装 ──────────────────────────
def _dedup_cn(main, suf):
    """主料与部位拼合时去重，避免「鸡肉胸肉」「鳕鱼鱼」「牛肉肉」。

    规则：
      主料以「肉/鱼/油/奶/蛋/豆/饼/糕/汁/酱/粉」结尾而部位以同字开头 → 合并且
      主料以「肉」结尾（多数为「X肉」）而部位以部位字开头 → 去主料的「肉」
    """
    if not (main and suf):
        return main + suf
    if main.endswith("肉") and suf[0] in "胸腿翅头脚尾皮腰肝心脑眼肚肠舌骨":
        return main[:-1] + suf
    # 同字相接去一
    if main[-1] == suf[0]:
        return main + suf[1:]
    return main + suf


# 中文里语义重复的后缀对（保留后者）
DUP_PAIR = re.compile(r'(.)\1')


def tidy_cn(cn):
    """中文名收尾清理：叠字去重、悬空部位字、空白"""
    if not cn:
        return cn
    cn = re.sub(r'\s+', '', cn)
    cn = re.sub(r'[（(]\s*[）)]', '', cn)          # 空括号
    # 连续相同汉字（仅这两类安全：名词叠字在食物名里几乎都为误拼）
    for _ in range(3):
        n2 = DUP_PAIR.sub(r'\1', cn)
        if n2 == cn:
            break
        cn = n2
    cn = re.sub(r'^[,、;，]+|[,、;，]+$', '', cn)
    return cn


# 类属主料：若 head 只是「汤/酱/汁」这类类别词，而后面跟着具体主料，
# 应让具体主料做核心、类别词退到名称末尾（Soup,clam chowder → 蛤蜊巧达浓汤）
GENERIC_MAIN = {"汤", "汤汁", "沙拉", "酱", "酱汁", "调味酱", "水", "汁", "粉",
                "油", "饮料", "饮品", "布丁", "糖果", "冰淇淋", "饼", "点心",
                "饼干", "面包", "蛋糕", "派", "零食", "调味料", "甜点", "肉"}


def assemble(head_hits, mod_hits=(), lang=None):
    """按中文语序组装。head 段的最后一个主料为核心，mod 段的主料作前缀配料"""
    global IS_ID
    IS_ID = (lang == "id")
    front = mod_hits_cn = []
    front_cls = set()
    buckets = collections.defaultdict(list)
    mains, pb, sf, mod_mf = [], [], [], []

    for cls, key, cn, _s, _e in head_hits:
        if not cn:
            continue                       # ZZ 类：已覆盖但不输出
        if cls == "MF":
            mains.append(cn)
        elif cls == "PB":
            pb.append(cn)
        elif cls == "SF":
            sf.append(cn)
        elif cls == "QT" and key in QT_PRE:
            buckets["QT"].append((0, key, cn))
        else:
            buckets[cls].append((G.WORD_RANK.get(key, 0), key, cn))

    for cls, key, cn, _s, _e in mod_hits:
        if not cn:
            continue
        if cls == "PB":
            pb.append(cn)
        elif cls == "SF":
            sf.append(cn)
        elif cls == "QT" and key in QT_PRE:
            buckets["QT"].append((0, key, cn))
        elif cls == "MF":
            mod_mf.append(cn)              # 复合前缀，不抢占核心
        else:
            buckets[cls].append((0, key, cn))

    # 前置修饰链：ST → CO → PR → NU → CL → CN → PH
    qt_post = []
    for cls in sorted((c for c in buckets if c in CLS_ORDER),
                      key=lambda c: CLS_ORDER[c]):
        items = buckets[cls]
        if cls in ("ST", "CO"):
            best = max(items, key=lambda x: (x[0], -len(x[1])))
            front.append(best[2])
            front_cls.add(cls)
            continue
        if cls == "QT":
            for _r, key, cn in items:
                (qt_post if key not in QT_PRE else front).append(cn)
            continue
        seen = []
        for _r, key, cn in items:
            if key in PH_SUFFIX:           # 形态成品交给后缀，不重复前置
                continue
            if cn not in seen:
                seen.append(cn)
        front.extend(seen)
        if seen:
            front_cls.add(cls)

    ph = [cn for _r, k, cn in buckets.get("PH", [])
          if k in PH_SUFFIX and G.PH.get(k)]

    # 主料：head 段可能有多个 MF（如印尼语 "susu kental manis" 里的 kental），
    # 未指定 lang 时按「取最后一个」处理 —— 但 PB/QT/SF 必须保留全部。
    main = mains[-1] if mains else ""
    if len(mains) > 1:
        # 前几个 MF 交给 mod 侧统一处理（英文里作复合前缀，印尼语里作补语）
        mod_extra = mains[:-1]
    else:
        mod_extra = []
    mains = mains[-1:]

    # 类属词让位给具体主料；只有后缀没有主料时，后缀升为核心
    if main in GENERIC_MAIN and (mod_mf or sf):
        pool = mod_mf or sf
        sf.insert(0, main)
        main = pool.pop() if pool is mod_mf else main
        mod_mf = pool
    elif not main and sf:
        main = sf.pop(0)

    if IS_ID:
        # ── 印尼语：状态/烹饪前置 → 主料 → 部位紧贴 → 其余修饰收尾 ──
        cn = "".join(front) + main
        pbs, qts = [], []
        for _r, k, c in buckets.get("PB", []):
            k2 = k[3:] if k.startswith("_id_") else k
            (pbs if k2 in PB_HEAD else qts).append(c)
        cn += "".join(pbs) + "".join(pb)
        for cls in ("ST", "CO", "PH", "NU", "PR", "QT"):
            if cls in front_cls:
                continue
            for _r, _k, c in buckets.get(cls, []):
                if c and c not in cn:
                    cn += c
        cn += "".join(mod_hits_cn) + "".join(sf)

    # ── 英语：修饰前置、主料居中、部位紧贴主料 ──
    cn = "".join(front)
    cn += "".join(mod_extra) + "".join(mod_mf) + main
    cn = tidy_cn(_dedup_cn(cn, "".join(pb)))
    if ph:
        cn += "（" + "、".join(ph) + "）"
    cn += "".join(sf)
    if qt_post:
        cn += "（" + "".join(qt_post) + "）"
    return tidy_cn(cn)


# ────────────────────────── 解析 ──────────────────────────
PAREN_KEEP = 28     # 括号内容短于此长度视为真修饰（品牌/产地/学名多为长串）


ING_SPLIT = re.compile(r'\b(with|without|plus|topped with|stuffed with|contains)\b',
                       re.I)


def _subparts(p):
    """段内再按 with/without 切成 [(文本, role)]，role=None 表示继承默认"""
    toks = ING_SPLIT.split(p)
    out = []
    if toks[0].strip():
        out.append((toks[0].strip(), None))
    for i in range(1, len(toks), 2):
        conn = toks[i].lower()
        rest = toks[i + 1].strip() if i + 1 < len(toks) else ""
        if not rest:
            continue
        neg = conn.startswith("without")
        out.append((rest, "ing-" if neg else "ing+"))
    return out or [(p, None)]


def split_parts(raw):
    """清理并按逗号分段 → [(段文本, role)]"""
    s = re.sub(r'[*†‡—–]', ' ', str(raw))

    def repl(m):
        inner = m.group(1).strip()
        return ", %s," % inner if 0 < len(inner) <= PAREN_KEEP else " "
    s = re.sub(r'\(([^)]*)\)', repl, s)
    s = re.sub(r'\[[^\]]*\]', ' ', s)

    parts = []
    for p in re.split(r'[,;]', s):
        p = p.strip()
        if not p:
            continue
        for txt, subrole in _subparts(p):
            if subrole:
                parts.append((txt, subrole))
            else:
                parts.append((txt, "head" if not parts else "mod"))
    # 美式 "...added" 结尾 = 配料
    for i, (txt, role) in enumerate(parts):
        if role == "mod" and re.search(r'\badded\b', txt, re.I):
            parts[i] = (txt, "ing+")
    return parts or [(s, "head")]


def translate_en(name):
    """英文食物名 → (中文, 状态, 方法, 未识别词)"""
    if not name or not str(name).strip():
        return None, "empty", "-", []

    parts = split_parts(name)
    head_text = parts[0][0]
    body_parts = parts[1:]

    # 统一坐标：手动拼接归一化串，记录每段偏移
    segs = [(head_text, "head")] + body_parts
    norm_whole, spans = [], []
    pos = 0
    for txt, role in segs:
        ntxt = _nm(txt)
        if not ntxt:
            spans.append((role, pos, pos))
            continue
        norm_whole.append(ntxt)
        spans.append((role, pos, pos + len(ntxt)))
        pos += len(ntxt) + 1
    norm_whole = " ".join(norm_whole)

    # 关键：在拼接后的整串上「一次性」扫描，而不是逐段扫描。
    # 只有这样才能命中跨逗号的倒装短语（egg whole / milk dry / prepared from recipe）。
    hits_sorted = scan(norm_whole, 0)

    role_map = collections.defaultdict(list)
    for (role, s0, s1) in spans:
        grp = [h for h in hits_sorted if s0 <= h[3] < s1]
        role_map[role].extend(grp)

    core = assemble(role_map["head"], role_map["mod"])
    core = re.sub(r'\s+', '', core)

    tails = []
    for role in ("ing+", "ing-"):
        sub = re.sub(r'\s+', '', assemble(role_map[role]))
        if sub:
            tails.append(("配" if role == "ing+" else "无") + sub)

    cn = core + "".join(tails)
    unk = unknown_tokens(norm_whole, hits_sorted)

    if not cn:
        return None, "untranslated", "-", unk
    return cn, ("partial" if unk else "ok"), "dict", unk


# 日本食品标准成分表：分类标记 ＜…＞ 要去掉；（…類）是子分类注解也要去掉；
# 保留食物本体名。名称以全角空格分段，段间用「・」连接更易读。
JP_KANA = {
    "生": "生", "ゆで": "水煮", "焼き": "烤", "蒸し": "蒸", "炒め": "炒",
    "揚げ": "油炸", "乾燥": "干制", "缶詰": "罐头", "冷凍": "冷冻",
    "塩蔵": "盐渍", "素干し": "淡干", "煮干し": "煮干", "燻製": "熏制",
    "発酵": "发酵", "漬け": "腌渍", "味付け": "调味", "油漬": "油浸",
    "水煮": "水煮", "液汁": "汤汁", "風味": "风味", "加糖": "加糖",
    "無糖": "无糖", "低脂肪": "低脂", "高脂肪": "高脂",
}


def clean_jp(name):
    """日本库：去 ＜分类＞ 前缀与 （XX類）注解，折叠全角空格"""
    s = str(name)
    s = re.sub(r'＜[^＞]*＞', '', s)
    s = re.sub(r'（[^）]*類[^）]*）', '', s)
    s = re.sub(r'[［\[][^］\]]*[］\]]', '', s)
    s = re.sub(r'[\u3000\s]+', ' ', s).strip()
    s = re.sub(r'\s+', '', s)
    return s.strip('　・') or str(name).strip()


# ── 日本库假名→汉字（常见食物名 + 形体词），让名称可读 ──────────
JP_KANJI = {
    # 谷物薯类
    "こむぎ": "小麦", "こめ": "大米", "うるちまい": "粳米", "もち米": "糯米",
    "もち": "糯米", "とうもろこし": "玉米", "じゃがいも": "马铃薯",
    "さつまいも": "甘薯", "ばれいしょ": "马铃薯", "やまいも": "山药",
    "ながいも": "长薯", "じねんじょ": "野山药", "さといも": "芋头",
    "こんにゃく": "魔芋", "でんぷん": "淀粉", "こむぎこ": "小麦粉",
    "そば": "荞麦", "そば粉": "荞麦粉", "うどん": "乌冬面", "そうめん": "素面",
    "ひやむぎ": "冷麦", "きりたんぽ": "烤米棒", "パン": "面包",
    "パン粉": "面包屑", "ベーグル": "贝果", "クロワッサン": "牛角包",
    "スパゲッティ": "意大利面", "マカロニ": "通心粉", "めん": "面",
    # 蔬菜
    "たまねぎ": "洋葱", "ねぎ": "葱", "こねぎ": "小葱", "にんにく": "大蒜",
    "しょうが": "姜", "にんじん": "胡萝卜", "だいこん": "白萝卜",
    "かぶ": "芜菁", "ごぼう": "牛蒡", "れんこん": "藕", "はす": "藕",
    "キャベツ": "甘蓝", "はくさい": "大白菜", "こまつな": "小松菜",
    "ほうれんそう": "菠菜", "レタス": "生菜", "サニーレタス": "散叶生菜",
    "きゅうり": "黄瓜", "トマト": "番茄", "なす": "茄子", "ピーマン": "青椒",
    "パプリカ": "甜椒", "かぼちゃ": "南瓜", "にがうり": "苦瓜",
    "ゴーヤー": "苦瓜", "ズッキーニ": "西葫芦", "おくら": "秋葵",
    "カリフラワー": "花椰菜", "ブロッコリー": "西兰花", "アスパラガス": "芦笋",
    "セロリ": "芹菜", "パセリ": "欧芹", "みつば": "鸭儿芹", "ゆず": "柚子",
    "すだち": "酢橘", "かぼす": "臭橙", "しいたけ": "香菇",
    "えのきたけ": "金针菇", "しめじ": "蟹味菇", "まいたけ": "舞茸",
    "エリンギ": "杏鲍菇", "なめこ": "滑菇", "マッシュルーム": "蘑菇",
    "きくらげ": "木耳", "もやし": "豆芽", "だいずもやし": "黄豆芽",
    "アルファルファ": "苜蓿芽", "たけのこ": "竹笋", "ふき": "蜂斗菜",
    "ぜんまい": "紫萁", "わらび": "蕨菜", "うど": "独活", "よもぎ": "艾草",
    "枝豆": "毛豆", "えだまめ": "毛豆",
    # 豆类豆制品
    "だいず": "大豆", "あずき": "红豆", "いんげんまめ": "四季豆",
    "うずら豆": "斑豆", "ささげ": "豇豆", "えんどう": "豌豆",
    "グリーンピース": "青豌豆", "そらまめ": "蚕豆", "ひよこまめ": "鹰嘴豆",
    "りょうりまめ": "菜豆", "とうふ": "豆腐", "おから": "豆腐渣",
    "油揚げ": "油豆腐", "あぶらあげ": "油炸豆腐", "がんもどき": "油炸豆腐饼",
    "納豆": "纳豆", "なっとう": "纳豆", "きなこ": "黄豆粉",
    "ゆば": "腐竹", "湯葉": "腐竹", "豆乳": "豆浆", "とうにゅう": "豆浆",
    "おからのいため": "炒豆腐渣", "凍り豆腐": "冻豆腐",
    # 果实
    "りんご": "苹果", "みかん": "橘子", "オレンジ": "橙", "グレープフルーツ": "西柚",
    "レモン": "柠檬", "ライム": "青柠", "バナナ": "香蕉", "パイナップル": "菠萝",
    "いちご": "草莓", "ぶどう": "葡萄", "マスカット": "麝香葡萄",
    "もも": "桃", "なし": "梨", "日本なし": "日本梨", "かき": "柿子",
    "くり": "栗子", "すいか": "西瓜", "メロン": "甜瓜", "キウイフルーツ": "猕猴桃",
    "さくらんぼ": "樱桃", "うめ": "梅", "あんず": "杏", "すもも": "李",
    "いちじく": "无花果", "ざくろ": "石榴", "びわ": "枇杷",
    "アボカド": "牛油果", "マンゴー": "芒果", "パパイヤ": "木瓜",
    "ブルーベリー": "蓝莓", "ラズベリー": "树莓", "クランベリー": "蔓越莓",
    "プルーン": "西梅干", "レーズン": "葡萄干", "アーモンド": "杏仁",
    "くるみ": "核桃", "カシューナッツ": "腰果", "ピーナッツ": "花生",
    "ぎんなん": "白果", "ごま": "芝麻", "ひまわりのたね": "葵花籽",
    "すいかのたね": "西瓜籽", "かぼちゃのたね": "南瓜籽",
    # 肉类
    "ぎゅうにく": "牛肉", "うし": "牛", "ぶた": "猪", "ぶたにく": "猪肉",
    "とりにく": "鸡肉", "にわとり": "鸡", "かも": "鸭", "あひる": "鸭",
    "ひつじ": "羊", "めんよう": "绵羊", "やぎ": "山羊", "うま": "马",
    "ヒレ": "里脊", "ロース": "里脊肉", "バラ": "五花", "もも": "腿",
    "かた": "肩", "むね": "胸", "ささみ": "鸡柳", "てばさき": "翅尖",
    "手羽先": "翅尖", "手羽元": "翅根", "すね": "小腿", "かたロース": "肩里脊",
    "ひき肉": "绞肉", "レバー": "肝", "ハツ": "心", "タン": "舌",
    "はつ": "心", "レバ": "肝", "ソーセージ": "香肠", "ベーコン": "培根",
    "ハム": "火腿", "ハンバーグ": "汉堡肉饼",
    # 水产
    "さかな": "鱼", "さけ": "三文鱼", "ます": "鳟鱼", "まぐろ": "金枪鱼",
    "かつお": "鲣鱼", "ぶり": "鰤鱼", "たい": "鲷鱼", "ひらめ": "比目鱼",
    "さば": "鲭鱼", "あじ": "竹䇲鱼", "さんま": "秋刀鱼", "いわし": "沙丁鱼",
    "うるめいわし": "圆腹鲱", "こい": "鲤鱼", "ふな": "鲫鱼", "うなぎ": "鳗鱼",
    "あなご": "星鳗", "どじょう": "泥鳅", "たら": "鳕鱼", "すけとうだら": "狭鳕",
    "ほっけ": "花鱼", "かれい": "鲽鱼", "にしん": "鲱鱼", "たこ": "章鱼",
    "いか": "鱿鱼", "するめいか": "太平洋鱿鱼", "あかいか": "赤鱿",
    "えび": "虾", "くるまえび": "车虾", "ブラックタイガー": "黑虎虾",
    "あまえび": "甜虾", "かに": "蟹", "ずわいがに": "雪蟹",
    "たらばがに": "帝王蟹", "かき": "牡蛎", "あさり": "蛤蜊",
    "しじみ": "蚬", "はまぐり": "文蛤", "ほたてがい": "扇贝",
    "さざえ": "蝾螺", "あわび": "鲍鱼", "うに": "海胆", "いくら": "鲑鱼籽",
    "たらこ": "鳕鱼籽", "めんたいこ": "明太子", "かずのこ": "鲱鱼籽",
    "ちくわ": "竹轮", "かまぼこ": "鱼糕", "はんぺん": "鱼饼",
    "さつまあげ": "萨摩炸鱼饼", "のり": "海苔", "わかめ": "裙带菜",
    "ひじき": "羊栖菜", "こんぶ": "海带", "もずく": "水云",
    "あおさ": "石莼", "てんぐさ": "石花菜",
    # 蛋奶
    "たまご": "鸡蛋", "鶏卵": "鸡蛋", "うずら": "鹌鹑",
    "卵黄": "蛋黄", "卵白": "蛋清", "ぎゅうにゅう": "牛奶",
    "牛乳": "牛奶", "にゅうせいひん": "乳制品", "ちち": "奶",
    "ヨーグルト": "酸奶", "チーズ": "奶酪", "バター": "黄油",
    "マーガリン": "人造黄油", "クリーム": "奶油", "アイスクリーム": "冰淇淋",
    "れんにゅう": "炼乳", "こなミルク": "奶粉", "生クリーム": "稀奶油",
    # 油脂糖调味
    "あぶら": "油", "サラダ油": "沙拉油", "オリーブオイル": "橄榄油",
    "ごま油": "芝麻油", "なたね油": "菜籽油", "とうもろこし油": "玉米油",
    "ラード": "猪油", "ショートニング": "起酥油",
    "さとう": "糖", "砂糖": "白糖", "はちみつ": "蜂蜜",
    "みずあめ": "水饴", "シロップ": "糖浆", "ジャム": "果酱",
    "チョコレート": "巧克力", "ココア": "可可粉", "あん": "豆沙",
    "つぶあん": "颗粒豆沙", "こしあん": "细豆沙", "しろあん": "白豆沙",
    "しょうゆ": "酱油", "こいくちしょうゆ": "浓口酱油",
    "うすくちしょうゆ": "淡口酱油", "たまりしょうゆ": "溜酱油",
    "みそ": "味噌", "みそしる": "味噌汤", "す": "醋", "酢": "醋",
    "みりん": "味醂", "さけ ": "清酒", "ソース": "酱汁",
    "マヨネーズ": "蛋黄酱", "ケチャップ": "番茄酱",
    "しお": "盐", "塩": "盐", "こしょう": "胡椒", "カレー": "咖喱",
    "からし": "芥末", "わさび": "山葵", "しょうゆ ": "酱油",
    "だし": "高汤", "コンソメ": "清汤料", "ポン酢": "柚子醋",
    "たれ": "蘸酱", "ドレッシング": "沙拉汁", "ふりかけ": "拌饭料",
    # 饮品
    "ちゃ": "茶", "緑茶": "绿茶", "せんちゃ": "煎茶", "ほうじ茶": "焙茶",
    "ウーロン茶": "乌龙茶", "こうちゃ": "红茶", "コーヒー": "咖啡",
    "インスタントコーヒー": "速溶咖啡", "コーラ": "可乐",
    "サイダー": "汽水", "ジュース": "果汁", "ビール": "啤酒",
    "ぶどう酒": "葡萄酒", "日本酒": "清酒", "焼酎": "烧酒",
    "ウイスキー": "威士忌", "ブランデー": "白兰地", "ワイン": "葡萄酒",
    "みず": "水", "水": "水", "ミネラルウォーター": "矿泉水",
    # 加工料理
    "パン類": "面包类", "めん類": "面类", "菓子": "糕点",
    "和生菓子": "日式生点心", "和干菓子": "日式干点心",
    "洋生菓子": "西式生点心", "洋干菓子": "西式干点心",
    "せんべい": "米饼", "あられ": "霰饼", "おこし": "米花糖",
    "だんご": "团子", "くし団子": "串团子", "まんじゅう": "馒头",
    "どらやき": "铜锣烧", "たいやき": "鲷鱼烧", "カステラ": "长崎蛋糕",
    "シュークリーム": "泡芙", "プリン": "布丁", "ゼリー": "果冻",
    "ケーキ": "蛋糕", "ビスケット": "饼干", "クッキー": "曲奇",
    "クラッカー": "薄脆饼", "ポテトチップス": "薯片",
    "洋風料理": "西式料理", "和風料理": "日式料理", "中華風料理": "中式料理",
    "カレー類": "咖喱类", "シチュー類": "炖菜类", "スープ類": "汤类",
    "すし": "寿司", "寿司": "寿司", "てんぷら": "天妇罗",
    "天ぷら": "天妇罗", "フライ": "油炸", "とんかつ": "炸猪排",
    "からあげ": "唐扬炸鸡", "やきとり": "烤鸡肉串", "焼き鳥": "烤鸡肉串",
    "ぎょうざ": "饺子", "しゅうまい": "烧卖", "ラーメン": "拉面",
    "チャーハン": "炒饭", "オムレツ": "煎蛋饼", "サラダ": "沙拉",
    "スープ": "汤", "みそ汁": "味噌汤", "漬物": "腌菜",
    "つけもの": "腌菜", "たくあん": "腌萝卜", "キムチ": "泡菜",
    "のりまき": "海苔卷", "いなりずし": "稻荷寿司",
    # 形体
    "果実": "果实", "葉": "叶", "葉柄": "叶柄", "茎": "茎", "根": "根",
    "りん茎": "鳞茎", "花": "花", "花蕾": "花蕾", "つぼみ": "花蕾",
    "種子": "种子", "たね": "籽", "皮": "皮", "皮つき": "带皮",
    "皮なし": "去皮", "全形": "整只", "きざみ": "切碎", "せん切り": "切丝",
    "たんざく切り": "切条", "角切り": "切块", "うす切り": "切片",
    "おろし": "磨泥", "すりおろし": "磨泥", "乾": "干制", "乾燥": "干制",
    "冷凍": "冷冻", "缶詰": "罐头", "びん詰": "瓶装", "加工品": "加工品",
    "素干し": "淡晒干", "塩蔵": "盐渍", "生": "生", "ゆで": "水煮",
    "蒸し": "蒸", "焼き": "烤", "炒め": "炒", "揚げ": "油炸",
    "フライ ": "油炸", "油いため": "油炒", "いため": "炒",
    "あんかけ": "勾芡浇汁", "含め煮": "炖煮", "煮": "煮",
}


# 第二批日文词（按残留频次补齐）
JP_KANJI.update({
    "つき": "月龄", "その": "其他", "リブ": "肋排", "でん": "淀粉", "じょう": "",
    "せいよう": "西洋", "そと": "外", "タイプ": "型", "むもの": "皮", "スタイル": "式",
    "カップ": "杯装", "つぶし": "颗粒", "たんぱく": "蛋白", "いり": "炒",
    "くろ": "黑", "ばら": "五花", "ざや": "荚", "うんしゅう": "温州",
    "しろ": "白", "サーロイン": "西冷", "ランプ": "臀肉", "ぬか": "米糠",
    "はるさめ": "粉丝", "きな": "黄豆", "らっかせい": "花生",
    "ストレート": "直形", "パインアップル": "菠萝", "あゆ": "香鱼",
    "おおむぎ": "大麦", "レンジ": "微波炉", "グリンピース": "青豌豆",
    "スイートコーン": "甜玉米", "プレミックス": "预拌粉", "ソテー": "嫩煎",
    "あめ": "糖", "ばえ": "蝇", "さくら": "樱", "したもの": "制品",
    "いも": "薯", "こし": "细腻", "ぐり": "栗", "とうがらし": "辣椒",
    "にら": "韭菜", "バレンシア": "瓦伦西亚", "ぶめじ": "刺身", "つくだ": "佃煮",
    "しら": "白", "まだい": "真鲷", "ホワイトナー": "植脂奶油",
    "りつぶし": "磨碎", "おおば": "大叶", "めばる": "石斑", "かんぱち": "𫚕鱼",
    "ひら": "平", "きす": "鱚鱼", "こはだ": "小鳍", "こち": "鲬鱼",
    "あんこう": "鮟鱇", "こういか": "剑尖鱿", "やま": "山", "うに ": "海胆",
    "しそ": "紫苏", "ゆりね": "百合", "らっきょう": "薤头",
    "はすいも": "莲芋", "ずいき": "芋茎", "かんぴょう": "干瓢",
    "くわい": "慈姑", "ゆり": "百合", "あさつき": "细香葱",
    "かき ": "牡蛎", "むかご": "零余子", "まこも": "菰", "はとむぎ": "薏苡",
    "あわ": "粟", "ひえ": "稗", "きび": "黍", "はと": "鸽",
    "しいら": "鲯鳅", "かんぱち": "𫚕", "はまち": "幼鰤",
    "いさき": "伊佐木", "のどぐろ": "赤鯥", "きんめだい": "金目鲷",
    "ちだい": "黄鲷", "れんこだい": "连子鲷", "いしだい": "石鲷",
    "くろだい": "黑鲷", "へダイ": "鲷", "へだい": "鲷",
    "ひらめ ": "比目鱼", "ます ": "鳟", "たかべ": "𬶭",
    "とびうお": "飞鱼", "さわら": "马鲛", "ししゃも": "柳叶鱼",
    "にしん ": "鲱", "はたはた": "雷鱼", "あんこう ": "鮟鱇",
    "やなぎ": "柳", "しま": "条纹", "かわ": "皮", "かた ": "肩",
    "すじ": "筋", "くず": "葛", "しん": "芯", "かま ": "鱼颈肉",
    "つぼ": "壶", "わせ": "早生", "あき": "秋", "なつ": "夏",
    "しろうり": "越瓜", "うり": "瓜", "なまり": "半干", "なまり節": "半干鲣节",
    "かつお": "鲣鱼", "傘": "伞盖", "かさ": "伞盖", "ほし": "干",
    "かんぴょう ": "干瓢", "ゆでこぼし": "焯水", "みじん切り": "切末",
    "はる": "春", "ふゆ": "冬", "おんしゅ": "温", "れいとう": "冷冻",
})
# 空值保护：じょう 映射为空说明是噪声，直接剔除
JP_KANJI.pop("じょう", None)

_JP_RX = re.compile("|".join(re.escape(k) for k in
                            sorted(JP_KANJI, key=len, reverse=True)))


def jp_localize(name):
    """把日文名里的假名替换成汉字，提升可读性（未登录假名原样保留）"""
    s = clean_jp(name)
    return _JP_RX.sub(lambda m: JP_KANJI[m.group(0)], s)


def translate_row(src, nloc, nen):
    """返回 (中文, 状态, 方法, 未识别词)"""
    for cand in (nloc, nen):
        if cand and re.search(r'[一-鿿]', str(cand)):
            return (jp_localize(cand) if src == "JP" else str(cand).strip(),
                    "native", "native", [])
    if src == "JP" and re.search(r'[ぁ-んァ-ヶ]', str(nloc or "")):
        loc = jp_localize(nloc)
        if re.search(r'[一-鿿]', loc):
            return loc, "native", "native", []
    if src == "ID" and GI is not None:
        return GI.translate(str(nloc or nen or ""))
    for cand in (nloc, nen):
        if cand:
            cn, st, me, unk = translate_en(cand)
            if cn:
                return cn, st, me, unk
    return None, "untranslated", "-", []


def main(limit=0, dry=False):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cols = {r[1] for r in cur.execute("PRAGMA table_info(norm_food)")}
    for col, ddl in [("name_cn", "TEXT"), ("translate_status", "TEXT"),
                     ("translate_method", "TEXT"), ("translate_unknown", "TEXT")]:
        if col not in cols:
            cur.execute(f"ALTER TABLE norm_food ADD COLUMN {col} {ddl}")
            print(f"  + 新增列 norm_food.{col}")
    con.commit()

    sql = "select norm_food_id, source, name_local, name_en from norm_food"
    if limit:
        sql += f" limit {limit}"
    rows = cur.execute(sql).fetchall()
    print(f"待处理 {len(rows):,} 条\n")

    out, unkstat = [], collections.Counter()
    for nid, src, nloc, nen in rows:
        cn, st, me, unk = translate_row(src, nloc, nen)
        out.append((cn, st, me, " ".join(sorted(set(unk)))[:200] or None, nid))
        for u in unk:
            unkstat[u] += 1

    if dry:
        return rows, out, unkstat

    con.isolation_level = None
    cur.execute("PRAGMA journal_mode=MEMORY")
    cur.execute("PRAGMA synchronous=OFF")
    cur.execute("BEGIN")
    cur.executemany("UPDATE norm_food SET name_cn=?, translate_status=?, "
                    "translate_method=?, translate_unknown=? WHERE norm_food_id=?",
                    out)
    cur.execute("COMMIT")

    n = len(rows)
    print("=== 翻译状态 ===")
    for st, c in cur.execute("select translate_status, count(*) from norm_food "
                             "group by 1 order by 2 desc"):
        print(f"  {str(st):<14} {c:>7,}  {c / n * 100:>5.1f}%")
    print("\n=== 各来源覆盖率 ===")
    print(f"{'来源':<7}{'总数':>8}{'有中文名':>10}{'ok':>8}{'partial':>9}{'覆盖率':>8}")
    for s, t, c, ok, pa in cur.execute(
            "select source, count(*), sum(name_cn is not null),"
            " sum(translate_status='ok'), sum(translate_status='partial')"
            " from norm_food group by source order by 2 desc"):
        print(f"{s:<7}{t:>8,}{c or 0:>10,}{ok or 0:>8,}{pa or 0:>9,}"
              f"{(c or 0) / t * 100:>7.1f}%")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_nf_cn ON norm_food(name_cn)")
    con.close()
    return rows, out, unkstat



if __name__ == "__main__":
    _lm = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 0
    _r, _o, unk = main(limit=_lm, dry=("--dry" in sys.argv))
    if unk:
        print(f"\n=== 未收录词 TOP60（{sum(unk.values()):,} 次 / {len(unk):,} 个唯一）===")
        print(", ".join(f"{k}({v})" for k, v in unk.most_common(60)))
