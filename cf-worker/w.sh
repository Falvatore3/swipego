#!/bin/bash
# wrangler 包装器：自动用本地 node + 本地装的 wrangler
# 用法：./w.sh login | ./w.sh deploy | ./w.sh secret put DEEPSEEK_KEY 等
DIR="$(cd "$(dirname "$0")" && pwd)"
export PATH="/Users/frankie/.workbuddy/binaries/node/versions/20.18.0/bin:$PATH"
exec "$DIR/node_modules/.bin/wrangler" "$@"
