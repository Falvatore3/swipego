#!/bin/bash
# 拉取手机端上传的调试日志
# 用法：
#   ./fetch-logs.sh             # 列出最新 20 条 key
#   ./fetch-logs.sh <key>       # 查看具体一条

set -e

# ⚠️ 改成你部署后的 worker base URL
BASE="${SWIPEGO_WORKER:-https://swipego-deepseek-proxy.YOUR-SUBDOMAIN.workers.dev}"
TOKEN="${SWIPEGO_DEBUG_TOKEN:-CHANGE_ME}"

if [ -z "$1" ]; then
  echo "📋 列出最新 20 条日志："
  curl -s "$BASE/log/list?token=$TOKEN&limit=20" | jq .
  echo ""
  echo "查看某条：./fetch-logs.sh <key>"
else
  echo "📖 查看 $1："
  curl -s "$BASE/log/get?token=$TOKEN&key=$1" | jq .
fi
