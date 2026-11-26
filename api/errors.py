"""统一异常与错误码。

约定：业务异常一律抛 AppError，由 main.py 的异常处理器转成固定 JSON 结构，
保证任何失败路径都能被接口测试断言（而不是 FastAPI 默认的 detail 字符串）。
"""
from __future__ import annotations

from typing import Any

# 错误码 -> HTTP 状态码。改这里就等于改契约，测试用例以它为准。
ERROR_STATUS: dict[str, int] = {
    "EMPTY_QUESTION": 400,
    "QUESTION_TOO_LONG": 400,
    "INVALID_PARAM": 422,
    "INDEX_NOT_READY": 503,
    "INTERNAL_ERROR": 500,
}

DEFAULT_MESSAGES: dict[str, str] = {
    "EMPTY_QUESTION": "问题不能为空",
    "INVALID_PARAM": "请求参数不合法",
    "INDEX_NOT_READY": "索引未就绪，请先构建索引",
    "INTERNAL_ERROR": "服务内部错误",
}


class AppError(Exception):
    """带错误码的业务异常。"""

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        status_code: int | None = None,
        details: Any = None,
    ) -> None:
        self.code = code
        self.status_code = status_code or ERROR_STATUS.get(code, 500)
        self.message = message or DEFAULT_MESSAGES.get(code, code)
        self.details = details
        super().__init__(self.message)
