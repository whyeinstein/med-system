#!/usr/bin/env bash
# 阶段 6 启用: 同时启动 FastAPI + Streamlit. 当前为占位脚本.
set -euo pipefail

echo "[run_dev] 阶段 6 会完善本脚本."
echo "  后端预期: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
echo "  前端预期: streamlit run frontend/app.py"
