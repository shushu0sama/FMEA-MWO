# RALPH 文档：FMEA-MWO 项目中文适配方案

> 版本: v1.0
> 日期: 2026-05-07
> 状态: 待审核

---

## 一、背景与目标

### 1.1 项目背景

本项目源自 IEEE Access 论文 "Generating Authentic Grounded Synthetic Maintenance Work Orders (MWOs)"，原始管线为：

```
MaintIE 英文 KG (Neo4j) → Cypher 路径提取 → GPT-4o mini 生成 → 英文规则人性化 → 英文 MWO
```

当前已完成两项前置工作：
1. 将 LLM 从 GPT-4o mini 迁移至 DeepSeek V4 (deepseek-chat)
2. 将 Neo4j 知识图谱从 MaintIE 英文 Schema 扩展为中文 FMEA Schema（52 系统/1,074 行）

### 1.2 适配目标

将项目从**英文 MWO 生成系统**改造为**中文维保工单生成系统**，使整条管线在中文环境下产出质量对等的合成数据。

### 1.3 适配性测试结论

已完成无损测试（未修改任何代码，仅调用现有模块观察输出），结论如下：

| 模块 | 兼容度 | 核心问题 |
|---|---|---|
| **PathExtraction** | 0% | Cypher 查询硬编码 MaintIE 英文标签（PhysicalObject/UndesirableEvent），中文 KG 使用完全不同 Schema（故障模式/故障起因/关注要素层次） |
| **Generate** | 30% | DeepSeek API 可输出中文，但 prompt 模板、few-shot 示例、黑名单词全部为英文设计，生成结果仅是实体名拼凑，缺乏多样性和自然度 |
| **Humanise** | 0% | 三个子模块全部依赖英语语言学特征：缩写（is not→isn't）、术语替换（service→svce）、键盘错字（QWERTY）、同音词（CMU 发音词典）。中文文本通过后零变化 |

### 1.4 不做的事

- 不修改 Neo4j 数据库结构（当前 FMEA Schema 已足够）
- 不修改 LLM API 层（DeepSeek V4 Flash 已稳定可用）
- 不修改评估模块（Turing Test 等需中文母语评估者，不属于工程改造范畴）
- 不删除原有英文功能（通过配置开关保留兼容性）

---

## 二、改造架构

```
                           改造边界
  ┌──────────┐    ╔══════════════════════════════╗    ┌──────────┐
  │ Neo4j    │───→║  Phase 1: PathExtraction    ║───→│          │
  │ 中文 KG  │    ║  重写 Cypher 查询            ║    │          │
  └──────────┘    ╚══════════════════════════════╝    │          │
                                                      │ Generate │
  ┌──────────┐    ╔══════════════════════════════╗    │  (部分   │
  │ DeepSeek │───→║  Phase 2: Generate 中文化    ║───→│  重写)   │
  │ V4 Flash │    ║  Prompt + Few-shot + 黑名单   ║    │          │
  └──────────┘    ╚══════════════════════════════╝    │          │
                                                      │          │
  ┌──────────┐    ╔══════════════════════════════╗    │          │
  │ 中文词典 │───→║  Phase 3: Humanise 中文重建  ║───→│          │
  │ (新建)   │    ║  拼音/字形/缩写/行业黑话     ║    └──────────┘
  └──────────┘    ╚══════════════════════════════╝         │
                                                          ↓
                                                   中文 MWO
```

---

## 三、Phase 1: PathExtraction 中文路径查询

### 3.1 现状

`path_queries.py` 定义了 4 个 direct_queries + 5 个 complex_queries，全部使用 MaintIE 标签：

```python
# 原始查询示例（完全不可用于中文 KG）
{"query": "MATCH (o:PhysicalObject)-[:hasProperty]->(p:Property)-[:hasState]->(e:UndesirableEvent) RETURN ...",
 "outfile": "object_property_state_paths"}
```

中文 KG 中对应标签不存在，所有查询返回 0 结果。

### 3.2 中文 KG Schema 分析

| 节点标签 | 数量 | 语义 |
|---|---|---|
| 关注要素层次 | 15 | 系统/子系统（类比 MaintIE 的更高层概念） |
| 故障模式 | 120 | 故障模式（类比 UndesirableEvent） |
| 故障起因 | 337 | 故障原因（MaintIE 无直接对应） |
| 故障影响 | 46 | 故障后果 |
| 下一低分析层次 | 111 | 组件/部件（类比 PhysicalObject 的子层级） |
| 功能 | 23 | 系统功能 |
| 预防控制措施 | 100 | 预防措施 |
| 探测控制措施 | 58 | 检测措施 |

| 关系类型 | 数量 | 语义 |
|---|---|---|
| 故障模式 | 422 | 系统 → 故障模式 |
| 故障起因 | 413 | 故障模式 → 故障起因 |
| 故障影响 | 135 | 故障模式 → 故障影响 |
| 预防控制措施 | 273 | 故障模式 → 预防措施 |
| 探测措施 | 168 | 故障模式 → 探测措施 |
| 下一低分析层次 | 111 | 系统 → 组件 |

### 3.3 新增查询设计

在 `path_queries.py` 中新增一个查询组 `cn_queries`，与原有英文查询并存：

```python
# 新增中文查询
cn_queries = [
    # 直接路径：系统 → 故障模式 → 故障起因
    {
        "label": "系统-故障-起因 (直接)",
        "query": """
            MATCH (s:关注要素层次)-[:故障模式]->(m:故障模式)-[:故障起因]->(c:故障起因)
            RETURN s.name AS system, m.name AS failure_mode, c.name AS cause,
                   labels(s) AS system_labels, labels(m) AS mode_labels, labels(c) AS cause_labels
        """,
        "outfile": "cn_system_failure_cause",
        "path_type": "direct"
    },
    # 直接路径：故障模式 → 故障影响
    {
        "label": "故障-影响 (直接)",
        "query": """
            MATCH (m:故障模式)-[:故障影响]->(e:故障影响)
            RETURN m.name AS failure_mode, e.name AS effect
        """,
        "outfile": "cn_failure_effect",
        "path_type": "direct"
    },
    # 复杂路径：系统 → 故障 → 起因 + 影响 + 措施
    {
        "label": "系统-故障-全链路 (复杂)",
        "query": """
            MATCH (s:关注要素层次)-[:故障模式]->(m:故障模式)
            OPTIONAL MATCH (m)-[:故障起因]->(c:故障起因)
            OPTIONAL MATCH (m)-[:故障影响]->(e:故障影响)
            OPTIONAL MATCH (m)-[:预防控制措施]->(p:预防控制措施)
            OPTIONAL MATCH (m)-[:探测措施]->(d:探测控制措施)
            RETURN s.name AS system, m.name AS failure_mode,
                   c.name AS cause, e.name AS effect,
                   p.name AS prevention, d.name AS detection
        """,
        "outfile": "cn_full_chain",
        "path_type": "complex"
    },
    # 直接路径：系统 → 组件层次
    {
        "label": "系统-组件 (直接)",
        "query": """
            MATCH (s:关注要素层次)-[:下一低分析层次]->(c:下一低分析层次)
            OPTIONAL MATCH (c)-[:下一低层次功能]->(f:下一低层次功能)
            RETURN s.name AS system, c.name AS component, f.name AS function
        """,
        "outfile": "cn_system_component",
        "path_type": "direct"
    },
]
```

### 3.4 输出格式适配

中文查询的输出字段名与英文版不同，需要适配 `get_all_paths()` 函数的数据读取逻辑。

**方案**：在 `get_all_paths()` 中增加 `schema` 参数（`'maintie'` / `'fmea'`），根据 schema 选择不同的查询组和字段映射。

```python
def get_all_paths(schema='fmea', valid=True, label=False):
    if schema == 'maintie':
        queries = direct_queries + complex_queries
    else:
        queries = cn_queries

    paths_list = []
    # ... 读取逻辑相同，字段名根据 schema 自动适配

# 统一输出格式（与 downstream generate 对接）
# {
#     "object_name": "前舱主梁组件",       # 设备/组件名
#     "event_name": "主梁断裂",            # 故障事件名
#     "object_type": "关注要素层次",        # 来源标签
#     "valid": True
# }
```

### 3.5 工作量

| 任务 | 估计时间 |
|---|---|
| 新增 `cn_queries` 4-5 个 Cypher 查询 | 30 min |
| 修改 `get_all_paths()` 支持双 schema | 30 min |
| 字段映射逻辑（中文→统一格式） | 20 min |
| 本地测试验证 | 20 min |
| **合计** | **~1.5 h** |

---

## 四、Phase 2: Generate 中文生成管线

### 4.1 现状问题

测试中，现有英文 prompt 模板 + 中文实体输入，产生的结果是：
```
输入: 前舱主梁组件 + 主梁断裂
输出: 前舱主梁组件主梁断裂。  ← 只是拼凑了两个词
```

对比英文：
```
输入: fuel pump + leaking
输出: Fuel pump leaking, urgent repair needed.  ← 有动词、有语境
```

原因：
1. Few-shot 示例全是英文工单格式
2. "8 words max" 限制对中文太短（中文 8 字 ≈ 英文 3-4 词）
3. 黑名单词（"shows signs of", "detected"）是英文特有的冗词
4. Prompt 变体用英文改写，对中文生成无帮助

### 4.2 改造方案

#### 4.2.1 中文 Prompt 模板

```python
CN_BASE_PROMPTS = [
    "根据以下设备故障信息，生成一条中文维护工单记录。",
    "请用简洁的技术语言，描述下列设备故障的维修工单内容。",
    "你是一名维修工程师。为以下设备故障编写一条维护记录，使用行业术语。",
]

CN_LIMIT_WORDS = [
    "语言简洁，每句不超过 20 字。",
    "避免冗长表述，控制在 15-20 字以内。",
    "使用短句，每句不超过 20 个汉字。",
]

CN_LIMIT_COUNT = [
    "每条记录仅包含 1-2 句话。",
    "直接描述故障和处理，不添加额外解释。",
]

CN_BLACKLIST = [
    "发现", "检测到", "观察到", "显示", "需要关注",
    "需要进行", "建议", "可能存在", "疑似",
]
```

#### 4.2.2 中文 Few-shot 示例

从 `data1014.xlsx` 中提取 4-6 组高质量的"组件→故障模式→工单"示例：

```csv
设备,故障事件,工单样本1,工单样本2,工单样本3,工单样本4,工单样本5
前舱主梁组件,主梁断裂,前舱主梁横向拉伸断裂需更换,更换前舱主梁组件主梁已断,前舱主梁受力过大断裂待修,前舱主梁发现裂纹马上拆换,断裂主梁更换并检查相邻结构
燃油泵,泄漏,燃油泵密封失效燃油渗漏,更换燃油泵密封垫处理泄漏,燃油泵底部渗油需拆检,燃油泵O型圈老化泄漏更换,燃油泵连接管处渗油紧固处理
散热器,堵塞,散热器内部水垢堵塞清理,散热器芯体堵塞导致高温,清理散热器水道恢复冷却,散热器翅片积尘影响散热更换,散热器管路堵塞冲洗疏通
```

#### 4.2.3 中文 Prompt 变体

减少 LLM 调用（原版用 GPT 改写 prompt 增加多样性），中文版直接手写 5-6 个变体：

```python
def initialise_cn_prompts():
    """直接返回手工编写的中文 prompt 变体，避免 API 调用"""
    base_prompts = [
        "根据以下设备故障信息，生成一条中文维护工单记录。",
        "你是维修技师，用简洁专业的中文写一条维护工单。",
        "为以下设备和故障编写标准维护工单（中文，简练）。",
        "用技术性语言描述以下故障的维修处理（中文工单格式）。",
        "撰写一条中文维护记录，包含故障现象和处理方式。",
    ]

    limit_words = [
        "语言简洁，每句不超过 20 字。",
        "避免冗长，单条工单控制在 15-20 字。",
        "使用短句，不超过 20 个汉字。",
        "限制每条工单 20 字以内，直接描述。",
        "简洁明了，20 字以内。",
    ]

    limit_count = [
        "每条记录仅包含 1-2 句话。",
        "不添加解释，直接描述故障和处理。",
        "一条工单一句话足矣，无需分段。",
        "直接输出工单内容，不加其他说明。",
        "一条故障对应一条工单，不要列举多条。",
    ]

    return (base_prompts, limit_words, limit_count)
```

#### 4.2.4 修改生成函数

`generate_mwo()` 和 `generate_diverse_mwo()` 函数需增加 `lang` 参数：

```python
def generate_mwo(client, prompt_variations, path, lang='cn'):
    if lang == 'cn':
        prompt = get_cn_generate_prompt(prompt_variations, path['object_name'], path['event_name'])
        fewshot = get_cn_generate_fewshot()
    else:
        prompt = get_generate_prompt(prompt_variations, path['object_name'], path['event_name'])
        fewshot = get_generate_fewshot(prompt_variations)
    # ... 后续调用逻辑不变
```

### 4.3 工作量

| 任务 | 估计时间 |
|---|---|
| 编写中文 prompt 模板 (5×3 变体) | 15 min |
| 从 data1014.xlsx 提取 few-shot 示例 | 20 min |
| 构建中文黑名单 | 10 min |
| 修改 `llm_generate.py` 增加 lang 参数 | 30 min |
| 修改 `llm_prompt.py` 增加中文 prompt 函数 | 20 min |
| 测试 + 调优 | 30 min |
| **合计** | **~2 h** |

---

## 五、Phase 3: Humanise 中文人性化体系

### 5.1 现状问题

英文版 3 个子模块的中文表现：

| 子模块 | 英文机制 | 中文完全无效 |
|---|---|---|
| introduce_contractions | 词典 112 条：is not→isn't | 中文无形态变化 |
| introduce_abbreviations | 词典 564 条：service→svce | 全英文词典 |
| rule_introduce_typos | QWERTY 键盘 + CMU 发音词典 | 中文错字模式完全不同 |

### 5.2 中文人性化子模块设计

#### 5.2.1 中文工业缩写替换（≈ introduce_abbreviations）

替代英文缩写字典，构建中文工业场景的缩写词典：

```python
CN_ABBREVIATIONS = {
    # 中文→缩写/行业写法
    "发动机": ["发", "引擎"],
    "发电机": ["电发", "GEN"],
    "控制器": ["控", "控制器"],
    "散热器": ["散热", "散热片"],
    "液压泵": ["液泵", "HYD泵"],
    "变速箱": ["波箱", "变速"],
    "起落架": ["起架", "LG"],
    "制动系统": ["刹车系统", "制动系"],
    "燃油泵": ["油泵", "燃泵"],
    "传感器": ["探头", "sensor", "感应器"],
    "作动筒": ["作动", "缸"],
    "密封圈": ["O型圈", "密封环", "油封"],
    "过滤器": ["滤芯", "滤清器"],
    "主梁": ["大梁", "主桁"],
    "蒙皮": ["外壳", "皮"],
    "不工作": ["失效", "罢工", "不灵"],
    "更换": ["换", "更换掉", "替换"],
    "检查": ["查", "排查", "巡检"],
    "故障": ["毛病", "问题", "坏"],
    "需要": ["需", "得", "要"],
    # 中英混用（实际工单中常见）
    "空气压缩机": ["空压机", "air compressor"],
    "空调": ["A/C", "冷气"],
    "左": ["左", "L", "LH"],
    "右": ["右", "R", "RH"],
}
```

#### 5.2.2 中文拼写错误模拟（≈ rule_introduce_typos）

中文输入法导致的错字模式：

```python
# 拼音混淆矩阵（常见输入法错字）
CN_PINYIN_CONFUSION = {
    "主": ["柱", "住", "注"],
    "梁": ["粮", "凉", "亮", "粱"],
    "裂": ["烈", "列", "劣"],
    "封": ["风", "峰", "丰"],
    "泵": ["崩", "蹦"],
    "散": ["三", "伞"],
    "热": ["惹"],
    "器": ["气", "弃", "其"],
    "检": ["见", "建", "减"],
    "修": ["休", "秀"],
    "更": ["耕", "庚"],
    "换": ["环", "幻", "缓"],
    "油": ["由", "有", "游"],
    "漏": ["露", "楼"],
    "发": ["法", "罚"],
    "动": ["东", "洞"],
    "机": ["鸡", "积"],
    "故": ["古", "固"],
    "障": ["章", "涨"],
}

# 字形混淆矩阵
CN_SHAPE_CONFUSION = {
    "梁": ["粱"],
    "裂": ["烈"],
    "换": ["唤", "焕"],
    "泵": ["汞"],
    "器": ["嚣"],
    "封": ["卦"],
    "检": ["捡", "睑"],
    "修": ["脩"],
    "漏": ["陋"],
    "油": ["汕", "泔"],
}

# 误删/多加字符（输入法连打）
# "发动机不工作" → "发动机不工"（漏打最后一个字）
# "主梁断裂" → "主梁锻炼裂"（拼音联想误触）
```

**实现函数**：

```python
def cn_introduce_typos(sentence, chance=0.05, max_typos=3):
    """中文输入法错字模拟"""
    typo_funcs = [
        cn_replace_pinyin,      # 拼音混淆替换
        cn_replace_shape,       # 字形混淆替换
        cn_omit_char,           # 漏字（输入法漏打）
        cn_insert_char,         # 多字（拼音联想误触）
        cn_homophone,           # 同音字替换
    ]
    # 概率权重：拼音 40%，字形 15%，漏字 20%，多字 15%，同音 10%
    weights = [40, 15, 20, 15, 10]

    words = list(sentence)  # 中文按字符处理
    typos = random.sample(range(len(words)), min(len(words), max_typos))

    for i in typos:
        if random.random() < chance:
            func = random.choices(typo_funcs, weights=weights, k=1)[0]
            words[i] = func(words[i])

    return ''.join(words)
```

#### 5.2.3 中文数字/符号混用（新增）

英文版无此功能，中文工单中常见：

```python
def cn_number_mixing(sentence):
    """数字和符号混用"""
    # 全角→半角
    # 中文数字→阿拉伯数字混用
    mappings = {
        "一": "1", "二": "2", "三": "3",
        "第一": "#1", "第二": "#2",
        "百分之": "%",
        "摄氏度": "℃",
    }
    for cn, en in mappings.items():
        if random.random() < 0.1:  # 10% 概率
            sentence = sentence.replace(cn, en)
    return sentence
```

#### 5.2.4 中文 humanise_sentence 主函数

```python
def cn_humanise_sentence(sentence, use_llm=False):
    """中文 MWO 句子人性化"""
    # Step 1: 缩写/行业黑话替换（40% 概率）
    sentence = cn_introduce_abbreviations(sentence, chance=0.4)

    # Step 2: 符号混用（30% 概率）
    sentence = cn_number_mixing(sentence)

    # Step 3: 输入法错字（5% 概率，最多 3 个错字）
    if use_llm:
        sentence = llm_introduce_cn_typos(client, sentence)
    else:
        sentence = cn_introduce_typos(sentence, chance=0.05, max_typos=3)

    return sentence
```

### 5.3 词典构建策略

中文词典需要从真实数据中提取，两个来源：

| 来源 | 内容 | 获取方式 |
|---|---|---|
| **MaintNorm 中文版**（若有） | 中文维保工单中已标注的 lexical normalization 对照 | 直接解析类似 MaintNorm 的标注格式 |
| **人工整理** | 中文工业缩写、常见错字 | 参考中文维保/维修论坛的实际文本，整理 200-300 条 |
| **data1014.xlsx 中已有模式** | 从现有 354 条中文 FMEA 数据中提取已有的大小写/全半角混用模式 | 自动扫描 |

### 5.4 工作量

| 任务 | 估计时间 |
|---|---|
| 构建拼音混淆矩阵（150+ 条目） | 1 h |
| 构建字形混淆矩阵（50+ 条目） | 30 min |
| 构建中文工业缩写词典（200+ 条目） | 1.5 h |
| 实现 cn_introduce_typos 函数 | 1 h |
| 实现 cn_introduce_abbreviations 函数 | 30 min |
| 实现 cn_humanise_sentence 主函数 | 30 min |
| 测试 + 参数调优 | 1 h |
| **合计** | **~6 h** |

---

## 六、执行计划

### 6.1 阶段划分

```
Phase 1: PathExtraction 中文查询     [1.5 h]  ████░░░░░░░░░░░░░░░░  优先级: P0 (阻塞后续)
Phase 2: Generate 中文生成           [2.0 h]  █████░░░░░░░░░░░░░░░  优先级: P0 (核心功能)
Phase 3: Humanise 中文人性化         [6.0 h]  ███████████████░░░░░  优先级: P1 (增强质量)
─────────────────────────────────────────────────────────────────
Total:                                [9.5 h]  约 1-2 个工作日
```

### 6.2 文件变更清单

| 文件 | 变更类型 | 阶段 |
|---|---|---|
| `PathExtraction/path_queries.py` | 修改：新增 cn_queries | Phase 1 |
| `PathExtraction/path_matching.ipynb` | 修改：支持双 schema | Phase 1 |
| `Generate/llm_generate.py` | 修改：增加 lang 参数、中文 prompt 函数 | Phase 2 |
| `Generate/llm_prompt.py` | 修改：增加 `initialise_cn_prompts()` | Phase 2 |
| `Generate/fewshot_messages/fewshot_cn.csv` | **新建**：中文 few-shot 示例 | Phase 2 |
| `Humanise/humanise.py` | 修改：增加中文人性化函数 | Phase 3 |
| `Humanise/humanise_cn.py` | **新建**：中文人性化独立模块 | Phase 3 |
| `data/Corrections/cn_abbreviations.csv` | **新建**：中文缩写词典 | Phase 3 |
| `data/Corrections/cn_pinyin_confusion.csv` | **新建**：拼音混淆矩阵 | Phase 3 |
| `data/Corrections/cn_shape_confusion.csv` | **新建**：字形混淆矩阵 | Phase 3 |

### 6.3 验收标准

| 阶段 | 验收条件 |
|---|---|
| Phase 1 | 执行 `path_matching.ipynb`，产出包含中文路径的 JSON 文件，path 数量 > 200 |
| Phase 2 | 输入中文 device+failure，输出 5 条中文 MWO 句子，人工评估其中 ≥ 3 条自然可用 |
| Phase 3 | 同一输入多次运行，输出有差异（多样性和随机性），约 30-50% 的句子含至少 1 处"人性化"改动 |

---

## 七、风险与缓解

| 风险 | 概率 | 缓解措施 |
|---|---|---|
| 中文 KG 路径多样性不足（仅 1 个系统） | 高 | Phase 1 先跑通，后续用 fmea_merged_final.xlsx 导入更多系统 |
| 中文 few-shot 质量不够好 | 中 | 从 data1014.xlsx 中精选 6-8 组最佳示例 |
| 中文缩写/错字词典覆盖不全 | 高 | 首版 200+ 条即可上线，后续迭代补充；可让 LLM 辅助生成 |
| Phase 2+3 的修改破坏原有英文功能 | 低 | 通过 lang 参数切换，英文代码路径完全保留不变 |

---

## 八、附录

### A. 中文 KG 与 MaintIE KG 对比

| 维度 | MaintIE (英文) | FMEA (中文) |
|---|---|---|
| 节点标签数 | 8 (PhysicalObject, UndesirableEvent, ...) | 10 (故障模式, 故障起因, ...) |
| 关系类型数 | 9 | 9 |
| 总节点数 | ~10,000 | 878 |
| 核心路径 | PhysicalObject→Property→UndesirableEvent | 关注要素层次→故障模式→故障起因 |
| 路径深度 | 1-3 跳 | 1-2 跳 |
| 覆盖领域 | 通用工业维护 | 航空飞控（单一领域） |

### B. 已排除的改造项

- **Turing Test 评估**：需要中文母语评估者重新标注，属于数据采集工作，非代码改造
- **Ranking Test**：同上
- **路径图可视化**：原版用 matplotlib 绘制英文路径图，中文版可延后
- **Diversity experiment notebook**：原有实验 notebook 的改造属于衍生工作，不在核心管线改造范围
