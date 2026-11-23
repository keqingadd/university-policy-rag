# 高校学生政策问答助手（RAG）

> 把《学生管理规定》《资助政策》等权威文件变成"能回答、能溯源"的问答助手：**标题感知切片 → BM25 + 向量混合检索（RRF）→ 查询改写 → 大模型带引用生成**，附检索评测脚本、单元测试和 Streamlit 演示界面。

![python](https://img.shields.io/badge/Python-3.10%2B-blue) ![deps](https://img.shields.io/badge/核心依赖-numpy-green) ![tests](https://img.shields.io/badge/tests-9%20passed-brightgreen)

---

## 1. 解决什么问题

学生问"评贫困生多久一次""勤工助学一个月能打多少小时工"，答案散在教育部规章、省教育厅办法和学校通知里：全文搜索找不到、翻文档太慢；直接问通用大模型，它不知道本校/本省政策，还会编。

本项目把**真实公开政策文件**做成可溯源的知识库问答：
- 回答必须来自检索到的原文，并标注引用编号（[1][2]）；
- 资料不足时明确说"无法确定"，而不是编造；
- 用户口语化提问时用**查询改写**把口语映射成政策术语；
- 检索效果有**可量化评测**（Hit@k / MRR）。

## 2. 语料（全部为公开政策原文）

| 文档 | 来源 |
|---|---|
| 普通高等学校学生管理规定（教育部令第41号） | 教育部官网 |
| 安徽省家庭经济困难学生认定工作实施办法 | 安徽省教育厅等六部门（皖教〔2019〕2号） |
| 高校学生资助政策 14 项（国奖/励志/助学金/贷款/勤工助学等） | 教育部资助热线政策解读（政府网转载） |
| 本专科生国家奖学金评审办法 | 教育部、财政部（教财函〔2019〕105号） |
| 高等学校勤工助学管理办法（2018 年修订） | 教育部、财政部（教财〔2018〕12号） |
| 教育部等四部门关于调整完善助学贷款有关政策的通知 | 教财〔2023〕4号 |

> 政策会更新，README 与评测只代表抓取时的公开文本；实际办理以最新文件为准。这也是"引用溯源"存在的意义。

## 3. 架构

`@mermaid
flowchart LR
    A[政策原文 .md] --> B[标题感知切片<br/>500 字 / 重叠 80]
    B --> C1[BM25 关键词索引]
    B --> C2[向量索引<br/>哈希向量 / 可换 API embedding]
    Q[用户提问] --> R[查询改写<br/>口语→政策术语]
    R --> C1
    R --> C2
    C1 --> D[RRF 混合排序]
    C2 --> D
    D --> E[Top-k 上下文 + 引用编号]
    E --> F[大模型生成<br/>只依据资料 · 标注引用]
    F --> G[CLI / Streamlit 界面]
`@

关键设计：
- **标题感知切片**：按 Markdown 标题切段，长段再按句子切并保留标题前缀，避免"公示 5 个工作日"这种关键句被切散。
- **混合检索**：BM25 保精确关键词（"10 日""LPR""5 个工作日"），向量兜语义，RRF 融合两路排名。
- **查询改写**：维护领域同义词表（"评贫困生"→"家庭经济困难学生认定"、"国奖"→"国家奖学金"），解决口语与公文用词不一致。
- **零依赖可复现**：字符 n-gram 哈希向量 + 纯 Python BM25，不装 torch 也能跑；`RAG_EMBEDDER=api` 可切真实 embedding。
- **可插拔生成**：任何 OpenAI 兼容接口都能接；没配 Key 自动降级为抽取式回答，保证 demo 永远能演示。

## 4. 目录结构

`@text
rag-kb-demo/
├─ app.py                     # Streamlit 演示界面
├─ src/
│  ├─ text.py                 # 中英混合分词、标题感知切片
│  ├─ embedder.py             # 哈希向量（零依赖）/ API embedding
│  ├─ index.py                # BM25 + 向量 + RRF 混合检索、索引持久化
│  ├─ query.py                # 查询改写（口语 → 政策术语同义词表）
│  ├─ llm.py                  # OpenAI 兼容对话接口（urllib，零依赖）
│  ├─ pipeline.py             # RAG 主流程（检索→上下文→生成/降级）
│  └─ evaluate.py             # Hit@k / MRR 评测
├─ scripts/
│  ├─ build_index.py
│  ├─ ask.py
│  ├─ evaluate.py
│  ├─ fetch_policy.py         # 抓取公开政策网页 → Markdown（复现语料）
│  └─ clean_docs.py           # 去掉网页导航噪音
├─ data/
│  ├─ docs/                   # 6 份政策原文
│  ├─ eval/                   # 关键词 10 题 + 口语化 6 题，标注 gold_doc
│  └─ index/                  # 构建产物（已 gitignore）
├─ tests/test_pipeline.py     # 9 个单元测试
└─ docs/                      # 演示脚本、答辩问答
`@

## 5. 快速开始

要求 Python 3.10+，核心只依赖 numpy。

`@bash
python -m pip install -r requirements.txt
python scripts/build_index.py
python scripts/ask.py "家庭经济困难学生认定多久评一次？"
python scripts/evaluate.py --mode hybrid
python -m pip install streamlit && streamlit run app.py
`@

接大模型（可选）：设置 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`（见 `.env.example`）。

## 6. 评测结果

评测方法：10 题关键词问法 + 6 题口语化问法，每题标注 `gold_doc`（正确来源文档），统计检索结果中 gold 文档的名次，计算 Hit@k 与 MRR。

| 问法 | 检索模式 | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---|---|---|---|
| 关键词（10 题） | BM25 | 90.0% | 100% | 100% | 0.950 |
| 关键词（10 题） | 向量 | 90.0% | 90.0% | 100% | 0.925 |
| 关键词（10 题） | **混合（默认）** | **90.0%** | 100% | 100% | **0.933** |
| 口语化（6 题） | BM25 | 83.3% | 100% | 100% | 0.889 |
| 口语化（6 题） | 向量 | 50.0% | 100% | 100% | 0.750 |
| 口语化（6 题） | **混合（默认）** | **100%** | 100% | 100% | **1.000** |

**消融：查询改写的作用**（同一套口语化题目，混合检索）：

| 版本 | Hit@1 | Hit@5 | MRR |
|---|---|---|---|
| 无查询改写 | 66.7% | 83.3% | 0.708 |
| **加查询改写** | **100%** | **100%** | **1.000** |

结论：
- 关键词问法本身已很强（BM25 Hit@1 90%），说明政策文本里精确字段多；
- 口语化问法上，单路向量掉到 50% Hit@1，混合检索靠 BM25 兜住；
- 真正的短板是"用词差异"，**查询改写把口语化 Hit@1 从 66.7% 提到 100%**，这是本项目的核心改进。

复现：`python scripts/evaluate.py --mode hybrid` 与 `--questions data/eval/paraphrase.jsonl`。

## 7. 设计决策（答辩时会被问）

1. **为什么切片 500 字、重叠 80？** 规章/办法的"条"通常 100-400 字，500 字能装下完整条款；重叠 80 字防止答案跨块被截断。
2. **为什么 BM25 + 向量混合？** 政策文本有大量精确字段（10 日、5 个工作日、LPR 减 60 个基点、16000 元），纯向量对这类精确匹配明显更弱（口语化 Hit@1 仅 50%）；RRF 融合不需要调权重。
3. **为什么做查询改写？** 用户说的是口语（"评贫困生""国奖"），原文是公文（"家庭经济困难学生认定""国家奖学金"）。同义词表可维护、可解释、零训练成本，比直接上大模型改写更可控。
4. **怎么控制幻觉？** 提示词限定"只能依据资料、必须标引用、资料不足就说无法确定"；无 Key 时降级抽取式；后续加引用校验。
5. **数据会不会过期？** 会。政策是抓取时点的公开文本，所以产品上要支持"文档版本 + 引用溯源 + 更新提示"，这也是下一步。

## 8. 简历怎么写

> **高校学生政策问答助手（RAG）**（个人项目，2026.11）
> - 独立实现政策文档问答：标题感知切片 + BM25/向量混合检索（RRF）+ 查询改写（口语→政策术语）+ 大模型带引用生成。
> - 抓取并清洗 6 份公开政策文件（教育部规章、安徽省认定办法、资助政策等），自建 16 题标注评测集。
> - 关键词问法 Hit@1 90%/MRR 0.93、Hit@3 100%；查询改写使口语化问法 Hit@1 从 66.7% 提升到 100%、MRR 0.71→1.00（6 题小样本，存在过拟合可能）。
> - 工程化：索引持久化、CLI + Streamlit 双入口、9 个单元测试、无 API Key 自动降级抽取式回答。

English bullet：

> Built a retrieval-augmented QA assistant over public university policies: heading-aware chunking, hybrid BM25 + vector retrieval with RRF, query rewriting (colloquial → policy terminology), and citation-grounded LLM generation. Created a 16-question labeled eval set; query rewriting lifted Hit@1 on colloquial queries from 66.7% to 100% (MRR 0.71→1.00). Shipped CLI + Streamlit demo, index persistence, and 9 unit tests.

## 9. 演示与答辩材料

- `docs/演示脚本.md`：3 分钟现场演示逐句稿
- `docs/答辩问答.md`：高频追问与参考答案

## 10. 改进路线图

- [ ] Cross-encoder rerank（bge-reranker）提升 Top-3 精度
- [ ] 用大模型做查询改写，与同义词表做 A/B
- [ ] 引用校验：答案中的 [n] 必须能在上下文找到
- [ ] 文档版本管理 + 政策更新时间提示
- [ ] Docker 化、缓存与流式输出

## 11. 许可

仅用于学习与赛事展示；政策文本版权归原发布机构，引用时请注明来源。