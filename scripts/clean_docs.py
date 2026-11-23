# -*- coding: utf-8 -*-
"""清理政策文档的网页噪音，删除虚构示例文档。"""
import re
from pathlib import Path

D = Path("data/docs")

RULES = {
    "01-普通高等学校学生管理规定.md": (r"^##\s*普通高等学校学生管理规定\s*$", None),
    "02-安徽省家庭经济困难学生认定工作实施办法.md": (r"^安徽省教育厅等六部门关于印发", r"^版权所有"),
    "03-学生资助政策14项.md": (None, None),
    "04-本专科生国家奖学金评审办法.md": (r"^教育部 财政部关于印发《本专科生国家奖学金评审办法》的通知", r"^扫一扫在手机打开当前页"),
    "05-高等学校勤工助学管理办法.md": (r"^教育部 财政部关于印发《高等学校勤工助学管理办法", r"^中国政府网微博"),
    "06-助学贷款政策调整通知.md": (r"^教育部等四部门关于调整完善助学贷款有关政策的通知\s*$", r"^中国政府网微博"),
}

META = re.compile(r"^(/20\d{5,}|科技、教育.*|\d{4}-\d{2}-\d{2}( \d{2}:\d{2}:\d{2})?|"
                  r"[\w\-]{10,20}|标\s*题：.*|发文机关：.*|来\s*源：.*|成文日期：.*|"
                  r"主题分类：.*|发文字号：.*|发布日期：.*)$")

for name, (start_pat, end_pat) in RULES.items():
    p = D / name
    if not p.exists():
        print("skip missing", name)
        continue
    lines = p.read_text(encoding="utf-8").splitlines()
    start, end = 0, len(lines)
    if start_pat:
        for i, line in enumerate(lines):
            if re.search(start_pat, line):
                start = i
                break
    if end_pat:
        for j in range(start, len(lines)):
            if re.search(end_pat, lines[j]):
                end = j
                break
    body = lines[start:end]
    # 去掉头部的元数据行（仅在前 15 行内处理）
    cleaned: list[str] = []
    for idx, line in enumerate(body):
        stripped = line.strip()
        if idx < 15 and META.match(stripped):
            continue
        cleaned.append(line.rstrip())
    # 压缩连续空行
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned)).strip() + "\n"
    p.write_text(text, encoding="utf-8")
    print(f"clean {name}: {len(lines)} -> {len(text.splitlines())} lines, {len(text)} chars")

fiction = ["01-产品概览.md", "02-部署与运维.md", "03-API使用指南.md",
           "04-常见问题FAQ.md", "05-定价与套餐.md", "06-安全与合规.md"]
removed = 0
for f in fiction:
    p = D / f
    if p.exists():
        p.unlink()
        removed += 1
print("removed fiction docs:", removed)
print("remaining:", sorted(x.name for x in D.glob("*.md")))
