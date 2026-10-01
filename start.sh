#!/bin/bash
echo "=== 印谱PDF提取工具 - Mac启动脚本 ==="
cd "$(dirname "$0")"

# 查找兼容的 Python 版本（3.9-3.12）
PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3.9 python3; do
    if command -v "$cmd" &> /dev/null; then
        ver=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -eq 3 ] && [ "$minor" -ge 9 ] && [ "$minor" -le 12 ]; then
            PYTHON="$cmd"
            echo "✅ 找到兼容 Python: $("$cmd" --version)"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "❌ 未找到兼容的 Python（需要 3.9~3.12）"
    echo "💡 请运行: brew install python@3.11"
    exit 1
fi

# 创建虚拟环境
if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    "$PYTHON" -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
echo "📦 安装依赖（首次运行需要几分钟）..."
pip install --upgrade pip
pip install -r requirements.txt

# 启动 Streamlit
echo "🚀 启动印谱工具..."
streamlit run app.py
