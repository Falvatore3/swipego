# 配置云端调试日志（5 分钟）

## 🎯 你要做的 3 件事

### ① 在 Cloudflare 建一个 KV 命名空间

1. 浏览器打开 https://dash.cloudflare.com
2. 左边栏点 **Workers & Pages**
3. 再点子菜单 **KV**（在 Workers & Pages 展开里）
4. 右上角 **Create a namespace**
5. 名字写：`swipego-logs`
6. 点 **Add**

✅ 完成后会有一个 **Namespace ID**（一长串十六进制字符），把它**复制下来**发给我。
样子像：`a1b2c3d4e5f6789012345678abcdef00`

---

### ② 设一个 Debug Token（防止陌生人偷看你的日志）

打开终端，进 worker 目录：

```bash
cd /Users/frankie/WorkBuddy/2026-05-08-task-2/swipego/cf-worker
wrangler secret put DEBUG_TOKEN
```

它会让你输入一个值。**随便编一个长字符串**（比如 `swipego-debug-2026-frankie-secret-xyz123`），按回车。

✅ 看到 `Success! Uploaded secret DEBUG_TOKEN` 就好。把这个 token 也发给我（或者你自己保存）。

---

### ③ 告诉我你的 Worker URL

之前部署 deepseek 代理时拿到的那个 `https://swipego-deepseek-proxy.xxx.workers.dev` 形式的 URL，发给我。
（如果忘了，在 Cloudflare Dashboard → Workers & Pages → 找到 `swipego-deepseek-proxy` → 点进去能看到）

---

## 🤖 我会做的事

收到你给我 3 个东西（KV ID + Debug Token + Worker URL）后：

1. 把 wrangler.toml 里的 KV ID 替换上
2. 把 index.html 里的 `DEBUG_UPLOAD_BASE` 填上 worker URL
3. 把 fetch-logs.sh 里的 BASE / TOKEN 填上
4. 用 `wrangler deploy` 重新部署 worker
5. push 前端到 GitHub Pages
6. 自己试一下 `curl` 看能不能拿到日志

之后你的工作流：

```
手机刷 swipego → 出问题 → 点右下角 🐞 → ☁️ 上传到云端
                                          ↓
                                       告诉我 key
                                          ↓
                                    我 curl 直接看现场
```

---

## 💸 费用确认

KV 免费额度（每天）：
- 读 10 万次（你预计每天 < 10 次）
- 写 1 千次（你预计每天 < 50 次）
- 存储 1 GB（一条日志 ~10KB，能存 10 万条）
- 日志 7 天自动过期，不会越积越多

**永远不会超出免费额度，0 元。**
