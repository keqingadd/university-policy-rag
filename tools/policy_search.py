"""工具 1：政策知识库检索（包装已有的 RAG 服务）。"""
from __future__ import annotations

from typing import Callable

from .registry import Tool, ToolError

KEYWORDS = (
    "奖学金", "助学金", "励志", "国奖", "国励", "贷款", "助学贷款", "勤工", "资助",
    "学费", "住宿费", "退费", "减免", "名额", "金额", "申请", "条件", "评定", "评审",
    "公示", "学籍", "转专业", "保研", "推免", "处分", "违纪", "申诉", "宿舍", "毕业",
    "学位", "绩点", "挂科", "重修", "选课", "实习", "医保", "档案", "报到证", "政策", "规定",
    "认定", "困难", "材料", "流程", "要求", "标准", "办法", "细则",
)

PARAMETERS = {
    "type": "object",
    "properties": {
        "question": {"type": "string", "minLength": 1, "maxLength": 2000, "description": "要检索的政策问题"},
        "top_k": {"type": "integer", "minimum": 1, "maximum": 10, "description": "召回条数"},
    },
    "required": ["question"],
    "additionalProperties": False,
}


def policy_search_tool(service_provider: Callable[[], object]) -> Tool:
    """service_provider 是取当前 RagService 的函数（索引可能还没加载好）。"""

    def handler(args: dict) -> dict:
        service = service_provider()
        if service is None:
            raise ToolError("INDEX_NOT_READY", "政策索引未就绪，先运行 python scripts/build_index.py")
        result = service.ask(args["question"], args.get("top_k"))
        return {
            "answer": result["answer"],
            "contexts": result["contexts"],
            "used_llm": result["used_llm"],
            "mode": result["mode"],
            "retrieval_ms": result["latency_ms"],
            "n_contexts": len(result["contexts"]),
        }

    return Tool(
        name="policy_search",
        description="在高校学生政策知识库里检索（奖学金/助学金/贷款/学籍/处分等），返回带出处的答案。",
        parameters=PARAMETERS,
        handler=handler,
        keywords=KEYWORDS,
    )
