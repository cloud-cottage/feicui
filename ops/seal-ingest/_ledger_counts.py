#!/usr/bin/env python3
"""极简台账计数（供分片器使用）：打印 status 计数 JSON。"""
import json
import sqlite3
import sys

c = sqlite3.connect(sys.argv[1])
rows = c.execute("SELECT status, COUNT(*) FROM seal_images GROUP BY status").fetchall()
d = {k: v for k, v in rows}
d["_total"] = sum(d.values())
print(json.dumps(d, ensure_ascii=False, sort_keys=True))
