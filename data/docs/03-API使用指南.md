# API 使用指南

## 认证方式
所有接口使用 Bearer Token 认证。在控制台「应用管理」中创建应用后获取 API Key，请求头需携带：

    Authorization: Bearer <your_api_key>

## 接口列表
- POST /v1/chat/completions：对话生成，兼容 OpenAI 协议。
- POST /v1/kb/query：知识库检索，返回命中的切片与相似度分数。
- POST /v1/kb/ingest：上传文档并构建索引。
- GET /v1/kb/status：查询索引构建进度。

## 限流规则
默认限流为每个应用 60 QPS，突发流量允许短时达到 120 QPS（持续不超过 10 秒）。超出限流会返回 HTTP 429，响应头 Retry-After 给出建议重试秒数。企业版可申请提升到 300 QPS。

## 错误码
- 401 Unauthorized：API Key 无效或已过期。
- 403 Forbidden：应用没有该知识库的访问权限。
- 429 Too Many Requests：触发限流，按 Retry-After 退避重试。
- 500 Internal Server Error：服务端异常，可重试 1 到 2 次，仍失败请联系技术支持。
- 504 Gateway Timeout：生成超时，建议缩短上下文或降低 max_tokens。

## 调用示例（Python）
    import requests
    resp = requests.post(
        "https://api.zhiqing.example.com/v1/chat/completions",
        headers={"Authorization": "Bearer <key>"},
        json={"model": "zqc-chat", "messages": [{"role": "user", "content": "支持私有化吗？"}]},
        timeout=60,
    )
    print(resp.json()["choices"][0]["message"]["content"])
