# main.py
# ⚠ DEPRECATED（2026-10-16，Kevin 裁定）：本地版入口已改为 **PyWebView**
#   ⇒ `./venv/bin/python webui/app.py`（原生窗口）。本 Streamlit 入口**保留不删、不再维护**，
#   也不要再起 8502 端口；只作历史参照（`streamlit run main.py` → `src/webui.py`）。
"""
「斐萃」本地电脑版 启动入口（**已退役，2026-10-16**）
运行：streamlit run main.py
"""
import os
import sys

import streamlit.web.bootstrap

if __name__ == "__main__":
    # 确保 src 包可导入
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    streamlit.web.bootstrap.run(
        "src/webui.py",
        is_hello=False,
        args=[],
        flag_options={},
    )
