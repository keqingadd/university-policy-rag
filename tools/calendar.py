"""工具 2：校历查询（教学周、假期、下一个时间节点）。

数据来自本地 JSON（默认 data/calendar/semester.json），示例数据仅用于演示，
不代表任何学校的真实校历；替换文件即可接入真实校历。
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .registry import Tool, ToolError

KEYWORDS = (
    "校历", "开学", "报到", "放假", "寒假", "暑假", "第几周", "教学周", "周次",
    "考试周", "期末考试", "期中考试", "节假日", "国庆", "元旦", "清明", "五一",
    "中秋", "春节", "还有几天", "什么时候开学", "什么时候放假",
)

WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")

PARAMETERS = {
    "type": "object",
    "properties": {
        "date": {
            "type": "string",
            "pattern": r"^\d{4}-\d{2}-\d{2}$",
            "description": "要查询的日期 YYYY-MM-DD，缺省为今天",
        }
    },
    "required": [],
    "additionalProperties": False,
}


def load_calendar(path: str | Path) -> dict:
    file = Path(path)
    if not file.is_file():
        raise ToolError("CALENDAR_NOT_READY", f"校历文件不存在：{file}")
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ToolError("CALENDAR_BROKEN", f"校历文件不是合法 JSON：{exc}") from exc


def _to_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ToolError("INVALID_TOOL_ARGS", f"日期格式应为 YYYY-MM-DD：{value}") from exc


def _events(data: dict) -> list[dict]:
    out = []
    for item in data.get("events", []):
        out.append(
            {
                "name": item["name"],
                "kind": item.get("kind", "event"),
                "start": _to_date(item["start"]),
                "end": _to_date(item.get("end") or item["start"]),
            }
        )
    out.sort(key=lambda e: e["start"])
    return out


def calendar_tool(path: str | Path, today: dt.date | None = None) -> Tool:
    def handler(args: dict) -> dict:
        data = load_calendar(path)
        current = _to_date(args["date"]) if args.get("date") else (today or dt.date.today())
        term = data.get("term") or {}
        term_start = _to_date(term["start"]) if term.get("start") else None
        term_end = _to_date(term["end"]) if term.get("end") else None
        in_term = bool(term_start and term_end and term_start <= current <= term_end)
        teaching_week = None
        if in_term and term_start:
            teaching_week = (current - term_start).days // 7 + 1

        events = _events(data)
        current_event = None
        for event in events:
            if event["start"] <= current <= event["end"]:
                current_event = {"name": event["name"], "kind": event["kind"]}
                break

        upcoming = []
        next_event = None
        for event in events:
            if event["start"] > current:
                item = {
                    "name": event["name"],
                    "kind": event["kind"],
                    "start": event["start"].isoformat(),
                    "days_until": (event["start"] - current).days,
                }
                upcoming.append(item)
        if upcoming:
            next_event = dict(upcoming[0])

        return {
            "date": current.isoformat(),
            "weekday": WEEKDAYS[current.weekday()],
            "term": {"name": term.get("name"), "start": term.get("start"), "end": term.get("end")},
            "in_term": in_term,
            "in_break": bool(term_start and term_end and not in_term and current > term_end),
            "teaching_week": teaching_week,
            "current_event": current_event,
            "next_event": next_event,
            "upcoming_60d": [item for item in upcoming if item["days_until"] <= 60],
            "note": data.get("note"),
        }

    return Tool(
        name="calendar",
        description="查询校历：某日期是第几教学周、是否在假期、下一个时间节点还有几天。",
        parameters=PARAMETERS,
        handler=handler,
        keywords=KEYWORDS,
    )
