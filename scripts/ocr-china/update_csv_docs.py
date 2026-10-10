# -*- coding: utf-8 -*-
"""附录 CSV 添加分册列 + 更新 README/校验报告"""
import csv, sqlite3, os

BASE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(BASE, "pkg")
DB1 = os.path.join(PKG, "数据库", "中国食物成分表.db")

# 1. 从主库读 food_code -> volume 映射(保证 CSV 与 DB 完全一致)
con = sqlite3.connect(DB1)
cur = con.cursor()
vol_map = {}
for t in ["food_nutrition", "sample_desc", "amino_acid", "fatty_acid"]:
    for c, v in cur.execute(f"SELECT food_code, volume FROM {t}"):
        if c and v:
            vol_map.setdefault(c.strip(), v)
con.close()
print(f"库内映射: {len(vol_map)} code")

# 2. 附录 3 个 CSV 加"分册"列
APPENDIX = [
    "数据表CSV/附录_食物样品描述.csv",
    "数据表CSV/附录_食物氨基酸含量.csv",
    "数据表CSV/附录_食物脂肪酸含量.csv",
]
for rel in APPENDIX:
    path = os.path.join(PKG, rel)
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        rows = list(reader)
    header, data = rows[0], rows[1:]
    if "分册" in header:
        idx = header.index("分册")
        header = [h for i, h in enumerate(header) if i != idx]
        data = [[c for i, c in enumerate(r) if i != idx] for r in data]
    header.append("分册")
    n1 = n2 = nblank = 0
    out = [header]
    for r in data:
        code = r[0].strip() if r else ""
        v = vol_map.get(code, "")
        if v == "第一册": n1 += 1
        elif v == "第二册": n2 += 1
        else: nblank += 1
        out.append(r + [v])
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh).writerows(out)
    print(f"{os.path.basename(rel)}: 第一册={n1} 第二册={n2} 留空={nblank}")

# 3. README.md 追加 volume 说明
readme_path = os.path.join(PKG, "README.md")
readme = open(readme_path, encoding="utf-8").read()
VOL_SECTION = """
## v2 更新：新增 volume（册次）字段

四张表（food_nutrition / sample_desc / amino_acid / fatty_acid）均已添加 `volume` 列，标注数据来自第几册。附录三个 CSV 同步添加"分册"列。

**分册判定规则**（以原书两册实际页面归属为准）：

| food_code 前两位 | 分册 | 说明 |
|---|---|---|
| 01~07 | 第一册 | 植物性食物（谷薯、豆类、蔬菜、菌藻、水果、坚果） |
| 08~13 | 第二册 | 动物性食物（畜禽肉、乳蛋、鱼虾蟹贝） |
| 19 且段位 1910 | 第二册 | 动物油脂（猪油/羊油/鸭油等） |
| 19 且段位 1920/1921/1922 | 第一册 | 植物油脂（通用油/品牌油/进口橄榄油） |
| 21 | 第二册 | 其他（药食两用等） |

- 主表 1810 行 100% 定册（第一册 844 / 第二册 966），以原始两个营养 CSV 的逐行拆分为硬依据
- 附录三表优先按主表映射，油脂类按段位规则，仅 amino_acid 表 3 个 OCR 异常编码（161101/601180/801111）无法判定留空
- `meta` 表 `volume_mapping` 条目记录完整规则
"""
if "v2 更新" not in readme:
    readme = readme.rstrip() + "\n" + VOL_SECTION
    open(readme_path, "w", encoding="utf-8").write(readme)
    print("README.md 已更新")

# 4. 校验报告追加
report_path = os.path.join(PKG, "校验与中间数据", "校验报告.txt")
lines = open(report_path, encoding="utf-8").read().rstrip().splitlines()
vol_line = "volume册次标注: 主表1810行全部定册(第一册844/第二册966); sample_desc 1084全定; fatty_acid 972全定; amino_acid 853/856定册(3个OCR异常编码161101/601180/801111留空)"
if not any("volume册次标注" in l for l in lines):
    lines.append(vol_line)
    open(report_path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("校验报告.txt 已追加")
