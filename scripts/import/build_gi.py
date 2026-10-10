#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导入《中国食物成分表》第6版 附录 —— 食物血糖生成指数(GI)数据。
来源: Sanotsu/china-food-composition-data -> json_gi_of_foods/glycemic_index_of_foods.json
新增表: china_food_gi  (259 条, 11 个大类)

同时尝试把每条 GI 记录与 china_food_composition 中的食物做名称匹配,
匹配结果写入 matched_food_code / matched_food_name / match_type 三列,
方便直接 JOIN 查出「某食物的 GI 值」。
"""
import json
import re
import sqlite3
import os

DB = "/workspace/fdc/nutrition.db"
GI_JSON = "/workspace/fdc/china/glycemic_index_of_foods.json"


def normalize(name: str) -> str:
    """归一化食物名: 去掉星号/空格/全半角括号差异, 只留中文与字母数字。"""
    s = name.strip()
    s = s.lstrip("*").strip()
    s = s.replace("，", ",").replace("（", "(").replace("）", ")")
    s = s.replace("／", "/").replace("/", "/")
    s = re.sub(r"[\s\u00a0]+", "", s)
    return s


def base_name(name: str) -> str:
    """取主名: 括号前的部分, 例如 '牛奶（加糖和巧克力）' -> '牛奶'。"""
    s = normalize(name)
    s = re.split(r"[（(]", s)[0]
    return s


def load_gi():
    with open(GI_JSON, encoding="utf-8") as f:
        return json.load(f)


def main():
    groups = load_gi()

    # ---------- 准备匹配索引 ----------
    con = sqlite3.connect(DB)
    cur = con.cursor()

    foods = list(cur.execute("SELECT foodCode, foodName, category FROM china_food_composition"))
    by_full = {}          # 归一化全名 -> [(code, name)]
    by_base = {}          # 归一化主名 -> [(code, name)]
    for code, name, cat in foods:
        f = normalize(name)
        b = base_name(name)
        by_full.setdefault(f, []).append((code, name))
        by_base.setdefault(b, []).append((code, name))

    def match(name):
        """返回 (code, name, match_type) 或 (None, None, None)。"""
        f = normalize(name)
        # 1) 完全同名
        if f in by_full:
            c, n = by_full[f][0]
            return c, n, "exact"
        # 2) 主名相同 (GI 侧括号多为做法说明, 主食侧括号多为品种说明)
        b = base_name(name)
        if b and b in by_base:
            for c, n in by_base[b]:
                # 排除干制/脱水/浓缩等状态差异过大的候选 (GI 值不具可比性)
                if any(k in n for k in ("脱水", "干制", "浓缩", "罐头")):
                    continue
                return c, n, "base"
        # 3) 前缀匹配: 仅允许「食物名 == GI名 + 后缀限定词」这种方向
        #    例如 GI '黑米' 可匹配食物 '黑米饭'/'黑米粥', 但绝不允许
        #    GI '菠萝' 匹配 '菠萝蜜' (那是另一物种), 也不允许 GI '甜菜' -> '甜菜叶' (食用部位不同)。
        #    规则: food 名必须以 GI 名开头, 且剩余部分只能是「饭/粥/面/粉/汤/条/饼/干/片/丝/酱/汁/茶」等加工后缀,
        #          不能是另一个实义名词 (蜜/叶/花/油...)。
        SUFFIX_OK = ("饭", "粥", "面", "粉", "汤", "条", "饼", "干", "片",
                     "丝", "酱", "汁", "茶", "糕", "卷", "包", "饺", "丸")
        if len(f) >= 2:
            for full, lst in by_full.items():
                if full.startswith(f) and len(full) > len(f):
                    rest = full[len(f):]
                    if rest and all(ch in "()（）," for ch in rest):
                        c, n = lst[0]
                        return c, n, "prefix"
                    # 余下部分须整体命中某个合法后缀
                    if rest in SUFFIX_OK or (len(rest) >= 1 and rest[0] in SUFFIX_OK
                                             and all(ch not in "蜜叶花籽油根茎皮仁" for ch in rest)):
                        c, n = lst[0]
                        return c, n, "prefix"
        return None, None, None

    # ---------- 建表 ----------
    cur.execute("DROP TABLE IF EXISTS china_food_gi")
    cur.execute("""
        CREATE TABLE china_food_gi (
            seq            INTEGER PRIMARY KEY,   -- 书内序号 1..259
            food_group     TEXT,                   -- 11 个大类
            food_name      TEXT,                   -- 原书食物名 (含 * 标记)
            gi_value       REAL,                   -- 血糖生成指数
            matched_food_code TEXT,                -- 匹配到的 china_food_composition.foodCode
            matched_food_name TEXT,                -- 匹配到的食物名
            match_type     TEXT,                   -- exact / base / prefix / NULL
            source         TEXT
        )
    """)

    src = "中国食物成分表 第6版 附录 (GI)"
    n_exact = n_base = n_prefix = n_none = 0
    rows = []
    for g in groups:
        for it in g["list"]:
            code, mname, mtype = match(it["foodName"])
            if mtype == "exact":
                n_exact += 1
            elif mtype == "base":
                n_base += 1
            elif mtype == "prefix":
                n_prefix += 1
            else:
                n_none += 1
            rows.append((it["index"], g["foodGroup"], it["foodName"], it["GI"],
                         code, mname, mtype, src))

    cur.executemany(
        "INSERT INTO china_food_gi VALUES (?,?,?,?,?,?,?,?)", rows)
    con.commit()

    total = cur.execute("SELECT COUNT(*) FROM china_food_gi").fetchone()[0]
    print(f"china_food_gi 导入完成: {total} 条")
    print(f"  分类精确匹配 exact  : {n_exact}")
    print(f"  主名匹配   base     : {n_base}")
    print(f"  前缀匹配   prefix   : {n_prefix}")
    print(f"  未匹配     (仍保留) : {n_none}")

    print("\n各食物组条数:")
    for r in cur.execute(
            "SELECT food_group, COUNT(*) FROM china_food_gi GROUP BY food_group ORDER BY MIN(seq)"):
        print(f"  {r[0]:16s} {r[1]}")

    con.close()


if __name__ == "__main__":
    main()
