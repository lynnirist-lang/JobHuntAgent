#!/usr/bin/env bash
# ============================================================
# 一键启动脚本
#
# 使用方式：
#   ./start.sh         — 同时启动后端 + 前端
#   ./start.sh backend — 仅启动后端
#   ./start.sh frontend — 仅启动前端
# ============================================================

set -e

# 检查 .env 文件
if [ ! -f ".env" ]; then
  echo "⚠  未找到 .env 文件，请复制 .env.example 并填写 DEEPSEEK_API_KEY"
  cp .env.example .env
  echo "已自动复制 .env.example → .env，请编辑后重新运行"
  exit 1
fi

# 检查 user_profile.json
if [ ! -f "user_profile.json" ]; then
  echo "⚠  未找到 user_profile.json，已复制模板，请填写个人信息后重新运行"
  cp user_profile.example.json user_profile.json
  exit 1
fi

start_backend() {
  echo "▶  启动后端 FastAPI (端口 8080)…"
  uvicorn backend.main:app --reload --port 8080
}

start_frontend() {
  echo "▶  启动前端 Next.js (端口 3001)…"
  cd frontend && npm run dev
}

case "${1:-all}" in
  backend)  start_backend ;;
  frontend) start_frontend ;;
  all)
    # 并行启动，Ctrl+C 同时停止两者
    trap 'kill 0' INT
    start_backend &
    start_frontend &
    wait
    ;;
  *)
    echo "用法：./start.sh [backend|frontend|all]"
    exit 1
    ;;
esac
