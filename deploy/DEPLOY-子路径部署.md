# 智课工作台 · 子路径部署手册（/zhike/）

> 依据《智课工作台平台子路径部署改造方案》落地。目标：把「前端 + 后端 + PostgreSQL + Valkey」全套部署到
> **183.229.246.162**，通过现有 AI 平台的 Nginx 反向代理，挂载在 **`/zhike/`** 子路径下对外提供 HTTPS。
>
> 对外入口：`https://183.229.246.162:3001/zhike/`
> 一句话：平台 Nginx 终结 HTTPS，按前缀转发；转发时剥掉 `/zhike` 前缀，后端只看到 `/api/v1`、`/ws`、`/health`。

---

## 0. 本次已完成的代码改造（本仓库内）

| 文件 | 改动 |
|---|---|
| `frontend/vite.config.ts` | 增加 `base`，构建时读取 `VITE_BASE_PATH`（来自 `.env.production`），默认 `/` |
| `frontend/src/app/router.tsx` | `createBrowserRouter(..., { basename })`，basename 取 `import.meta.env.BASE_URL`，SPA 路由识别子路径 |
| `frontend/src/api/ws.ts` | 相对地址分支补上 `BASE_PATH`，WebSocket 不再丢失子路径前缀 |
| `frontend/.env.production`（新建） | `VITE_BASE_PATH=/zhike/`、`VITE_API_BASE_URL=/zhike/api/v1`、`VITE_WS_BASE_URL` 留空自动推导 |
| `docker-compose.yml` | PostgreSQL / Valkey / sandbox 改为容器内网互访（不映射宿主端口）；backend 保留 `8001:8001`；生产启动改 uvicorn（去 reload）；frontend 归入 `dev` profile |
| `.env`（根） | `ENVIRONMENT=production`、CORS 追加平台来源、`PUBLIC_API_BASE_URL` 指向公网子路径、强 JWT/ENCRYPTION 密钥、`SEED_ADMIN_PASSWORD` |
| `deploy/nginx-zhike.conf`（新建） | 平台 Nginx 需要的 4 个 location 片段 |

> ⚠️ 前端路由匹配用的 `location.pathname` 均来自 `useLocation()`（React Router 会自动剥离 basename），
> 已核对无需额外改动。

---

## 1. 准备：确认决策与风险

- **前缀**：本方案使用 `/zhike/`（独立前缀，不与平台自身 `/workspace/chats/...` 冲突）。若平台方要求换前缀，
  只需整体替换 `frontend/.env.production`、根 `.env` 的 `PUBLIC_API_BASE_URL`、`deploy/nginx-zhike.conf` 中的 `/zhike` 后重新构建。
- **端口**：目标服务器若已有 PostgreSQL(5432)/Redis(6379)，本方案已默认不映射宿主端口（仅容器内网），
  backend 仍需占用宿主 **8001**（Nginx 反代目标）。若 8001 也被占用，改 `docker-compose.yml` 的
  `"8001:8001"` 为其它端口，并同步修改 `deploy/nginx-zhike.conf` 的 `proxy_pass`。

---

## 2. 服务器端部署步骤

### 2.1 同步代码与配置

把仓库同步到目标服务器（git push/pull 或 scp 整目录），**根 `.env` 必须带上**（含 API Key、强密钥）。
⚠️ 不要把 `frontend/node_modules`、`backend/.venv` 传上去（有 `.dockerignore`）。

### 2.2 启动后端栈

```bash
cd /path/to/zhike-ai-learning-workbench
docker compose -p zhike up -d --build
```

- 会自动执行 `alembic upgrade head`（含 0039 迁移：用 `SEED_ADMIN_PASSWORD` 写管理员密码）再启动 uvicorn。
- 验证后端：`curl http://127.0.0.1:8001/health` 应返回 `{"status":"ok",...}`。

### 2.3 构建前端并上传 dist

构建产物要求 `base=/zhike/`（已写入 `frontend/.env.production`，直接构建即可）。

**在本机（Windows）构建：**

```powershell
cd D:\Develop\Challenge Cup\frontend
corepack pnpm build
# 产物在 frontend/dist/
```

或直接在服务器（Linux）构建：

```bash
cd frontend
pnpm build
```

然后把 `dist/` 上传到服务器并放置到 Nginx alias 目录：

```bash
mkdir -p /srv/zhike/frontend
scp -r dist root@183.229.246.162:/srv/zhike/frontend/
# 服务器上：mv /srv/zhike/frontend/dist /srv/zhike/frontend/dist  （确认路径为 /srv/zhike/frontend/dist）
```

> 若服务器上不想用 `/srv/zhike/frontend/dist`，可自定目录，但必须同步修改 `deploy/nginx-zhike.conf` 的 `alias`。

### 2.4 平台 Nginx 增加转发

把 `deploy/nginx-zhike.conf` 里的 4 个 location 块追加到平台现有 server 块
（监听 **3001**、已配置 TLS 的那个），然后：

```bash
nginx -t && nginx -s reload
```

---

## 3. 验证清单（浏览器）

| # | 检查项 | 期望 |
|---|---|---|
| 1 | 打开 `https://183.229.246.162:3001/zhike/` | 首页/登录页正常加载，无静态资源 404 |
| 2 | 登录成功 | 跳转到 `/zhike/dashboard`（或 `/zhike/ta/dashboard`） |
| 3 | 刷新页面 | 不 404（SPA history 回退生效） |
| 4 | AI 对话 | WebSocket 连接成功（`wss://183.229.246.162:3001/zhike/ws`），消息能流式收发 |
| 5 | 管理端 | `/zhike/admin/...` 可访问 |
| 6 | 健康检查 | `https://183.229.246.162:3001/zhike/health` 返回 `status: ok` |
| 7 | 跨域 | 浏览器 Console 无 CORS 报错（后端 CORS 已含 `https://183.229.246.162:3001`） |

**定位技巧**：F12 → Network 过滤 `ws`，确认 WS 地址带 `/zhike/ws`；若连不上，多半是 Nginx 的
`Upgrade`/`Connection` 头没配上，或 `proxy_pass` 前缀没剥对。

---

## 4. 让「另一个平台上的 Skill」走真实后端

部署完成后，智课后端有了公网可达的 AI 网关（DeepSeek 等，见根 `.env` 的 `*_API_KEY`）。
在另一个平台运行 skill 时：

1. 把 skill 的 `BASE_URL` 指向：`https://183.229.246.162:3001/zhike`
   （本仓库的 `zhike-ta-portal` skill 支持环境变量 `ZHIXE_TA_BASE_URL` 覆盖，无需改 skill 代码）
2. 所有接口路径自动变为 `https://183.229.246.162:3001/zhike/api/v1/...`
3. 依赖 AI 的环节（如追问、AI 批改、学情诊断）由真实后端模型网关完成，不再依赖平台自带 AI。

> 首次使用需注册教师账号：`POST {BASE_URL}/api/v1/auth/register {"email":..., "password":..., "role":"ta"}`，
> 或使用管理员账号（管理员同样可访问 TA 接口）。

---

## 5. 常见故障

| 现象 | 处理 |
|---|---|
| 页面加载但接口 404 | dist 未重新构建（旧 base 为 `/`）；重新 `pnpm build` 并覆盖 `/srv/zhike/frontend/dist` |
| WS 连不上 | 检查 Nginx `location /zhike/ws` 的 Upgrade 头与 `proxy_pass http://127.0.0.1:8001/ws`；确认 8001 可直连 |
| 浏览器 CORS 报错 | 确认后端 `.env` 的 `CORS_ORIGINS` 含 `https://183.229.246.162:3001` 且容器已重启 |
| 后端拒绝启动（密钥报错） | 生产环境要求强密钥：`JWT_SECRET_KEY`/`ENCRYPTION_KEY` ≥32 字符且非示例值（已生成） |
| 8001 端口冲突 | 改 `docker-compose.yml` 映射端口 + `deploy/nginx-zhike.conf` 的 `proxy_pass` |
| 管理员登录失败 | 首次部署用 `SEED_ADMIN_PASSWORD`（见根 `.env`）；登录后立即在个人设置改密 |

---

## 6. 回滚

- 前端：用 `base=/`（即删除 `.env.production` 或改 `VITE_BASE_PATH=/`）重新构建即可，反代移除新增 location。
- 后端/数据：保留改造前代码分支；`docker compose -p zhike down` 停止，数据卷保留。
- 换前缀：全局替换 `/zhike` → 新前缀（4 处：`.env.production`、根 `.env` 的 `PUBLIC_API_BASE_URL`、Nginx conf、CORS 若含路径），重新构建前端 + reload Nginx。
