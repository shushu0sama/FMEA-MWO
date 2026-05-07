# CLAUDE.md - FMEA-MWO 项目记忆文件

## 项目概述

本项目源自 IEEE Access 论文 "Generating Authentic Grounded Synthetic Maintenance Work Orders"，从知识图谱（Neo4j）+ LLM 生成合成维护工单（MWO）。

### 当前状态

- **LLM 模型**: DeepSeek V4 Flash (`deepseek-chat`)，通过 OpenAI SDK 调用
- **Neo4j 数据库**: 本地运行 (bolt://localhost:7687)，包含中文 FMEA 数据（1 个系统/878 节点）
- **Python 虚拟环境**: `venv/`（Python 3.13.9）
- **API Key**: 在 `.env` 文件中（`.gitignore` 已排除）
- **远程仓库**: https://github.com/shushu0sama/FMEA-MWO.git

## 核心改造（已完成）

### 1. 模型迁移
- GPT-4o mini → DeepSeek V4 Flash (`deepseek-chat`)
- API 端点: `https://api.deepseek.com`
- `deepseek-v4-pro` 无法使用（返回空响应），V4 Flash 稳定

### 2. 外网访问
- 用户使用 Clash VPN 代理，系统级代理已配置
- GitHub 可直接访问，HuggingFace 不通，nbsdc.cn 需高校认证

### 3. 中文适配（三阶段改造）
- **PathExtraction**: 新增 6 个中文 Cypher 查询，支持双 Schema（maintie/fmea）
- **Generate**: 中文 Prompt/Few-shot/黑名单，通过 `--cn` 参数切换
- **Humanise**: 新建 `humanise_cn.py`，200+ 缩写 + 120+ 拼音混淆 + 30+ 字形混淆

### 4. 数据扩展
- 外部数据集: `data/external/` 目录（NHTSA/StingRAY/Zenodo）
- 最终产出: `_output/fmea_merged_final.xlsx`（1,074 行/52 系统）
- 原始数据 `data1014.xlsx` 未被修改

## 运行方式

```bash
# 激活虚拟环境
source venv/Scripts/activate

# 中文 MWO 生成管线（需 Neo4j 运行中）
cd Generate
python llm_generate.py --cn --samples 10

# 英文管线（原有，需 MaintIE JSON 路径文件）
python llm_generate.py
```

## 关键文件结构

```
LLM-KG-Synthetic-MWO/
├── PathExtraction/
│   ├── path_queries.py          # 英文 + 中文 Cypher 查询（已修改）
│   └── maintie_to_kg.py         # MaintIE 数据导入（未修改）
├── Generate/
│   ├── llm_generate.py          # 中英文双模式生成（已修改）
│   ├── llm_prompt.py            # Prompt 变体 + 中文 prompt（已修改）
│   └── fewshot_messages/
│       ├── fewshot_generate.csv  # 英文 few-shot（未修改）
│       └── fewshot_cn.csv        # 中文 few-shot（新增）
├── Humanise/
│   ├── humanise.py              # 英文人性化（未修改）
│   └── humanise_cn.py           # 中文人性化（新增）
├── data/external/
│   └── _output/
│       └── fmea_merged_final.xlsx  # 最终扩展数据
├── .env                          # API Key + Neo4j 配置（gitignore）
├── .gitignore
├── 项目改造完整工作报告.md
├── 中文适配方案_RALPH.md
└── 数据处理工作报告.md
```

## 已知问题

1. `deepseek-v4-pro` 返回空响应，目前用 `deepseek-chat`（V4 Flash）
2. HuggingFace 连不上（代理不支持该域名）
3. Neo4j 中仅 1 个系统数据，fmea_merged_final.xlsx 未导入
4. Humanise 中文词典覆盖范围需扩充
5. NhTSA 完整数据（1.56GB）在 `.gitignore` 中排除，本地在 `data/external/nhtsa_complaints.zip`
