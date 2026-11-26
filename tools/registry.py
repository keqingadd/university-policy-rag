"""工具注册表：JSON Schema（子集）校验 + 统一错误码。

只实现本仓库用得到的校验能力（type / required / minimum / maximum / enum /
minLength / maxLength / pattern / additionalProperties=false），不引入 jsonschema，
保持零新依赖。校验失败一律抛 ToolError，由接口层翻译成业务错误码。
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any, Callable

_TYPE_CHECKS: dict[str, Callable[[Any], bool]] = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
}


class ToolError(Exception):
    """工具层错误：code 是给接口层用的业务错误码。"""

    def __init__(self, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    handler: Callable[[dict], dict]
    keywords: tuple[str, ...] = ()

    def spec(self) -> dict:
        """对外暴露的 schema：不含内部用于规则路由的关键词。"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": copy.deepcopy(self.parameters),
        }


def _fail(message: str, field: str | None = None) -> ToolError:
    details = {"fields": [{"loc": field, "msg": message}]} if field else None
    return ToolError("INVALID_TOOL_ARGS", message, details)


def validate_args(tool: Tool, args: dict) -> dict:
    if not isinstance(args, dict):
        raise _fail("工具参数必须是 JSON 对象")
    schema = tool.parameters
    props: dict = schema.get("properties", {})
    required: list = schema.get("required", [])
    if schema.get("additionalProperties", False) is False:
        unknown = sorted(set(args) - set(props))
        if unknown:
            raise _fail(f"不支持的参数：{', '.join(unknown)}", unknown[0])
    for name in required:
        if args.get(name) is None:
            raise _fail(f"缺少必填参数 {name}", name)
    for name, value in args.items():
        if value is None:
            continue
        spec = props.get(name, {})
        kind = spec.get("type")
        if kind and not _TYPE_CHECKS[kind](value):
            raise _fail(f"参数 {name} 类型应为 {kind}", name)
        if kind == "string":
            if "minLength" in spec and len(value) < spec["minLength"]:
                raise _fail(f"参数 {name} 至少 {spec['minLength']} 个字符", name)
            if "maxLength" in spec and len(value) > spec["maxLength"]:
                raise _fail(f"参数 {name} 最多 {spec['maxLength']} 个字符", name)
            if "pattern" in spec and not re.search(spec["pattern"], value):
                raise _fail(f"参数 {name} 格式不合法", name)
        if kind in ("integer", "number"):
            if "minimum" in spec and value < spec["minimum"]:
                raise _fail(f"参数 {name} 不能小于 {spec['minimum']}", name)
            if "maximum" in spec and value > spec["maximum"]:
                raise _fail(f"参数 {name} 不能大于 {spec['maximum']}", name)
        if "enum" in spec and value not in spec["enum"]:
            raise _fail(f"参数 {name} 必须是 {spec['enum']} 之一", name)
    return args


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        if not tool.name:
            raise ToolError("INVALID_TOOL", "工具必须有名字")
        if tool.name in self._tools:
            raise ToolError("DUPLICATE_TOOL", f"工具已注册：{tool.name}")
        self._tools[tool.name] = tool
        return tool

    def has(self, name: str) -> bool:
        return name in self._tools

    def get(self, name: str) -> Tool:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError("UNKNOWN_TOOL", f"没有这个工具：{name}", {"available": sorted(self._tools)})
        return tool

    def names(self) -> list[str]:
        return sorted(self._tools)

    def specs(self) -> list[dict]:
        return [self._tools[name].spec() for name in self.names()]

    def call(self, name: str, args: dict | None = None) -> dict:
        tool = self.get(name)
        payload = validate_args(tool, {} if args is None else args)
        try:
            result = tool.handler(payload)
        except ToolError:
            raise
        except Exception as exc:  # 工具内部异常统一收敛，避免把栈暴露给调用方
            raise ToolError("TOOL_EXEC_FAILED", f"工具 {name} 执行失败：{exc}") from exc
        if not isinstance(result, dict):
            raise ToolError("TOOL_EXEC_FAILED", f"工具 {name} 返回值必须是 dict")
        return result
