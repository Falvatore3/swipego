# SwipeGo DeepSeek 代理 — 部署指南（给 Frankie）

> 这份文档帮你把 DeepSeek 的 API key 藏到 Cloudflare Workers 服务端，
> 这样前端 `swipego` 仓库就**不再需要**写 key 了，别人扒代码也刷不了你的余额。
>
> 全程在你**本机终端**执行，不需要会写后端，照着步骤抄命令就行。预计 15 分钟内搞定。

---

## 你大概要做什么（先了解全貌）

1. 注册一个 Cloudflare 账号（免费）
2. 在你电脑上装一个叫 `wrangler` 的命令行工具
3. 用 `wrangler` 登录 Cloudflare
4. 用 `wrangler` 把 DeepSeek key 写进 Cloudflare 的"密钥保险箱"
5. 用 `wrangler` 把这个文件夹的代码部署上去
6. 拿到一个 `https://xxx.workers.dev` 的地址
7. 在前端代码里把 `https://api.deepseek.com/...` 换成这个新地址

---

## 准备工作

- 一台能上网的 Mac/Windows/Linux 都行
- 已经装了 Node.js（在终端里跑 `node -v`，能看到版本号即可；没装就去 https://nodejs.org 下 LTS 版）
- 一个邮箱用来注册 Cloudflare
- 你的 DeepSeek API key（**就是已经被泄露的那个，先用来部署，部署完立刻去 DeepSeek 后台 reset 一下，再用新 key 重新设 secret**）

---

## ✅ 步骤 1：注册 Cloudflare 账号

1. 打开 https://dash.cloudflare.com/sign-up
2. 用邮箱 + 密码注册，验证邮箱
3. 登录进 dashboard

> **完成会看到**：左侧菜单里有"Workers & Pages"这一项。
>
> **出错怎么办**：邮件没收到就检查垃圾箱；如果提示要绑信用卡，**忽略它**，免费版不需要。

---

## ✅ 步骤 2：安装 Wrangler CLI

打开终端（Mac 用"终端" App，Windows 用 PowerShell），执行：

```bash
npm install -g wrangler
```

验证是否装好：

```bash
wrangler --version
```

> **完成会看到**：输出一个版本号，例如 `⛅️ wrangler 3.x.x`。
>
> **出错怎么办**：
> - 提示 `permission denied`：Mac 上加 `sudo`，即 `sudo npm install -g wrangler`
> - 提示 `command not found: npm`：你 Node.js 没装好，回去装 Node。

---

## ✅ 步骤 3：登录 Cloudflare

进入这个 worker 的目录（**注意路径**）：

```bash
cd /Users/frankie/WorkBuddy/2026-05-08-task-2/swipego/cf-worker
```

然后执行登录：

```bash
wrangler login
```

它会自动打开浏览器，让你点"Allow"授权。

> **完成会看到**：终端打印 `Successfully logged in.`，浏览器页面显示 "You have logged in."。
>
> **出错怎么办**：
> - 浏览器没自动打开：复制终端里那个 `https://dash.cloudflare.com/oauth2/auth?...` 的链接，手动粘到浏览器。
> - 公司 / 学校网络挡了 oauth：换手机热点试试。

---

## ✅ 步骤 4：把 DeepSeek key 写进 Worker secret（**最关键的一步**）

**不要**把 key 写到任何文件里！只用下面这条命令注入：

```bash
wrangler secret put DEEPSEEK_KEY
```

运行后它会提示 `Enter a secret value:`，把你的 DeepSeek key（`sk-` 开头那一长串）粘进去回车。

> **完成会看到**：`✨ Success! Uploaded secret DEEPSEEK_KEY`。
>
> **出错怎么办**：
> - 提示 `You need to create a worker first` → 先跳到步骤 5 部署一次（哪怕没 key 也能创建），创建完再回来跑这条命令。
> - 提示选 worker 名字 → 选 `swipego-deepseek-proxy`（在 `wrangler.toml` 里定义的）。
>
> ⚠️ **安全提示**：这条命令把 key 加密存到 Cloudflare 服务器，Worker 运行时才能读到，**任何人**（包括你自己）都没法再从 dashboard 看到原文。这就是我们要的效果。

---

## ✅ 步骤 5：部署 Worker

确认你还在 `cf-worker` 目录下，然后执行：

```bash
wrangler deploy
```

> **完成会看到**：终端最后打印一行类似：
> ```
> Published swipego-deepseek-proxy (1.23 sec)
>   https://swipego-deepseek-proxy.<你的-cf-用户名>.workers.dev
> ```
> 这个 URL 就是给前端用的代理地址，**记下来**。
>
> **出错怎么办**：
> - 第一次部署 CF 会让你选一个 `workers.dev` 子域名，按提示输一个全局唯一的就行（例如你的英文名）。
> - 提示 `DEEPSEEK_KEY is not defined` 之类报错：回去执行步骤 4。
> - 提示某个端口/字段格式错：把 `wrangler.toml` 内容贴给团队 lead 看。

---

## ✅ 步骤 6：验证部署成功

打开浏览器访问：

```
https://swipego-deepseek-proxy.<你的-cf-用户名>.workers.dev/healthz
```

> **完成会看到**：页面纯文本显示 `ok`。
>
> **出错怎么办**：返回 1101 / 500 错误 → 在终端跑 `wrangler tail` 实时看日志，找报错。

---

## ✅ 步骤 7：在前端把 DeepSeek URL 替换成 Worker URL

打开前端项目 `swipego` 仓库里调用 DeepSeek 的代码，**做两件事**：

1. **删掉硬编码的 key**（找出 `sk-` 开头那一行，整行删掉，包括相关变量）。
2. **把 URL 替换**：

   **改之前（旧）**：
   ```js
   fetch("https://api.deepseek.com/chat/completions", {
     method: "POST",
     headers: {
       "Content-Type": "application/json",
       "Authorization": `Bearer ${DEEPSEEK_KEY}`,  // ← 删掉这行
     },
     body: JSON.stringify({ ... })
   })
   ```

   **改之后（新）**：
   ```js
   fetch("https://swipego-deepseek-proxy.<你的-cf-用户名>.workers.dev/v1/chat/completions", {
     method: "POST",
     headers: {
       "Content-Type": "application/json",
       // 不再需要 Authorization，Worker 帮你加
     },
     body: JSON.stringify({ ... })   // body 内容**完全不用变**
   })
   ```

3. 提交 + push 到 GitHub Pages，等 Pages 重新发布。

> **完成会看到**：在 https://falvatore3.github.io/swipego/ 调用 AI 功能能正常返回结果。
>
> **出错怎么办**：
> - 浏览器控制台出现 `CORS` 错误 → 检查你访问的域名是不是 `https://falvatore3.github.io`（注意 `falvatore3`），如果你用了别的域名，告诉团队 lead 把它加到 `wrangler.toml` 的 `ALLOWED_ORIGINS` 里再 `wrangler deploy` 一次。
> - 返回 403 `Origin not allowed` → 同上。
> - 返回 429 `Too Many Requests` → 简易限流默认 20 次/分钟/IP，正常使用碰不到，碰到就等一分钟。
> - 返回 500 `DEEPSEEK_KEY not set` → 步骤 4 没做。

---

## ✅ 步骤 8（**强烈建议**）：换掉那个泄露的 key

旧 key 在 GitHub 公网仓库里出现过，几乎可以默认它已经被爬虫扒走了。

1. 登录 https://platform.deepseek.com/ 的 API Keys 页面
2. **删除**旧 key
3. **新建**一个新的 key，复制
4. 回到终端再跑一次：
   ```bash
   wrangler secret put DEEPSEEK_KEY
   ```
   把**新的** key 粘进去回车（会自动覆盖旧的）。
5. **不需要重新 deploy**，secret 是即时生效的。

---

## 常见问题 FAQ

**Q：免费版 Workers 够用吗？**
A：免费每天 10 万次请求。SwipeGo 这种小流量产品完全够。

**Q：能看到 Worker 的实时日志吗？**
A：终端里跑 `wrangler tail`，会把 Worker 的 `console.log` 实时推给你（我们只记时间/状态/token 用量，不记你和用户的对话内容）。

**Q：以后 DeepSeek 又出新模型，要改 Worker 吗？**
A：不用。Worker 是**透明转发**，body 是什么样原样转发，前端 body 里写 `model: "deepseek-chat"` 还是 `model: "deepseek-reasoner"` 都能走通。

**Q：要不要绑自定义域名？**
A：不强求。`*.workers.dev` 已经能跑。等你想要更专业的形象再去 `wrangler.toml` 里加 `[routes]`。

**Q：怎么把 Worker 删掉？**
A：`wrangler delete`（在这个目录里跑）。

---

## 文件结构速览

```
cf-worker/
├── wrangler.toml      ← Worker 配置（白名单/限流参数都在这）
├── src/
│   └── index.js       ← Worker 主程序（CORS / 转发 / 限流 / 日志）
└── README.md          ← 这份文档
```

如有任何步骤卡住，把终端报错截图发出来，团队 lead 会帮你看。
