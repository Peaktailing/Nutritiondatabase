# 营养数据整合库（USDA + 中国 + 国际）

一个 SQLite 整合库，包含 **8 个来源、10 个国家/地区** 的营养数据：

| 数据集 | 状态 | 内容 |
|--------|------|------|
| **USDA FoodData Central**（2026-04-30 完整包） | ✅ 已完成 | 美国农业部食品营养库，210 万条食品 / 2719 万条营养素记录 |
| **中国食物成分表（标准版 第6版）** | ✅ 已完成 | 1677 条食物、61 个类别、31 项营养素（含英文名） |
| **中国食物血糖生成指数（第6版附录）** | ✅ 已完成 | 259 条 GI 数据、11 个食物组，已与成分表食物做名称匹配 |
| **中国居民膳食营养素参考摄入量（2023版）** | ✅ 已完成 | EAR / RNI / AI / UL / AMDR，277 行，逐行标注来源与核实状态 |
| **法国 CIQUAL 2025** | ✅ 已完成 | 3484 条食物、84 列，ANSES 官方英文版 |
| **英国 CoFID 2021** | ✅ 已完成 | 34,644 行 / 279 列（McCance & Widdowson's 第7版；按 `food_code` 去重后为 2,886 种食物） |
| **日本食品標準成分表 2020（八訂）** | ✅ 已完成 | 2478 条食物 + 1954 条氨基酸成分 |
| **FAO/INFOODS 西非食物成分表 2019** | ✅ 已完成 | 1028 条真实食物（WAFCT） |
| **印尼食物成分表 TKPI 2017** | ✅ 已完成 | 1146 条食物（Kemenkes 官方数据），名称已补全 1146/1146 |
| **东盟食物成分数据库 ASEAN FCD 2014** | ✅ 已完成 | 565 条食物，覆盖印尼/马来西亚/菲律宾/泰国/越南/文莱 |

数据库文件：**`/workspace/fdc/nutrition.db`**（约 4.4 GB，8 个来源共 3610 万行）

> 汇总：**美 / 中 / 法 / 英 / 日 / 西非（区域）/ 印尼 / 东盟六国** 八大来源全部入库，全部为官方公开数据。
> 东南亚此前是缺口，现由 **TKPI 2017 + ASEAN FCD 2014** 补上（越南、泰国主要以 ASEAN FCD 形式覆盖）。
>
> 跨库并排层（`norm_food` 等）已做**食物名称中文化**，覆盖率 **99.1%**（26,711 / 26,958），全库支持中文检索，详见 [第七节](#七食物名称中文化覆盖率-991)。

---

## 一、中国食物成分表（已完成）

**表：`china_food_composition`** — 1677 条 × 36 列

| 字段 | 说明 |
|------|------|
| `category` | 食物类别（61 类，如「谷类及其制品-小麦」「蔬菜类及其制品-嫩茎叶花菜类」） |
| `foodCode` | 食物编码（第6版编码体系） |
| `foodName` / `englishName` | 中文名 / 英文名（1241 条有英文名，可用于与 USDA 库对照） |
| `edible` | 可食部（%） |
| `energyKCal` / `energyKJ` | 能量（kcal / kJ） |
| `protein` `fat` `CHO` `dietaryFiber` `cholesterol` `ash` | 宏量营养素（g / mg，**每 100g 可食部**） |
| `vitaminA` `carotene` `retinol` `thiamin` `riboflavin` `niacin` `vitaminC` `vitaminE*` | 维生素 |
| `Ca` `P` `K` `Na` `Mg` `Fe` `Zn` `Se` `Cu` `Mn` | 矿物质 |
| `remark` | 备注（多为产地/来源） |

> 原表用 `—` 表示未检测/无数据、`Tr` 表示痕量，两者在数值列中均记为 `NULL`。

**视图：`v_china_foods`** — 常用列速查（编码、类别、中英文名、能量、蛋白、脂肪、碳水、钙铁锌、维A、维C）。

数据来源与加工：原书为《中国食物成分表（标准版 第6版）》（杨月欣主编）。
本库数据取自开源项目 [Sanotsu/china-food-composition-data](https://github.com/Sanotsu/china-food-composition-data)
的**人工矫正版 + 英文名增强版**：先由两个视觉大模型交叉识别书中表格，再自动校验（恒等式/值域/行数/双模型共识），
最后人工定点复核。该数据集**不含「婴幼儿食品」分类**（原书该栏位结构不同且多为品牌奶粉商品）。
数值为本库原样收录，未作修改。

---

## 二、中国食物血糖生成指数（GI）（已完成）

**表：`china_food_gi`** — 259 条 × 8 列

《中国食物成分表（标准版 第6版）》附录中的**食物血糖生成指数（GI）**数据，
是原书独立于「一般营养成分」表格之外的一整套数据，本库单独收录。

| 字段 | 说明 |
|------|------|
| `seq` | 书内序号（1–259） |
| `food_group` | 11 个食物组：糖类、谷类及制品、薯类/淀粉及制品、豆类及制品、蔬菜类、水果类及制品、种子类、乳及乳制品、速食食品、饮料类、混合膳及其他 |
| `food_name` | 原书食物名（带 `*` 者为引用自国际 GI 表的条目） |
| `gi_value` | 血糖生成指数（葡萄糖 = 100） |
| `matched_food_code` | 匹配到的 `china_food_composition.foodCode`（可为空） |
| `matched_food_name` | 匹配到的食物名 |
| `match_type` | `exact`（同名）/ `base`（主名一致）/ `prefix`（前缀）/ 空（未匹配） |

**匹配结果**：259 条中 82 条成功关联到成分表食物（15 exact + 65 base + 2 prefix）。
匹配规则刻意保守，避免 `菠萝` 误配到 `菠萝蜜`、`甜菜` 误配到 `甜菜叶` 之类跨物种/跨部位错误；
未匹配的条目（如「速食食品」组）原书 GI 表本身即为独立收录，成分表无对应条目，属正常情况。

```bash
python3 query.py gi 米饭              # 搜米饭类 GI
python3 query.py gi --group 水果      # 按食物组查
python3 query.py gi 馒头 --limit 10
```

```sql
-- 高 GI（≥70）食物
SELECT food_name, gi_value FROM china_food_gi
WHERE gi_value >= 70 ORDER BY gi_value DESC;

-- 某食物的 GI 及其营养成分（联合查询）
SELECT g.food_name, g.gi_value, f.energyKCal, f.protein, f.CHO
FROM china_food_gi g JOIN china_food_composition f ON f.foodCode = g.matched_food_code
WHERE g.gi_value IS NOT NULL LIMIT 10;
```

---

## 三、中国居民膳食营养素参考摄入量（2023版）（已完成）

**表：`china_dri_2023`** — 277 行

| 字段 | 说明 |
|------|------|
| `nutrient_key` / `nutrient_cn` | 营养素（英文键 / 中文名） |
| `unit` | 单位（μgRAE/d、mgNE/d、μgDFE/d、%E 等） |
| `age_group` | 年龄段（`18岁~`、`65岁~`、`孕中期`、`乳母` 等） |
| `sex` | `male` / `female` / `both` |
| `dri_type` | `EAR` / `RNI` / `AI` / `UL` / `AMDR` / `EER` |
| `value` | 数值（**绝对摄入量**，非增量） |
| `value_text` | 区间型取值（如 AMDR `20-30`） |
| `source` | 数据来源 |
| `verified` | **1 = 已核实（原书表格/营养学会发布值）；0 = 社区整理，待原书核验** |
| `note` | 说明（含原书增量换算过程） |

纯文本副本：**`/workspace/fdc/china/dri_2023.csv`**（便于人工审阅/修订）。

### ⚠️ 重要：版本混淆已修正
2023 版 DRIs 官方**没有提供机读下载**，网上流传的结构化数据普遍混入了 **2013 版**数值。本库已按原书逐项校正，已知被修正的坑：

| 营养素 | ❌ 常见错误值（2013版） | ✅ 2023版正确值 |
|--------|----------------------|----------------|
| 维生素A（18岁~） | 男 800 / 女 700 μgRAE | **男 770 / 女 660 μgRAE**（UL 3000） |
| 铁（18-49岁女性） | RNI 20 mg/d | **RNI 18 mg/d**（EAR 12，UL 42；孕中/晚 25/29，乳母 24） |

已核实（verified=1）的完整年龄表：**维生素A**（原书表11-1-1）、**铁**（原书表10-1-1）、
**碘**（中国营养学会 2023 发布值）。其余成人/老人分性别数值为社区整理（verified=0），
已交叉核对但与 2023 版一致性的最终核验请以原书为准。

---

## 四、USDA FoodData Central（已完成）

已下载并导入**官方完整 CSV 整合包** `FoodData_Central_csv_2026-04-30.zip`（459 MB，481,517,495 字节，
已通过 `unzip -t` 完整性校验）。

导入结果（表已在 `nutrition.db` 中）：

| 表 | 行数 | 说明 |
|----|------|------|
| `food` | 2,101,279 | 食品入口表，主键 `fdc_id`，含 `data_type`、`description` |
| `food_nutrient` | 27,195,013 | 食品-营养素-数值事实表（含 `fdc_id`、`nutrient_id`、`amount`） |
| `branded_food` | 1,999,950 | 商业包装食品（含条码、品牌等） |
| `nutrient` | 477 | 营养素字典（名称、单位） |
| `food_category` / `measure_unit` / `food_portion` | — | 分类 / 计量单位 / 份量 |
| `foundation_food` `sr_legacy_food` `survey_food` | — | 各类型食物扩展属性 |

视图：
- `v_foods` — 统一食品视图（联 `food_category`，给出 `fdc_id, data_type, description, food_category, publication_date`）
- `v_food_nutrients` — 人读的营养素视图（`fdc_id, nutrient_name, amount, unit_name`）

> 原始 zip 保留在 `/workspace/fdc/`，`extract/` 为解压目录（约 3.2 GB）。
> 注：`food_nutrient` 是 2719 万行的大表，已在 `fdc_id`、`nutrient_id` 上建索引。

---

## 五、国际食物数据库（已完成）

数据存放在 `intl/`，来源均为**官方免费公开**文件：

| 文件 | 来源 | 状态 |
|------|------|------|
| `fr_ciqual_2025.xlsx` | 法国 ANSES-CIQUAL 2025 英文版 | ✅ 已入库 → `ciqual_food` |
| `fao_wafct_2019.xlsx` | FAO/INFOODS 西非食物成分表 | ✅ 已入库 → `fao_wafct_food` |
| `uk_cofid_2021.xlsx` | 英国 CoFID (McCance & Widdowson's 第7版) | ✅ 已入库 → `uk_cofid_food` |
| `jp_mext_2020_ch2.xlsx` | 日本食品標準成分表 2020(八訂) 本表 | ✅ 已入库 → `jp_mext_food` |
| `jp_mext_2020_amino1.xlsx` | 日本 氨基酸成分表 第1表 | ✅ 已入库 → `jp_mext_amino_food` |

东南亚数据存放在 `intl_sea/`（此前为覆盖缺口，现补上）：

| 文件 | 来源 | 状态 |
|------|------|------|
| `id_tkpi_2017.csv` | 印尼 TKPI 2017（Tabel Komposisi Pangan Indonesia） | ✅ 已入库 → `id_tkpi_food`（1146 条） |
| `asean_fcd_2014.pdf` / `asean_fcd_2014_clean.csv` | 东盟 ASEAN Food Composition Database 2014 | ✅ 已入库 → `asean_fcd_2014`（565 条） |

导入脚本：`build_intl.py`（自动处理 **欧洲小数逗号**、多行表头、INFOODS tagname 等格式差异）；
东南亚部分用 `build_sea.py`，其中 **ASEAN FCD 2014 是从 PDF 表格用坐标法重建**（`parse_asean.py`，
按 x 坐标对齐 22 个营养数列，`(值)`/`-`/`Tr` 分别处理为计算值 / 缺失 / 痕量）。

### 表字段说明

**`ciqual_food`**（3484 行 × 84 列，法国 CIQUAL 2025）
- 标识：`alim_code`、`alim_nom_eng`（英文名）、`alim_nom_sci`（学名）
- 分类：`alim_grp_nom_eng` / `alim_ssgrp_nom_eng` / `alim_ssssgrp_nom_eng`
- 营养素列：`名称__单位_基准`，如 `protein__g_100g`、`calcium__mg_100g`

**`uk_cofid_food`**（31757 行 × 267 列，英国 CoFID 2021）
- 由 14 个数据 sheet（Proximates / Inorganics / Vitamins / 各类脂肪酸 / 植物甾醇 / 有机酸）合并
- 标识：`food_code`（如 `12-346`）、`food_name`、`group`
- 营养素列：`名称__单位`，如 `protein__g`、`energy_kcal__kcal`、`retinol__ug`

**`jp_mext_food`**（2478 行 × 59 列，日本 2020 八訂）
- 标识：`food_number`（食品番号，如 `01081`）、`food_name`（日文名）
- 营养素列用 **INFOODS 成分識別子**：`ENERC_KCAL`（kcal）、`WATER`、`PROT-`、`FAT-`、`CHOCDF-`、`NA` 等

**`jp_mext_amino_food`**（1954 行，日本氨基酸成分表）

**`fao_wafct_food`**（1055 行，含分类标题行，真实食物 1028 条）
- `Code`（格式 `01_172`）；`_is_food=1` 筛真实食物
- `Food_name_in_English` / `Food_name_in_French` / `Scientific_name`
- 营养素用 INFOODS 标签：`ENERC`、`PROTCNT`、`FAT`、`CHOAVLDF`、`CA`、`FE`、`ZN` 等

**`id_tkpi_food`**（1146 行 × 20 列，印尼 TKPI 2017）
- 标识：`food_code`（如 `AP001`）
- 营养素列已改为规范英文名：`energy_kcal`、`protein_g`、`fat_g`、`carbohydrate_g`、
  `fiber_g`、`calcium_mg`、`iron_mg`、`vitamin_c_mg` 等

**`asean_fcd_2014`**（565 行 × 26 列，东盟六国）
- 标识：`food_code`、`food_name`（英文名）、`desc`（含各国本地名，`(TH)`/(VN)/(MY)/(PH) 等标注国别）、`group`
- 营养素列用 INFOODS 标签：`energy_kcal`、`WATER`、`PROCNT`、`FAT`、`CHOAVLDF`、`CA`、`FE`、`ZN`、`VITC` 等
- 由 PDF 表格重建，`(值)` 为计算值、`-` 为缺失（NULL）、`T`/`tr` 为痕量

### 国际库查询

```bash
python3 query.py ciqual camembert   # 法国 CIQUAL
python3 query.py cofid cheddar      # 英国 CoFID
python3 query.py mext 米            # 日本 MEXT
python3 query.py wafct millet       # FAO 西非表
python3 query.py tkpi AP0           # 印尼 TKPI
python3 query.py asean rice         # 东盟 ASEAN FCD
```

```sql
-- CIQUAL：高钙食物
SELECT alim_nom_eng, calcium__mg_100g FROM ciqual_food
WHERE calcium__mg_100g IS NOT NULL ORDER BY calcium__mg_100g DESC LIMIT 10;

-- CoFID：蛋白质最高的食物
SELECT food_name, protein__g FROM uk_cofid_food
WHERE protein__g IS NOT NULL ORDER BY protein__g DESC LIMIT 10;

-- 日本：某食品的能量与三大营养素
SELECT food_name, "ENERC_KCAL", "PROT-", "FAT-", "CHOCDF-" FROM jp_mext_food
WHERE food_name LIKE '%こめ%' LIMIT 10;

-- 印尼 TKPI：高维生素C 食物
SELECT food_code, vitamin_c_mg FROM id_tkpi_food
WHERE vitamin_c_mg IS NOT NULL ORDER BY vitamin_c_mg DESC LIMIT 10;

-- 东盟：按国家查（desc 中含国别标记）
SELECT food_code, food_name, energy_kcal FROM asean_fcd_2014
WHERE desc LIKE '%(TH)%' LIMIT 10;   -- 泰国
```

---

## 六、并排浏览层（跨库对照，**不合并**）

> 设计原则：**不做跨库食物实体合并**，各来源保持独立记录，按**统一分类 + 名称 + 状态**并排排列；所有数值**统一换算到公制**（质量类一律 g 存储，显示层转 mg/μg）。
>
> 为什么不做合并：实测各库食物名**精确匹配率 0%**，模糊匹配召回 35% 但存在系统性误配（黄油→可可脂、奶油→豆奶油、全脂奶粉→奶昔）。不合并就没有误配，每条记录的来源、原始名称、原始分类全部保留，判断权交给使用者。

### 表结构

| 表/视图 | 说明 |
|---------|------|
| `norm_nutrient` | 29 个统一营养素（`nut_key` / 中文名 / 统一单位 / 类型），其中 **23 个有实际数值** |
| `norm_canon_cat` | 15 个统一分类分段 |
| `norm_food` | **26,958 条**并排食物索引，每来源一条独立记录 |
| `norm_value` | **493,941 条**公制化数值（每食物 × 每营养素） |
| `v_by_cat` | 视图：分类分段 × 来源 分布矩阵 |
| `v_browse` | 视图：分类 + 来源 + 名称 + 公制指标 |

`norm_food` 字段：

| 字段 | 说明 |
|------|------|
| `source` | `CN` / `UK` / `FR` / `USDA` / `JP` / `ASEAN` / `WAFCT` / `ID` |
| `source_id` | 该库原始编码，可回溯原始表 |
| `name_local` / `name_en` | 本地语言名 / 英文名 |
| `name_cn` | **中文名**（见第七节，覆盖率 99.1%） |
| `translate_status` | `ok`(全词命中) / `partial`(有未收录词) / `native`(原文即中文) / `untranslated` |
| `translate_method` | `dict` / `id_dict` / `native` |
| `translate_unknown` | 未收录词清单（便于后续迭代补词） |
| `canon_cat` | 15 个统一分段之一 |
| `cat_raw` | 该库原始分类字段（原样保留） |
| `state` / `state_basis` | 状态判定 + **判定依据**（可审计） |
| `kcal` `protein` `fat` `carb` | 冗余指标，便于排序浏览 |
| `note` | 已知问题标注 |

`norm_value` 字段：`value_si`（统一 SI 值，质量类一律 g）、`display_val` + `display_unit`（按营养素习惯显示 mg/μg）、`raw_value` + `raw_unit`（原值留存）。

### 15 个统一分类分段

乳蛋类、肉类、水产、蔬菜、水果、谷类、豆类、坚果种子、油脂、糖类、饮料、调味品、零食、婴幼儿、其他

各来源归一化后分布（`python3 query.py bycat` 可直接打印）：

| 分段 | 合计 | 中国 | 英国 | 法国 | USDA | 日本 | 东盟 | 西非 | 印尼 |
|------|-----:|-----:|-----:|-----:|-----:|-----:|-----:|-----:|-----:|
| 其他 | 8,006 | 0 | 0 | 1,040 | 5,597 | 664 | 45 | 166 | 494 |
| 肉类 | 4,410 | 267 | 645 | 579 | 2,364 | 302 | 44 | 125 | 84 |
| 蔬菜 | 2,652 | 379 | 672 | 262 | 913 | 136 | 116 | 110 | 64 |
| 谷类 | 2,207 | 138 | 378 | 214 | 945 | 274 | 0 | 160 | 98 |
| 水产 | 1,748 | 249 | 285 | 184 | 288 | 438 | 114 | 56 | 134 |
| 水果 | 1,437 | 182 | 228 | 300 | 430 | 59 | 77 | 78 | 83 |
| 乳蛋类 | 1,326 | 270 | 33 | 414 | 341 | 137 | 42 | 51 | 38 |
| 豆类 | 846 | 81 | 0 | 53 | 351 | 64 | 43 | 142 | 112 |
| 糖类 | 841 | 0 | 76 | 361 | 360 | 18 | 14 | 3 | 9 |
| 零食 | 831 | 21 | 31 | 0 | 683 | 89 | 7 | 0 | 0 |
| 调味品 | 774 | 0 | 191 | 0 | 323 | 149 | 50 | 58 | 3 |
| 油脂 | 589 | 26 | 223 | 0 | 228 | 53 | 0 | 40 | 19 |
| 饮料 | 539 | 0 | 74 | 0 | 370 | 65 | 13 | 12 | 5 |
| 婴幼儿 | 384 | 0 | 0 | 39 | 345 | 0 | 0 | 0 | 0 |
| 坚果种子 | 368 | 64 | 50 | 38 | 156 | 30 | 0 | 27 | 3 |

> USDA 的 8,006 条「其他」中约 5,597 条是 `survey_fndds_food` 的 `food_category_id` 为 NULL 所致，属数据源本身的分类缺失。

### 公制化规则

```
质量类 → 一律换算到 g 存储，显示层按需转 mg / μg
  g = 1.0     mg = 0.001     μg = 1e-6     ng = 1e-9

显示单位：
  水分/蛋白/脂肪/碳水/纤维 → g
  钙/铁/磷/钾/钠/锌        → mg
  硒/维生素A/维生素E       → μg
  能量                      → kcal（能量不与质量混用）
```

**非公制单位不做伪换算**：IU（维生素 A/D/E）、`UMOL_TE`(ORAC)、`MG_GAE`(总酚)、`SP_GR`(比重)、pH —— 这些保留原值并标注，因为换算系数依赖食物类别，强行换算会引入错误。

### 食物状态维度

状态不对齐的比对等于没比对（生食/烤熟/苹果干/苹果汁能量密度可差 5 倍）。归一为受控词表：

| `state` | 含义 | 判定依据举例 |
|---------|------|------------|
| `raw` | 生/鲜 | 名称含 `raw/fresh/生/鲜`，或中国库无状态词默认 |
| `cooked` | 熟/烹饪后 | 名称含 `grilled/boiled/烤/炒/（熟）` |
| `processed` | 加工 | 名称含 `canned/smoked/pickled/罐头/（干）` |
| `dried_or_concentrated` | 干制/浓缩 | 含水 ≤15% 兜底 |
| `unknown` | 未标注 | 名称不含任何状态线索 |

**中国库状态判定**（用户判断「几乎所有食物都是新鲜分割或清洗、未加工」经实测验证）：名称括号内显式状态 > 烹饪动作词 > 加工保藏词 > 含水量兜底。1,676 条中约 92.7% 落入 `raw`，与含水量交叉验证（鲜食+中间态 75.4%）方向一致。

> `state_basis` 字段记录每条记录的判定依据（如 `name:bracket[干]`、`water<=15%`、`name:en_cooking`），可审计、可回溯。

### 并排浏览

```sql
-- 分类 × 来源 分布
SELECT * FROM v_by_cat;

-- 某分类下全部来源的并排
SELECT source, name, state, kcal_per100g, calcium_mg FROM v_browse WHERE canon_cat='vegetable';

-- 某食物的全部公制化数值
SELECT n.nut_cn, v.display_val, v.display_unit
FROM norm_value v JOIN norm_nutrient n USING (nut_key)
WHERE v.norm_food_id = ? AND v.value_si IS NOT NULL;
```

---

## 七、食物名称中文化（覆盖率 99.1%）

> 目标：把 **26,958 条**并排记录的原始名称（英文 / 法文 / 日文 / 印尼文 / 东盟多语混排）统一产出中文名，写回 `norm_food.name_cn`，使全库可用中文检索。

### 为什么不用机器翻译

实测过外部 MT 接口（MyMemory 等）直接逐条翻译，问题有三：

1. **术语失控**：`cheddar cheese` 被译成粤语「車打芝士」、`whole-wheat` 被切成「整个小麦」、`fat-free` 被切成「脂肪」+「免费」；
2. **速度**：2.1 万条逐条调用，按限速要跑数小时；
3. **不可复现**：同一词前后译法不一致，无法审计。

改用**受控词典**方案后，同样 2.1 万条只需**秒级**跑完，且每条译名可追溯到用到了哪些词条（`translate_unknown` 字段列出未收录词，便于迭代补词）。

### 词典方案的数据依据

对全部英文名称做 token 统计：

| 指标 | 数值 |
|------|------|
| 参与翻译的英文名条数 | 21,657 |
| 唯一 token 数 | **5,310** |
| TOP200 token 覆盖率 | 65.8% |
| TOP500 token 覆盖率 | 81.0% |
| TOP800 token 覆盖率 | 87.5% |
| TOP1200 token 覆盖率 | **91.9%** |

> 结论：词表长尾很陡——**给 5,310 个 token 一次性定译名，远优于逐条整句翻译**（效率约 40 倍）。实测整条名称能整体命中词典的只有 117/21,657 条，证明「词组词典」不可行，必须走 token 组装路线。

> 词表以 **7 批增量补齐**（每批统计「未收录高频词」再补）：`glossary_en.py` 主料词条已达 **1,574** 条。收益递减点出现在第 6–7 批（每批新增命中 <400 条），此后停止。

### 词典分类体系

`glossary_en.py`（英语）与 `glossary_id.py`（印尼语）各自按语义类别组织词条：

| 类别 | 含义 | 举例 |
|------|------|------|
| `MF` | 主料 | `beef`→牛肉、`salmon`→三文鱼、`rice`→大米 |
| `PB` | 部位补语 | `breast`→胸肉、`round`→后腿、`rib`→肋排 |
| `SF` | 后缀 | `flour`→粉、`powder`→粉 |
| `ST` | 状态 | `raw`→生、`cooked`→熟 |
| `CO` | 烹饪方式 | `grilled`→烤、`boiled`→水煮、`roasted`→烤 |
| `PR` | 加工保藏 | `canned`→罐头、`smoked`→熏制、`dried`→干 |
| `NU` | 含量宣称 | `low-fat`→低脂、`fat-free`→脱脂 |
| `CL` | 颜色 | `red`→红、`green`→绿 |
| `CN` | 国别/产地 | `italian`→意式、`chinese`→中式 |
| `PH` | 物理形态 | `sliced`→片、`whole`→全、`ground`→碎 |
| `QT` | 取料部位 | `boneless`→去骨、`skinless`→去皮 |
| `ZZ` | **占位屏蔽词** | `style`/`recipe`/`home`→ 空串（进词盆但不输出，避免误报未收录） |

### 语序与组装规则

- **语序权重**：`CLS_ORDER = {ST:1, CO:2, PR:3, NU:4, CL:5, CN:6, PH:7, QT:8}`，数值小的靠前；
- **同类择一**：`WORD_RANK` 决定 ST/CO 同类只保留最具体的一个（`cooked, hard-boiled` → 只出「水煮」）；
- **最长短语优先**：全部词条 key 归一化（连字符→空格）后按长度降序拼成一个正则 alternation，**对整条名称做一次 `finditer`**——Python `re` 取最左成功分支，天然实现「最长匹配」，彻底消灭 `whole-wheat`→`whole`+`wheat`、`fat-free`→`fat`+`free` 的切分错误；
- **跨逗号扫描**（关键）：把各逗号段归一化后**拼成整串再单次扫描**，这样倒装短语（`egg whole`、`milk dry`、`prepared from recipe`）才能被命中；
- **with/without 配料解析**：`ING_SPLIT` 按 `with/without/plus/topped with/stuffed with/contains` 切分，输出「配XX」/「无XX」；
- **类属词让位**：head 若只是「汤/酱/汁」而后有具体主料，则具体主料升为核心、类属词退回末尾（`Soup, clam chowder` → 「蛤蜊巧达浓汤汤」）；
- **中文清理 `tidy_cn()`**：叠字去重、去空括号、去首尾标点；`_dedup_cn()` 处理「主料+部位」边界（`鸡`+`胸肉`→鸡胸肉，`鳕鱼`+`鱼`→鳕鱼）。

### 各语种通路

| 语种 | 处理 | 说明 |
|------|------|------|
| 英语 | `glossary_en.py` + 上述语序 | USDA / 英国 CoFID / 法国 CIQUAL（NFKD 变音折叠后复用英语表）/ 西非 WAFCT |
| 印尼语 | `glossary_id.py` **独立码表 + 结构反转** | 印尼语「主料在前、修饰在后」与英语相反，`IS_ID` 分支单独组装（状态前置→主料→部位紧贴→其余收尾）；独立码表避免 `daun`/`daging` 等同形词与英语互相污染 |
| 日语 | `clean_jp()` + `jp_localize()` | 去掉 `＜分類＞`、`（XX類）` 注解，再用约 500 条 `JP_KANJI` 假名→汉字表本地化（`えだまめ`→毛豆） |
| 东盟 | 名称抢救 | 原 `food_name` 被泰/越/马来语混排打乱，改用 `desc` 列解析（`fix_asean_names.py`），救回英文名后复用英语通路 |
| 中文 | `native` | 原文即中文，直接落库 |

### 覆盖率

| 来源 | 条数 | 已译 | 覆盖率 |
|------|-----:|-----:|-------:|
| 中国 CN | 1,677 | 1,677 | 100% |
| 法国 FR | 3,484 | 3,484 | 100% |
| 英国 UK | 2,886 | 2,885 | 100% |
| USDA | 13,694 | 13,671 | 99.8% |
| 日本 JP | 2,478 | 2,473 | 99.8% |
| 西非 WAFCT | 1,028 | 1,026 | 99.8% |
| 印尼 ID | 1,146 | 1,065 | 92.9% |
| 东盟 ASEAN | 565 | 430 | 76.1% |
| **合计** | **26,958** | **26,711** | **99.1%** |

> `translate_status` 四态：`ok` 全词命中（15,891 / 58.9%）、`partial` 有未收录词但主体可译（6,670 / 24.7%）、`native` 原文即中文（4,150 / 15.4%）、`untranslated`（247 / 0.9%）。
>
> 剩余未译几乎全部来自 **ASEAN（135）/ 印尼（81）**——其名称被泰/越/马来语与语言码（如 `TH) AAC`）打乱，属数据源本身的名称残缺，无法靠词典救回。USDA/日/英/法 的未译均 <15 条。

### 质量抽样

```
生绞碎牛肉                             <- Beef, ground, regular, raw
市售全麦面包                           <- Bread, whole-wheat, commercially prepared
水煮熟全蛋                             <- Egg, whole, cooked, hard-boiled
罐头西柚（分瓣、果汁浸、固形物与汤汁） <- Grapefruit, sections, canned, juice pack, solids and liquids
生鲜苋菜                               <- Bayam, segar            (印尼)
毛豆冷冻                               <- えだまめ　冷凍           (日本)
```

---

## 查询示例

命令行（无需写 SQL）：

```bash
python3 query.py cnsearch 苹果            # 搜中文食物
python3 query.py cnnutrients 061101x      # 某食物的全部成分
python3 query.py gi 米饭                  # 中国食物 GL/GI
python3 query.py gi --group 水果
python3 query.py dri --nutrient 铁 --verified
python3 query.py dri --nutrient 维生素A --age 18岁~
python3 query.py search "apple"           # 搜 USDA
python3 query.py nutrients 1103865
python3 query.py ciqual cheese            # 法国 CIQUAL
python3 query.py cofid cheddar            # 英国 CoFID
python3 query.py mext 米                  # 日本 MEXT
python3 query.py wafct millet             # FAO 西非表
python3 query.py tkpi AP0                 # 印尼 TKPI
python3 query.py asean rice               # 东盟 ASEAN FCD
python3 query.py tables                   # 列出所有表及行数
```

并排浏览层（**不合并**，按分类 + 名字排列，数值统一公制）：

```bash
python3 query.py bycat                        # 分类分段 × 来源 分布矩阵
python3 query.py browse --cat 水产            # 某分类下全部来源
python3 query.py browse --cat 乳蛋类 --source CN   # 指定来源
python3 query.py browse --name 三文鱼          # 按中文名浏览（跨全库）
python3 query.py browse --name rice --state raw    # 带状态过滤
python3 query.py side 牛肉                     # 关键词跨来源并排对照（支持中文）
python3 query.py side Apple                   # 也支持英文原名
```

> `browse` / `side` 均可**按中文或原文检索**，输出同时给出「中文名」与「原名」两列。中文名由第七节的中文化流程生成（覆盖率 99.1%）。

SQL 示例：

```sql
-- 并排层：某分类下各来源的并排（不合并）
SELECT source, name, state, kcal_per100g, protein_g, calcium_mg
FROM v_browse WHERE canon_cat='fruit' ORDER BY source LIMIT 20;

-- 并排层：某食物的全部公制化数值
SELECT n.nut_cn, v.display_val, v.display_unit, v.raw_value, v.raw_unit
FROM norm_value v JOIN norm_nutrient n USING (nut_key)
JOIN norm_food f USING (norm_food_id)
WHERE f.source='CN' AND f.name_local LIKE '%苹果%' AND v.value_si IS NOT NULL;

-- 并排层：按中文名跨来源检索（走 idx_nf_cn 索引）
SELECT source, name_cn, name_local, state, kcal, protein, fat, carb
FROM norm_food WHERE name_cn LIKE '%三文鱼%' ORDER BY source;

-- 并排层：查看各来源中文化进度
SELECT source,
       count(*) AS 总数,
       sum(name_cn IS NOT NULL) AS 已译,
       round(100.0*sum(name_cn IS NOT NULL)/count(*), 1) AS 覆盖率
FROM norm_food GROUP BY source ORDER BY 总数 DESC;

-- 并排层：找出仍有未收录词的记录（便于补词表）
SELECT source, name_en, translate_unknown FROM norm_food
WHERE translate_status='partial' AND translate_unknown IS NOT NULL LIMIT 30;

-- 中文食物：按能量排序的谷类
SELECT foodName, englishName, energyKCal, protein
FROM china_food_composition
WHERE category LIKE '谷类%' ORDER BY energyKCal DESC LIMIT 10;

-- 高钙食物 Top10
SELECT foodName, Ca FROM china_food_composition
WHERE Ca IS NOT NULL ORDER BY Ca DESC LIMIT 10;

-- 2023版：18岁以上成人的铁参考摄入量
SELECT sex, dri_type, value FROM china_dri_2023
WHERE nutrient_cn='铁' AND age_group='18岁~';

-- 2023版：只看已核实数据
SELECT * FROM china_dri_2023 WHERE verified=1;

-- USDA：维生素C 高于 50mg 的食品（导入后可用）
SELECT f.description, fn.amount, n.unit_name
FROM food_nutrient fn
JOIN food f ON f.fdc_id = fn.fdc_id
JOIN nutrient n ON n.id = fn.nutrient_id
WHERE n.name LIKE '%Vitamin C%' AND fn.amount > 50
ORDER BY fn.amount DESC LIMIT 50;
```

---

## 文件清单

```
/workspace/fdc/
├── nutrition.db                    ★ 整合库（SQLite，约 4.4 GB，3610 万行）
├── china/
│   ├── food_composition_full.csv   中国食物成分表原始数据
│   ├── dri_2023.csv                DRIs 2023 纯文本副本
│   └── glycemic_index_of_foods.json  GI 附录原始数据
├── intl/                           国际库原始 Excel（法/英/日/FAO 西非）
├── intl_sea/                       东南亚数据（印尼 TKPI CSV + 名称表 / 东盟 FCD PDF+CSV）
├── usda/                           已解压的 USDA 完整 CSV 包（3.1 GB）
├── parts_full/                     USDA 分片下载临时文件（可删）
├── FoodData_Central_csv_2026-04-30.zip  USDA 完整包（481,517,495 字节）
├── pdl_full.sh                     16 路分片并发下载器
├── dl.sh                           单连接断点续传下载器
├── build_db.py                     USDA CSV → SQLite（追加模式）
├── build_cn.py                     中国食物成分表 + DRIs → SQLite
├── build_intl.py                   国际库（法/英/日/西非）→ SQLite
├── build_sea.py                    东南亚（印尼/东盟）→ SQLite
├── build_gi.py                     中国食物 GI 附录 → SQLite（含名称匹配）
├── parse_asean.py                  东盟 FCD PDF 坐标法解析
├── build_norm.py                   并排层：8 来源食物归一化（分类 + 状态 + 名称）
├── build_norm_values.py            并排层：公制化数值长表 + 浏览视图
├── glossary_en.py                  ★ 英语词表（12 类，4 批增量补齐至收益递减点）
├── glossary_id.py                  ★ 印尼语词表（独立通路，结构反转组装）
├── translate_names.py              ★ 中文化引擎（单次正则全词盆匹配 + 语序组装）
├── fix_asean_names.py              东盟名称抢救（从 desc 列救回英文名）
├── query.py                        命令行查询助手
├── CROSS_DB_PLAN.md                跨库比对：实测数据与设计决策记录
└── README.md
```

## 免责与溯源

- USDA 数据为美国农业部公共领域数据。
- 中国食物成分表、GI 附录与 2023 版 DRIs 为公开出版物内容；本库仅做结构化整理，
  **数值未作修改**，但受获取渠道限制，部分 DRIs 数值未经原书逐项核验（`verified` 字段已标明）。
  GI 附录来自开源项目结构化整理，已做名称匹配但与成分表编码的对应关系仅供参考。
  用于临床、科研或生产决策前，请以《中国食物成分表（标准版第6版）》和
  《中国居民膳食营养素参考摄入量（2023版）》原书为准。
- 法国 CIQUAL、英国 CoFID、日本 MEXT、印尼 TKPI、东盟 FCD 均为各自机构公开发布的数据。

---
