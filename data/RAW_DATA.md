# 原始数据说明

本目录存放各国**原始数据文件**，用于追溯与重算。整合后的成品库见仓库根目录的 `nutrition_data.sql.gz`。

## 目录结构

```
data/
├── nutrition_data.sql.gz      ★ 整合成品库（58 MB 解压后可查询，见 README 快速开始）
├── usda/                     USDA FoodData Central 2026-04-30（分片，见下）
│   └── <表名>/
│       └── <表名>.csv.gz.part000 ...
├── international/            法/英/日/FAO 西非/印尼/东盟 原始文件
└── china/                    中国食物成分表 + DRIs 2023 + GI 附录
```

## USDA 分片说明

**为什么分片**：GitHub 单文件硬限制 100 MB，而 USDA 最大的 `food_nutrient.csv` 有 1709 MB。gzip 后约 220 MB，仍超限，故按 90 MB 切片。

**体积**：原始 3.1 GB → 压缩分片后约 460 MB（压缩率约 86%）。

**还原方法**：

```bash
# 从仓库根目录执行（需要 git-lfs 或仓库已完整 clone）
python3 tools/split_usda.py restore data/usda ./usda

# 或手动拼接：
cd data/usda/food_nutrient
cat food_nutrient.csv.gz.part* > /tmp/food_nutrient.csv.gz
gunzip -c /tmp/food_nutrient.csv.gz > usda/food_nutrient.csv
```

> 切片文件名 `*.part000`、`*.part001`… 按序号**字典序排序即为正确顺序**，用 `cat *.part*` 即可。

**或者直接从 USDA 官网下载原始包**（推荐，更快）：

```bash
curl -O https://fdc.nal.usda.gov/download-datasets/FoodData_Central_csv_2026-04-30.zip
unzip FoodData_Central_csv_2026-04-30.zip -d usda/
```

## 国际数据

| 文件 | 来源 | 格式 |
|------|------|------|
| `fr_ciqual_2025.xlsx` | 法国 CIQUAL 2025（ANSES 官方英文版） | xlsx |
| `uk_cofid_2021.xlsx` | 英国 CoFID 2021（McCance & Widdowson's 第7版） | xlsx |
| `jp_mext_2020_ch2.xlsx` | 日本食品標準成分表 2020 八訂 第2章 | xlsx |
| `jp_mext_2020_amino1.xlsx` | 同上·氨基酸成分 | xlsx |
| `fao_wafct_2019.xlsx` | FAO/INFOODS 西非食物成分表 2019 | xlsx |
| `id_tkpi_2017.csv` | 印尼 TKPI 2017（Kemenkes） | csv |
| `id_tkpi_2017_names.csv` | 印尼名称补全表 | csv |
| `asean_fcd_2014.csv` | 东盟食物成分数据库 2014（原始解析） | csv |
| `asean_fcd_2014_clean.csv` | 同上·清洗版 | csv |
| `asean_p35.xml` | 东盟 PDF 坐标法解析产物 | xml |

## 中国数据

| 文件 | 说明 |
|------|------|
| `food_composition_full.csv` | 中国食物成分表（标准版 第6版），1677 条食物 |
| `dri_2023.csv` | 中国居民膳食营养素参考摄入量（2023版），277 行 |
| `glycemic_index_of_foods.json` | 中国食物血糖生成指数（第6版附录），259 条 |
| `README.md` | 中国数据字段说明 |

## 数据来源与授权

- **USDA** — 美国农业部公共领域数据
- **CIQUAL** — 法国ANSES
- **CoFID** — 英国 McCance & Widdowson's
- **MEXT** — 日本文部科学省
- **WAFCT** — FAO/WHO 西非食物成分表
- **TKPI** — 印尼卫生部（Kemenkes）
- **ASEAN FCD** — 东盟食物成分数据库
- **中国食物成分表 / DRIs / GI** — 公开出版物内容

各数据集版权归原发布机构所有。本仓库仅做结构化整理，**数值未作修改**。