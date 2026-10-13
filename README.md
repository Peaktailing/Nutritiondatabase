# Nutrition Database · 食品营养数据整合库

整合 **9 个来源**的食品营养数据，覆盖 10 个国家/地区：

| 来源 | 数据量 | 说明 |
|------|-------:|------|
| **USDA FoodData Central**（美） | 2,101,279 食品 / 2,719 万条营养素 | 2026-04-30 完整包，全球最全 |
| **中国食物成分表 标准版 第6版** | 1,831 食物（已合并） | OCR 抽取 1,810 + 早期整理版补缺 21 |
| **英国 CoFID 2021** | 2,886 食物 | McCance & Widdowson's 第7版 |
| **法国 CIQUAL 2025** | 3,484 食物 | ANSES 官方 |
| **日本 MEXT 八订** | 2,478 食物 + 1,954 氨基酸 | 食品標準成分表 2020 |
| **印尼 TKPI 2017** | 1,146 食物 | Kemenkes 官方 |
| **FAO/INFOODS 西非** | 1,055 食物 | WAFCT 2019 |
| **东盟 FCD 2014** | 565 食物 | 印尼/马来/菲/泰/越/文莱 |
| **中国居民膳食营养素参考摄入量 2023版** | 277 行 | EAR/RNI/AI/UL/AMDR |

---

## 快速开始

```bash
# 1. 还原整合成品库（58 MB）
gunzip -c data/nutrition_data.sql.gz | sqlite3 nutrition.db

# 2. 查询（支持中文）
python3 scripts/query/query.py browse --name 三文鱼      # 中文检索
python3 scripts/query/query.py side 牛肉# 跨来源并排对照
python3 scripts/query/query.py bycat                     # 分类 × 来源矩阵
python3 scripts/query/query.py tables                    # 列出所有表
```

> `query.py` 默认读 `./nutrition.db`，可用 `--db` 指定路径。
>
> 想直接用 OCR 成果库（无需还原）：
> ```bash
> python3 scripts/query/query.py --db data/china-ocr/中国食物成分表.db tables
> ```

---

## 仓库结构

```
├── data/                ★ 全部原始数据（可追溯、可重算）
│   ├── usda/                          USDA 2026-04-30，34 个 CSV（37 个 gzip 分片）
│   │   ├── <表名>/<表名>.csv.gz.partNNN
│   │   └── MD5SUMS.txt34 条 MD5 校验
│   ├── international/                 法/英/日/西非/印尼/东盟 原始文件
│   ├── china/                         中国食物成分表 + DRIs 2023 + GI 附录
│   ├── china-ocr/                  ★ 中国第6版 OCR 抽取成果
│   │   ├── 中国食物成分表.db
│   │   ├── 中国食物成分表_USDA兼容版.db
│   │   ├── csv_tables/                5 张可直接导入的 CSV
│   │   ├── validation_report/         校验报告 + 抽取中间数据
│   │   ├── OCR_README.md              OCR 抽取管线详细文档
│   │   └── ocr_pipeline.zipOCR 处理管线归档
│   ├── nutrition_data.sql.gz        ★ 整合成品库（8 来源并排层）
│   └── RAW_DATA.md                   原始数据说明与还原方式
│
├── scripts/
│   ├── import/                        各来源原始层导入（7 个）
│   ├── normalize/                     并排归一化层构建（2 个）
│   ├── translate/                     名称中文化（词典 + 引擎，4 个）
│   ├── ocr-china/                  中国第6版 OCR 处理管线（26 个）
│   └── query/                         命令行查询
│
├── tools/
│   ├── split_usda.py                  USDA 分片打包 / 还原
│   ├── export_release.py              整合层导出
│   ├── rebuild_all.sh                 一键重建
│   ├── pdl_full.sh                    USDA 16 路并发下载器
│   └── dl_intl.sh                     国际库下载器
│
└── docs/
    ├── TECHNICAL.md完整技术文档
    ├── REBUILD.md                     重新整合流程
    └── CROSS_DB_PLAN.md               跨库比对实测与决策记录
```

---

## 整合成品库

| 表 | 行数 | 说明 |
|----|-----:|------|
| `norm_food` | 26,958 | **并排食物索引**，8 来源各一条独立记录，含中文名 |
| `norm_value` | 493,941 | 公制化数值（质量类一律 g，显示层转 mg/μg） |
| `norm_nutrient` | 29 | 统一营养素字典 |
| `norm_canon_cat` | 15 | 统一分类分段 |
| `china_food_composition` | 1,677 | 中国食物成分表第6版（早期整理版，原始留存） |
| `china_food_merged` | 1,831 | ★ 两版合并结果（并排层数据源） |
| `china_food_synthetic` | 39 | 被隔离的代表值估算（不进并排层） |
| `china_merge_map` | 1,872 | 合并决策日志，可审计 |
| `china_dri_2023` | 277 | 中国 DRIs 2023版 |
| `china_food_gi` | 259 | 中国食物 GI |
| `uk_cofid_food` | 34,644 | 英国 CoFID |
| `ciqual_food` | 3,484 | 法国 CIQUAL |
| `jp_mext_food` | 2,478 | 日本 MEXT |
| `id_tkpi_food` | 1,146 | 印尼 TKPI |
| `asean_fcd_2014` | 565 | 东盟 FCD |
| `fao_wafct_food` | 1,055 | FAO 西非 |

还原后约 58 MB，含 28 张表。

---

## 三个核心设计

### 1. 不做跨库合并（并排而非混合）

各库食物名**精确匹配率实测 0%**，模糊匹配召回 35% 但存在系统性误配：

| 查询 | USDA | 实际匹配到 | 错误类型 |
|------|------|-----------|---------|
| 黄油 | butter | 可可脂 | 相似词 |
| 奶油 | cream | 豆奶油 | 相似词 |
| 全脂奶粉 | whole milk powder | 奶昔 | 相似词 |

因此**不合并**：每条记录的来源、原始名称、原始分类全部保留，判断权交给使用者。

### 2. 数值统一公制

质量类一律以 g 存储，显示层按营养素习惯转 mg/μg。

**不做伪换算**：IU（维生素 A/D/E）、`UMOL_TE`(ORAC)、`MG_GAE`(总酚)、`SP_GR`(比重)、pH —— 换算系数依赖食物类别，强行换算会引入错误，故保留原值并标注。

### 3. 食物名称中文化（覆盖率 99.0%）

自建受控词典替代机器翻译。实测外部 MT 接口会把 `cheddar cheese` 译成粤语「車打芝士」、把 `whole-wheat` 切成「整个小麦」、把 `fat-free` 切成「脂肪+免费」。

- **词典**：`scripts/translate/glossary_en.py`，1,574 主料词条 / 12 个语义类别
- **机制**：全部词条拼成单个正则 alternation，对整条名称一次 `finditer` —— Python `re` 取最左成功分支，天然「最长短语优先」
- **语序**：`{状态:1, 烹饪:2, 加工:3, 宣称:4, 颜色:5, 国别:6, 形态:7, 取料:8}`
- **印尼语独立通路**：语序与英语相反（主料在前、修饰在后），需单独组装
- **日语本地化**：约 500 条假名→汉字表

| 来源 | 条数 | 有中文名 | 覆盖率 |
|------|-----:|-----:|-------:|
| 法国 / 英国 | 6,370 | 6,369 | 100.0% |
| 中国 | 1,831 | 1,815 | 99.1% |
| USDA / 日本 / 西非 | 17,200 | 17,170 | 99.8% |
| 印尼 | 1,146 | 1,065 | 92.9% |
| 东盟 | 565 | 420 | 74.3% |
| **合计** | **27,112** | **26,839** | **99.0%** |

中国库的 16 条缺口即上文 `name_missing`（原书名称列 OCR 丢失），非翻译失败。

---

## 中国数据：两版已合并

仓库里有两份中国成分表，**同属第6版标准版、互补而非迭代**，现已合并入并排层：

| 来源 | 条数 | 位置 | 说明 |
|------|-----:|------|------|
| **OCR 抽取版** | **1,810** | `data/china-ocr/` | 两册扫描件逐页 OCR，质量分级 A/B/C |
| 早期整理版 | 1,677 | `data/china/` | 第一册为主的结构化整理 |

编码重合度 89.2%（交集 1,615 / 并集 1,872）。早期整理版独有的 62 条经逐条甄别后分三类处置：

| 类别 | 条数 | 处置 | 依据 |
|------|-----:|------|------|
| `x` 后缀代表值 | 39 | **隔离**到 `china_food_synthetic` | 早期整理时对「一码多品种」做的合成估算（如 `102101x` 全脂奶粉），非原书条目 |
| 跨编码重名 | 2 | 归入 OCR 版，不重复计 | `081324≡081325` 猪里脊、`191001≡100161` 牛油 |
| 真补缺 | 21 | 整行取自早期整理版 | OCR 版完全没有的条目（娃娃菜、鲜驴奶、鱼肚干等） |

**合并结果 1,831 条** = OCR 1,810 + 真补缺 21。落地表：`china_food_merged`，决策日志 `china_merge_map`（1,872 条可审计）。

### 合并中发现的 OCR 读数错误

合并时用守恒关系复核，额外查出 **两簇 OCR 读数错误**（原 `check_grade` 未覆盖）：

| 标记 | 条数 | 症状 | 例 |
|------|-----:|------|-----|
| `ocr_carb_column_shift` | 107 | 碳水列读串，macro_sum > 106 | 豆角(鲜) 碳水 74.0 g（实际约 5-7）、鲜驼奶 99.0 g |
| `ocr_kj_decimal_shift` | 72 | kJ 小数点丢失，kJ/kcal < 3.5 | 米粉类 407 kcal 配 5.4 kJ（原书约 1702） |
| `ocr_macro_sum_low` | 3 | macro_sum < 94 | — |
| `name_missing` | 16 | 原书名称列 OCR 丢失 | 主表/CSV/sample_desc/USDA 兼容版四处均为空 |

一律用 `merge_flag` 旁注，**不改** OCR 脚本给出的 `check_grade`（那是原始判定，应尊重）。

### OCR 读数错误的自动修复（已完成）

`scripts/normalize/fix_ocr_shifts.py` 用守恒约束对上表标记的可疑行做假设检验修复，共修 **117 条**，决策日志在 `data/china-ocr/repair_log.json`（**182 条全覆盖**：117 修复 + 61 假警报 + 4 转人工，每条含 code/name/flag/修复前后值/五项和）：

| 修复类型 | 条数 | 方法 |
|------|-----:|------|
| 碳水列 ×10 / 蛋白列多读 0 / 脂肪列多读 0 | 46 | 五项守恒（水+蛋白+脂肪+碳水+灰分=100±2.5）strict 轮加能量校验（±30%），loose 轮仅守恒（记录的 kcal 可能与碳水同源出错，此时不能用作否决依据），唯一候选才采信 |
| kJ 小数点丢失（重算 kJ=kcal×4.184） | 13 | kcal 可信时直接换算 |
| kcal / kJ 两列互换 | 58 | ratio=kj/kcal∈[0.10,0.35] 且回代比值∈[3.6,5.2] |

另有 61 条 macro_sum 越界为**假警报**（数据自洽，宏量口径定义差异），只重算 macro_sum、不动数据；4 条多解不唯一**转人工**（`needs_manual_review` 标记，保持原值）：玉米笋罐头、茄子（白皮、长）、油菜心、红螺。

**该步骤已挂进 `rebuild_all.sh` 第 3.5 步**（合并之后、归一化之前）——顺序不能反，归一化层从 `china_food_merged` 取数，跳过修复步则 117 条修复不进成品。已验证：从零重跑合并+修复，与线上成品 1,831 行 × 46 列逐一比对**完全一致**。

**能量公式实测口径**：中国表碳水列**含膳食纤维**（总碳水），能量只计可利用碳水，`kcal_calc = 4×蛋白 + 9×脂肪 + 4×(碳水 − 纤维)`。纤维系数不可重复相加——否则茄子等合法修复假设会被误杀。

### 跨库交叉比对

`scripts/query/cross_db_report.py` 生成 [`docs/CROSS_DB_REPORT.md`](docs/CROSS_DB_REPORT.md) + `data/cross_db_match.csv`：

- **A 部分**：8 数据源 × 15 分类 × 10 营养素中位数对照（同分类横向核查异常源）
- **B 部分**：UK↔USDA 词集重叠匹配 230 对（阈值 3.5，分类一致 +1.0 分）。CN↔USDA 直接匹配误配率过半（中国表英文名仅 21 条补缺行有、描述句式与 USDA 差异大），故 B 部分不含 CN

### 符号语义与口径

中国表数值符号语义在合并层显式保留，**NULL ≠ 0**：

| 符号 | 含义 | 处理 |
|------|------|------|
| `Tr` / `tr` | 未检出 | → NULL |
| `—` / 空 | 未检测 / 不详 | → NULL |
| `*` | 参考值 | 数值保留，需人工判断 |
| `un` | 不能计算 | → NULL |

「未检出」与「含量为零」是两条不同的营养学结论，不可混同 —— 全库没有任何一处把 `Tr` 写成 0。

**`macro_sum` 口径经实测确认 = 水 + 蛋白 + 脂肪 + 碳水 + 纤维 + 灰分**（六项合计，理论约 98%）。原 OCR 文档写作「六大宏量合计」，指的是同一组列，但不含灰分——复核时须按六项算，否则会误报 500+ 条越界。

### ⚠️ 跨库碳水不可直接比较

USDA 的 `Carbohydrate, by difference` 是**减差法**计算值（总碳水 − 纤维 − …），中国表的碳水化合物是**可利用碳水**口径，两者定义不同。本库在并排层保持各自口径，`china_food_merged.carb_note` 字段逐行标注，**不做任何跨库碳水合并**。

### ⚠️ 合并中国数据时必读

USDA 的 `Carbohydrate, by difference` 是**减差法**计算值，与中国表的「可利用碳水」口径不同，两者不可直接比较（详见上一节的 `carb_note`）。符号标记语义已在合并层显式处理为 NULL，不会被当成 0。

---

## 重新整合

```bash
bash tools/rebuild_all.sh    # 约 40 分钟，峰值磁盘 9 GB
```

详见 [`docs/REBUILD.md`](docs/REBUILD.md)。

**还原 USDA 分片**：

```bash
python3 tools/split_usda.py restore data/usda ./usda
cd usda/FoodData_Central_csv_2026-04-30 && md5sum -c ../../data/usda/MD5SUMS.txt
```

> USDA 原始 CSV 3.1 GB，最大单文件 `food_nutrient.csv` 有 1709 MB，超过 GitHub 100 MB 限制，故 gzip 后按 90 MB 分片（压缩率 85.2%）。**还原后 MD5 与官方文件 34/34 完全一致。**

---

## 数据来源

| 数据集 | 发布方 | 授权 |
|--------|--------|------|
| USDA FoodData Central | 美国农业部 | 公共领域 |
| 中国食物成分表 第6版 | 中国疾控中心 | 公开出版物 |
| 中国 DRIs 2023版 | 中国营养学会 | 公开出版物 |
| CIQUAL 2025 | 法国 ANSES | 公开 |
| CoFID 2021 | 英国 SACN / McCance & Widdowson's | 公开 |
| 食品標準成分表八訂 | 日本文部科学省 | 公开 |
| TKPI 2017 | 印尼卫生部 Kemenkes | 公开 |
| WAFCT 2019 | FAO / WHO | 公开 |
| ASEAN FCD 2014 | 东盟 | 公开 |

各数据集版权归原发布机构所有。本仓库仅做结构化整理，**数值未作修改**。

---

## 免责声明

本项目为个人性质的数据整理成果。原始数据的准确性、完整性以各发布机构为准。中国 DRIs 部分数值受获取渠道限制未经原书逐项核验（`verified` 字段已标明）。OCR 抽取数据可能残留个别识别误差，已用质量守恒、能量守恒、kJ/kcal 一致性三重约束修正，但仍建议关键数据交叉核对原书。

**请勿将本数据用于临床或医疗决策。**

---

## LICENSE

MIT License，版权归 Peaktailing 所有。见 [`LICENSE`](LICENSE)。数据本身遵循各自来源机构的授权条款。