# -*- coding: utf-8 -*-
import re, sys
sys.path.insert(0, "scripts")
from fetch_policy import UA, BlockParser, decode, clean_blocks, to_markdown
import urllib.request
from pathlib import Path

jobs = [
    ("04-本专科生国家奖学金评审办法.md", "本专科生国家奖学金评审办法",
     "http://www.moe.gov.cn/srcsite/A05/s7505/201909/t20190930_401817.html"),
    ("05-高等学校勤工助学管理办法.md", "高等学校勤工助学管理办法（2018 年修订）",
     "https://www.gov.cn/zhengce/zhengceku/2018-12/31/content_5443471.htm"),
    ("06-助学贷款政策调整通知.md", "教育部等四部门关于调整完善助学贷款有关政策的通知",
     "https://www.gov.cn/zhengce/zhengceku/202309/content_6904362.htm"),
]
outdir = Path("data/docs")
for name, title, url in jobs:
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            ctype = resp.headers.get("Content-Type", "")
        text = decode(raw, ctype)
        parser = BlockParser()
        parser.feed(text)
        blocks = clean_blocks(parser.blocks)
        md = to_markdown(title, blocks)
        (outdir / name).write_text(md, encoding="utf-8")
        print(f"OK {name} chars={len(md)} blocks={len(blocks)}")
    except Exception as exc:
        print(f"FAIL {name}: {exc}")
