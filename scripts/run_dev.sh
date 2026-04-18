#!/usr/bin/env bash
# 阶段 6: 同时启动 FastAPI 后端与 Streamlit 前端 (开发模式).
#
# 用法:
#   bash scripts/run_dev.sh            # 同时启动前后端
#   BACKEND_ONLY=1 bash scripts/run_dev.sh
#   FRONTEND_ONLY=1 bash scripts/run_dev.sh
#
# 环境变量:
#   BACKEND_HOST   默认 0.0.0.0
#   BACKEND_PORT   默认 8000
#   FRONTEND_PORT  默认 8501
#   BACKEND_URL    传给前端 (默认 http://localhost:${BACKEND_PORT})
#
# 前置条件: 已激活 conda env qwen, 并完成 init_db / build_kb_index.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-8501}"
export BACKEND_URL="${BACKEND_URL:-http://localhost:${BACKEND_PORT}}"

BACKEND_ONLY="${BACKEND_ONLY:-0}"
FRONTEND_ONLY="${FRONTEND_ONLY:-0}"

# 禁止 huggingface_hub / sentence-transformers 发起任何网络请求 (无外网环境必须)
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

# 确保项目根目录在 Python 模块搜索路径中 (Streamlit 默认只加 frontend/ 目录)
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH:-}"

backend_pid=""
frontend_pid=""

cleanup() {
    [[ -n "${backend_pid}"  ]] && kill "${backend_pid}"  2>/dev/null || true
    [[ -n "${frontend_pid}" ]] && kill "${frontend_pid}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if [[ "${FRONTEND_ONLY}" != "1" ]]; then
    echo "[run_dev] FastAPI → http://${BACKEND_HOST}:${BACKEND_PORT}"
    uvicorn app.main:app --host "${BACKEND_HOST}" --port "${BACKEND_PORT}" --reload &
    backend_pid=$!
fi

if [[ "${BACKEND_ONLY}" != "1" ]]; then
    echo "[run_dev] Streamlit → http://localhost:${FRONTEND_PORT}  (BACKEND_URL=${BACKEND_URL})"
    streamlit run frontend/app.py \
        --server.port "${FRONTEND_PORT}" \
        --server.headless true \
        --browser.gatherUsageStats false &
    frontend_pid=$!
fi

# 等待任一子进程退出
wait -n
#!/usr/bin/env bash
# 阶段 6 启用: 同时启动 FastAPI + Streamlit. 当前为占位脚本.
set -euo pipefail

echo "[run_dev] 阶段 6 会完善本脚本."
echo "  后端预期: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
echo "  前端预期: streamlit run frontend/app.py"
