# Agent：工具调用 / 多轮记忆 / 规划评测

> 这一层给问答助手装上"手"：除了查政策库，还能查校历、抓网页；一次会话内记住上文；并且有一个可复现的评测集来量化"工具选得对不对"。

## 1. 做了什么

| 模块 | 位置 | 作用 |
|---|---|---|
| 工具注册表 | `tools/registry.py` | 工具声明（JSON Schema 子集）+ 参数校验 + 统一错误码 |
| 政策检索工具 | `tools/policy_search.py` | 包装已有 RAG 服务，返回答案 + 出处 |
| 校历工具 | `tools/calendar.py` | 教学周、假期、下一个时间节点（读 `data/calendar/semester.json`） |
| 网页抓取工具 | `tools/web_fetch.py` | 抓一个 URL、抽正文（拒绝内网地址、限超时/字节） |
| 规划器 | `agent/planner.py` | 选工具 + 填参数（默认规则版，可选大模型） |
| 多轮记忆 | `agent/memory.py` | 按 session_id 存最近 20 轮 |
| 执行循环 | `agent/loop.py` | 规划 → 调工具 → 组织答案 → 写记忆 |
| 接口 | `api/routes_agent.py` | `GET /agent/tools`、`POST /agent/chat` |
| 评测 | `eval/agent_eval.py` + `data/agent_eval/questions.jsonl` | 20 条标注题，算工具选择准确率 |

## 2. 为什么默认用规则规划，而不是大模型 function calling

- 这台机器**没有配置 LLM API Key**（`src/llm.py` 里 `is_configured()` 为假），上大模型规划就只能"写代码但跑不出数"，违背"不许编造数字"的约束；
- 规则版**完全可复现**：同一句话永远选同一个工具，才能写出稳定通过的接口测试与评测集；
- 大模型路径没有删：`agent/planner.py` 里 `_llm_plan()` 在检测到 `LLM_API_KEY` 时会先让模型输出 `{"tool":..,"args":..}`，解析失败/工具不存在就自动回落到规则。**这条路径在本机未实测（没有 Key）**，所以 README 里不写它的准确率。

## 3. 三个工具

| 工具 | 必填参数 | 可选参数 | 返回要点 | 主要错误码 |
|---|---|---|---|---|
| `policy_search` | `question` | `top_k` 1~10 | `answer`、`contexts[]`（doc_id/title/snippet/score）、`n_contexts` | `INDEX_NOT_READY` 503 |
| `calendar` | — | `date`（YYYY-MM-DD，缺省今天） | 教学周、是否在学期/假期、当前事件、下一个节点及天数 | `CALENDAR_NOT_READY` 503、`INVALID_TOOL_ARGS` 422 |
| `web_fetch` | `url` | `max_chars` 200~4000 | `title`、`text`（去标签）、`status`、`bytes`、`truncated` | `FORBIDDEN_URL` 400、`FETCH_FAILED` 502 |

注册表用 7 个校验点卡参数：类型、必填、数值范围、字符串长度、正则、枚举、未知字段（`additionalProperties: false`）。校验失败一律 `INVALID_TOOL_ARGS`，工具内部异常收敛成 `TOOL_EXEC_FAILED`，不会把栈抛给调用方。

## 4. 规划规则（可解释）

1. 消息里有 `http(s)://` 链接 → `web_fetch`；
2. 否则按各工具的关键词表计数，得分最高者胜（政策词 60+ 个，校历词 20+ 个）；
3. 一个都没命中 → 回落 `policy_search`（知识库是主业务）；
4. 日期用正则 `YYYY-MM-DD` 抽出来塞给 `calendar` 的 `date` 参数。

规则全部写在代码里，`POST /agent/chat` 的响应用 `reason` 字段说明这次为什么选它，方便答辩时被追问"你怎么知道该调哪个工具"。

## 5. 多轮记忆

`SessionMemory` 按 `session_id` 存最近 20 轮（user/assistant 成对），带线程锁；同一 `session_id` 的追问会命中同一会话，最近 2 轮文本会拼进规划提示（规则版暂不依赖它，但大模型路径会用）。

边界说清楚：**进程内内存**，重启即丢；多副本部署要换 Redis，这里没做。

## 6. 接口

```bash
curl -s http://127.0.0.1:8000/agent/tools
curl -s -X POST http://127.0.0.1:8000/agent/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"看看 https://www.moe.gov.cn/ 首页","session_id":"demo-web"}'
```

本机实测（uvicorn 单进程，2026-11-27）：

| 消息 | 选中工具 | 结果 |
|---|---|---|
| 国家励志奖学金一年多少钱？ | policy_search | 200，5 条切片，4.9 ms，citations 5 条 |
| 今天第几教学周了 | calendar | 200，"2026-11-27（周五）；第 12 教学周；下一个节点「元旦」还有 35 天" |
| 看看 https://www.moe.gov.cn/ 首页 | web_fetch | 200，HTTP 200、101632 B、104.6 ms，抽到标题《中华人民共和国教育部政府门户网站》 |
| http://127.0.0.1:8000/health | web_fetch | 工具返回 `FORBIDDEN_URL`（拒绝内网地址），HTTP 仍是 200，错误在 `tool_calls[0].error` |

## 7. 评测：工具选择准确率

```bash
python eval/agent_eval.py                                   # 只测规划层，离线
python eval/agent_eval.py --live --out reports/agent_eval.json   # 真调工具
```

20 条标注题（政策 10 / 校历 7 / 网页 3），本机实测：

| 指标 | 值 | 说明 |
|---|---|---|
| 工具选择准确率 | **20/20 = 100%** | 规划层，与是否联网无关 |
| 真实执行成功 | 17/20 = 85% | 3 条网页用例用的 `example.edu.cn` 域名不存在，如实记 `FETCH_FAILED` |
| 政策题引用覆盖率 | 10/10 = 100% | 每条 policy 答案都带 citations |
| 端到端延迟 | P50 3.9 ms / P95 17.5 ms | 本机回环，校历与政策都是毫秒级 |

**必须说清楚的偏差**：这 20 条用例和关键词表是同一轮写的，规划层 100% 属于"自己出的卷子自己考"，不能当成泛化能力。真正能说明问题的只有两件事：① 规则对三类意图的边界是清晰的（带链接、带日期、带政策术语）；② 每加一个工具只要补一组关键词 + 用例，回归成本很低。换真实用户问法后准确率一定会掉，掉多少要用真实日志重测。

## 8. 局限与下一步

- 规划靠关键词，遇到"奖学金什么时候到账"这种既像校历又像资助的问法会走知识库——目前这是可接受的默认；
- 工具选择评测集只有 20 条且与规则同源，需要真实问法扩充（下一步：从接口日志里采样）；
- `web_fetch` 只抓单页、不执行 JS，通知列表页需要再做一层链接抽取；
- 记忆在进程内，多副本需要 Redis；
- 大模型规划路径（`_llm_plan`）**未实测**，配好 `LLM_API_KEY` 后应先跑一遍这 20 条再上线。
