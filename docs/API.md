# 接口文档

服务用 FastAPI 实现，启动后自带交互式文档：

- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

## 启动

```bash
python -m pip install -r requirements-api.txt
python scripts/build_index.py --docs data/docs --out data/index   # 首次需要
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `RAG_INDEX` | `data/index` | 索引目录，需含 index.json 与 embeddings.npy |
| `RAG_TOP_K` | `5` | 默认召回条数 |
| `RAG_MODE` | `hybrid` | 默认检索模式：hybrid / bm25 / vector |
| `RAG_MAX_QUESTION_CHARS` | `2000` | 问题长度上限，超过返回 QUESTION_TOO_LONG |
| `LOG_LEVEL` | `INFO` | 日志级别 |

## GET /health

探活接口，容器 HEALTHCHECK 与 CI 都依赖它。

```json
{
  "status": "ok",
  "chunks": 60,
  "embedder": "hash",
  "version": "0.1.0",
  "index_dir": "data/index",
  "detail": null
}
```

- 索引正常：`200`
- 索引未就绪：`503`，`status="degraded"`，`detail` 说明原因

## POST /query

请求体：

```json
{
  "question": "国家励志奖学金的申请条件是什么？",
  "top_k": 5,
  "mode": "hybrid"
}
```

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| question | string | 是 | 去空白后非空，长度 ≤ 2000 |
| top_k | int | 否 | 1..10，默认取 RAG_TOP_K |
| mode | string | 否 | hybrid / bm25 / vector，默认取 RAG_MODE |

响应体（200）：

```json
{
  "question": "国家励志奖学金的申请条件是什么？",
  "answer": "……",
  "contexts": [
    {"id": "…", "doc_id": "…", "title": "…", "chunk_index": 3, "score": 0.83, "snippet": "…"}
  ],
  "latency_ms": 12.4,
  "used_llm": false,
  "mode": "hybrid",
  "top_k": 5
}
```

- `contexts` 为空表示没有命中，此时 `answer` 走抽取式降级，仍返回 200。
- `latency_ms` 是服务端自测耗时，不含网络。

## 错误响应

统一结构：

```json
{
  "error": {
    "code": "QUESTION_TOO_LONG",
    "message": "question 长度不能超过 2000 个字符",
    "request_id": "0f3c…",
    "details": {"length": 2001, "max": 2000}
  }
}
```

| HTTP | code | 触发条件 |
|---|---|---|
| 400 | EMPTY_QUESTION | question 为空或全空白 |
| 400 | QUESTION_TOO_LONG | question 超过 2000 字符 |
| 422 | INVALID_PARAM | 缺字段、字段类型错、top_k 越界、mode 非法、多余字段 |
| 503 | INDEX_NOT_READY | 索引文件缺失或损坏 |
| 500 | INTERNAL_ERROR | 未捕获异常 |

## 响应头

| 头 | 说明 |
|---|---|
| `X-Request-ID` | 每次请求的唯一 id，出错时一并返回，便于对日志 |
| `X-Process-Time-Ms` | 服务端处理耗时 |
