#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ASEAN FCD 名称修复 + 重译。

问题：ASEAN 原始表的 food_name 在 CSV 解析时被本地语言（泰/越/马来语）打乱了，
      565 条里有 29 条为空、281 条无法翻译 —— 但 desc 列完整保留了
      「代码 语言码 英文名 本地语名」的结构，可从里面把英文名救回来。

做法：以「语言码 / 食物代码」为切点把 desc 切成若干纯英文片段，
      取词数最多的一段作英文名；只有比现有名字更长时才替换。
"""
import sqlite3, re, html, sys, os

DB = os.environ.get("FDC_DB", "/workspace/fdc/nutrition.db")
CODE = r'[A-Z]{2,3}\d{1,4}[A-Z]?'
LANG = r'(?:TH[BC]|VN[BC]|MY[BC]|PH[BC]|ID[BC]|BR[BC]|YD)'
MARK = re.compile(r'(?:' + LANG + r'\d{0,4}|' + CODE + r')')
NONLAT = re.compile(r'[\u0e00-\u0e7f\u0100-\u024f\u1e00-\u1eff]')


def extract(desc):
    """从 ASEAN desc 里救回最完整的英文食物名"""
    if not desc:
        return None
    d = html.unescape(str(desc)).replace('\u200b', ' ').replace('−', '-')
    cands = []
    for s in MARK.split(d):
        s = s.strip(' ,;-()')
        if not s or NONLAT.search(s) or not re.match(r'^[A-Za-z]', s):
            continue
        nw = len(re.findall(r'[A-Za-z]{2,}', s))
        if nw < 2:
            continue
        s = re.sub(r'\([A-Z]{2}\)', '', s).strip(' ,;-')
        cands.append((nw, len(s), s))
    if not cands:
        return None
    cands.sort(key=lambda x: (-x[0], -x[1]))
    return re.sub(r'\s+', ' ', cands[0][2])[:90]


def main(apply=False):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    rows = cur.execute("select food_code, food_name, desc from asean_fcd_2014").fetchall()
    print(f"ASEAN 共 {len(rows)} 条")

    upd_name = []
    for code, fn, desc in rows:
        got = extract(desc)
        if not got:
            continue
        if fn and len(str(fn).strip()) >= len(got):
            continue                      # 没有变好就不动
        upd_name.append((got, code))

    # 同步修 norm_food.name_en / name_local
    upd_norm = []
    for code, fn, desc in rows:
        got = extract(desc)
        if not got:
            continue
        old = (fn or "")
        if len(str(old).strip()) >= len(got):
            continue
        upd_norm.append((got, code))

    print(f"可改进命名的 {len(upd_name)} 条")
    if apply:
        cur.executemany("update asean_fcd_2014 set food_name=? where food_code=?",
                        upd_name)
        cur.execute("update norm_food set name_en=(select food_name from "
                    "asean_fcd_2014 a where a.food_code=norm_food.source_id) "
                    "where source='ASEAN'")
        cur.execute("update norm_food set name_cn=null, translate_status=null,"
                    " translate_method=null, translate_unknown=null "
                    "where source='ASEAN'")
        con.commit()
        print(f"已更新 asean_fcd_2014 {len(upd_name)} 行；"
              f"norm_food 的 ASEAN 条目已重置待重译")
    con.close()


if __name__ == "__main__":
    main(apply=("--apply" in sys.argv))
