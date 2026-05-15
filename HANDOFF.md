# 📋 lit-share 项目交接文档

> 给下一个 Claude 会话：读完这份文档，你就有了所有上下文。
> 用户：Anna（annachow250815@gmail.com）
> 服务器：腾讯云 VM，公网 IP `43.173.104.146`
>
> **公开 demo**：https://hz.xpro.work/ （根路径，无 basic auth，可分享）
> **私有入口**：https://c.xpro.work/preview/lit/ （anna 凭据 basic auth + /preview/lit 前缀）
>
> 两域名同一个 uvicorn 进程、同一个 DB。Caddy 通过 `X-Forwarded-Prefix` 头告诉应用各自的公共 base path。

---

## 🎯 立即要做的事

```
M0 ✅ / M1 ✅ / M2 ✅ / M3 ✅ / M4 ✅ → 下一步：M5（SMTP + e2e 测试 + 部署优化）
```

> **Admin 已就绪**：邮箱 `annachow250815@gmail.com` / 密码 `Wxhz123321!`。
> 初始 200 积分（admin_gift seed），可直接发布。已有 `/admin` 后台。

---

## 📌 项目背景

公益学术 PDF 互助平台。完整需求文档：`/home/claude/inbox/文献互助平台.md`

**核心流程**：
```
用户付积分发求助 → 待应助大厅 → 应助者认领+上传 PDF → 求助者确认/驳回 → 积分到账
                                                          ↓
                                               48h 无确认 → 自动确认
```

完结后 PDF 沉淀到共享文献库，其他人免费下载。

---

## ✅ 已完成：M0 + M1 + M2 + M3 + M4

### 技术栈（已确认）
- **Python 3.12** + **FastAPI 0.115** + **SQLAlchemy 2.0** + **Alembic**
- **Jinja2** SSR + **HTMX** + **Alpine.js** + 自写 **CSS（学术蓝）**，**不上 SPA**
- **APScheduler**（48h 自动确认 scheduler）
- **PyMuPDF**（PDF 处理，M3 用）
- **SQLite 默认**，`DATABASE_URL` 切换 MySQL/PG。已装 `pymysql`、`psycopg[binary]` 驱动

### 项目结构（M3 后）
```
/home/claude/projects/lit-share/
├── .env / .env.example
├── requirements.txt        # bcrypt 直接用 + apscheduler + pymupdf
├── run.sh
├── HANDOFF.md              # ← 你正在看的文件
├── .venv/
├── app/
│   ├── __init__.py
│   ├── main.py             # FastAPI 入口 + lifespan 启停 APScheduler + 首页活动流
│   ├── settings.py         # Pydantic Settings (bootstrap 配置)
│   ├── db.py               # 引擎工厂 + SessionLocal + get_db
│   ├── models.py           # ORM,BigInt 变体跨 DB
│   ├── security.py         # bcrypt + 签名 cookie + current_user/require_login/require_admin
│   ├── templating.py       # render() + base_path_of(request)
│   ├── urls.py             # public_url/redirect/strip_base 助手
│   ├── runtime_config.py   # get_setting(db, key, default, cast) — system_settings
│   ├── points.py           # adjust_points + REASON_* 常量
│   ├── timekit.py          # Asia/Shanghai 时区 + humanize_remaining
│   ├── pdf_redact.py       # PyMuPDF 元数据 + 首尾页 email/IP 涂黑
│   ├── services.py         # complete_request/expire_request/reject_upload/force_close_request/tick
│   ├── routers/
│   │   ├── auth.py         # /auth/register|verify|login|logout
│   │   ├── me.py           # /me, /me/profile, /me/signin
│   │   ├── requests.py     # /requests + 6 状态机 endpoint + download + report
│   │   └── admin.py        # /admin{,/settings,/gift,/users,/requests,/reports}
│   ├── templates/
│   │   ├── base.html, index.html
│   │   ├── auth/{register,login,notice}.html
│   │   ├── me/{index,profile}.html
│   │   ├── requests/{lobby,new,detail}.html
│   │   └── admin/{_layout,index,settings,gift,users,requests,reports}.html
│   └── static/app.css
├── data/app.db             # SQLite (M3 测试数据已清,Anna 保留 200 积分)
├── uploads/                # raw + sanitized PDF (req{id}_h{helper}_{ts}.pdf{,.sanitized.pdf})
└── library/                # 沉淀的共享文献,按 paper id 编号 ({id}.pdf + {id}.sanitized.pdf)
```

### 已建的 7 张 ORM 表（`app/models.py`）

| 表 | 用途 |
|---|---|
| `users` | id/email/password_hash/nickname/points/is_admin/is_active/email_verified/created_at |
| `help_requests` | id/requester_id/title/authors/journal/year/bounty/status/claimed_by/expires/library_paper_id... |
| `attachments` | id/request_id/helper_id/original_path/sanitized_path/desensitized/size_bytes |
| `library_papers` | 完结后沉淀的共享库(其他人免费下) |
| `point_transactions` | append-only 积分账本 |
| `daily_signins` | unique(user_id, date) |
| `reports` | 举报 |
| `system_settings` | admin 后台可改的运行时配置 |

### 已部署
- **systemd 服务**：`lit-share.service`（uvicorn 跑在 127.0.0.1:10800）
- **Caddy 反代**：
  - `https://c.xpro.work/preview/lit/*` → :10800 (`handle_path` 剥前缀 + `header_up X-Forwarded-Prefix /preview/lit`，basic auth)
  - `https://hz.xpro.work/*` → :10800 (根路径，无 auth，不发 `X-Forwarded-Prefix` 头 → 应用 base_path 为空)
- **Dashboard 自动发现**：`https://c.xpro.work/dash` 会显示"→ 预览"链接到 lit-share

### 重要的踩坑记录
- ⚠️ **Base path 动态化（M2.5 改造）**：一个 uvicorn 实例要同时为 `c.xpro.work/preview/lit/*` 和 `hz.xpro.work/*` 服务。方案 = Caddy `handle_path` 剥前缀 + `header_up X-Forwarded-Prefix /preview/lit`；应用层中间件 `main.proxy_prefix` 把头值塞进 `scope["root_path"]`。`templating.base_path_of(request)` 是单一读取点；所有 cookie/redirect/template URL 都从它派生。`settings.APP_BASE_PATH` 已不再用于 FastAPI 构造（保留在 .env 里仅作文档参考，可忽略）
- ⚠️ 注意：**用 sudo 跑 `caddy validate` 会用 root 创建空日志文件，把后续 caddy 用户的写权限抢掉**。要么 `chown caddy:caddy /var/log/caddy/access-*.log`，要么干脆 `caddy validate --config /tmp/foo`（不要 sudo）
- ⚠️ uploadserver 把 `/upload` 当成自己内部路由，**不能挪到 /upload 路径下**——保持在根 `/`
- ⚠️ Caddyfile 里 bcrypt 哈希 **不要做 `$$` 转义**，直接写原文
- ⚠️ **passlib 1.7.4 + bcrypt 5.x 不兼容**（backend detect 用超长 secret 探测会抛 ValueError）。改成直接用 `bcrypt` 库。已从 requirements.txt 移除 passlib
- ⚠️ **SQLite + BigInteger PK 不会触发 ROWID autoincrement**，插入会 `NOT NULL: id` 失败。`models.BigInt = BigInteger().with_variant(Integer(), "sqlite")` 是修复方案——MySQL/PG 仍是 BIGINT

---

## 🎬 用户的决策（已确认）

### 业务规则
| 项 | 决策 |
|---|---|
| PDF 脱敏 | L2 实现 + **admin 后台开关切换"脱敏/原件"**（关键功能） |
| 求助超时 | 7 天（可配） |
| 48h 确认窗口 | 可主动驳回；超时自动确认 |
| 重复论文 | 完结后沉淀到共享文献库，他人免费下载（接受合规风险） |
| Admin 账号 | `.env` 的 `ADMIN_EMAIL`，**首次注册该邮箱自动 admin** |
| 通知 | MVP 仅站内消息；邮件留 phase 2 |
| 浏览大厅 | 未登录可看不可操作 |
| PDF 限制 | 50MB（可配） |
| 频率限制 | 单用户同期刊每月 ≤4 篇（可配） |
| 数据库 | SQLite 默认，**强制 SQLAlchemy 抽象兼容 MySQL/PostgreSQL** |
| 端口 | 内部 :10800，外部 `/preview/lit/` |
| 反爬 | 邮箱验证（先做 stub 走控制台，不接 SMTP） |

### 设计原则
- **几乎所有"数字"和"文案"都要进 `system_settings` 表**，admin 后台可改
- `.env` 只放 bootstrap 配置（SECRET、DATABASE_URL、ADMIN_EMAIL、SMTP）
- 业务默认值在 `.env` 里只是首次启动种子数据用

---

## 📊 Milestone 进度

| M | 状态 | 内容 |
|---|---|---|
| M0 | ✅ 完成 | 项目脚手架 + 部署反代 |
| M1 | ✅ 完成 | 用户系统 + 首页 + 个人中心壳 |
| M2 | ✅ 完成 | 求助发布 + 待应助大厅 + 签到 + 个人中心扩展 + 活动流 + 频率限制 |
| M2.5 | ✅ 完成 | 双域名支持 (hz 公开 + c 私有),per-request base_path |
| M3 | ✅ 完成 | 完整应助流转 + PDF 脱敏 + library 沉淀 + APScheduler 自动确认/过期 |
| M4 | ✅ 完成 | /admin 后台 + 运行时设置 + 积分赠送 + 用户/求助管理 + 举报机制(阈值自动关闭) |
| **M5** | **▶ 下一个** | SMTP 接入(替换 stub) + e2e 测试 + 部署优化 + 性能/安全打磨 |

### M1 交付物（已完成,冒烟测试通过）
- 注册 / 邮箱验证 stub（验证链接打印到 app.log，找它直接 `grep verify\?token /home/claude/projects/lit-share/app.log | tail`）
- 登录 / 登出 / itsdangerous 签名 cookie（`litshare_session`，path=`/preview/lit`，30 天）
- 密码哈希：`bcrypt` 直接调用，72 字节硬截断
- 首次注册 `ADMIN_EMAIL` 自动 `is_admin=True`
- `current_user` / `require_login` / `require_admin` 三个依赖（`app/security.py`）
- 未登录访问受保护 HTML 页 → 303 到 `/auth/login?next=...`；JSON 请求仍 401
- 个人中心 `/me`（资料卡片）+ `/me/profile`（改昵称）
- 首页 nav 接入登录态：未登录显示「登录/注册」，已登录显示昵称 + 登出按钮

### M2 交付物（已完成，冒烟测试通过）
- **签到** `POST /me/signin`：写 `daily_signins` (user+date 唯一 + Asia/Shanghai 日界)，award SIGNIN_POINTS，同日重复幂等
- **发布求助** `GET/POST /requests/new`：表单含 title/authors/journal/year/extra/bounty。提交校验 → 扣分 → INSERT help_requests(status=open, deadline=now+REQUEST_TIMEOUT_DAYS) → 写 ledger
- **大厅** `GET /requests`：列 status=open，按 created_at 倒序，PAGE_SIZE=20 分页。未登录可看不可发
- **求助详情** `GET /requests/{id}`：完整元数据 + 状态徽章 + 剩余时间。owner 看到「（我）」标记
- **频率限制**：同用户 + 同期刊（lowercase+strip）+ 同 CN 月 ≥ `SAME_JOURNAL_MONTHLY_LIMIT`（默认 4）时拒绝
- **/me 扩展**：积分卡片 + 签到按钮 + 我发布的(top10) + 我的应助(top10) + 最近积分流水(top8)
- **首页活动流**：从 point_transactions 取 publish/accept 最近 15 条，渲染"X 求助了《...》" / "X 完成了一次应助"

### 关键模块
- **`app/points.py`** — `adjust_points(db, user_id, delta, reason, ref_request_id, note, allow_negative=False)` 是积分变动唯一入口。会 row-lock user 后原子更新 users.points + 写 ledger 行。`InsufficientPoints` 异常需 catch + rollback。`REASON_*` 常量是所有 reason 字段的来源
- **`app/runtime_config.py`** — `get_setting(db, key, default, cast=str)`。所有"业务数字"都走它：`get_setting(db, "REQUEST_TIMEOUT_DAYS", settings.REQUEST_TIMEOUT_DAYS, cast=as_int)`。`.env` 是不可变默认值，DB 行覆盖；删行→恢复默认
- **`app/timekit.py`** — 时区分层：DB 存 naive UTC，用户侧用 `Asia/Shanghai`。签到的日期 key 用 `today_cn_str()`；剩余时间用 `humanize_remaining(deadline)`

### 全局重要约定
- **模板 URL 用 `{{ base_path }}` 前缀**——`base_path` 由 `templating.render(request, ...)` 注入,值来自 `request.scope["root_path"]`(per-request)
- 路由里的 redirect 用 `app.urls.redirect(request, "/path")`,**不要**写 `RedirectResponse(url=...)` 不带 base
- cookie 的 `set_session_cookie`/`clear_session_cookie` 必须传 `request`,内部从 scope.root_path 算 path
- 业务"数字 / 文案"用 `runtime_config.get_setting`,不要硬编码 `.env` 值
- 跨 DB:PK/FK 用 `models.BigInt`,不要直接 `BigInteger`
- 积分变动只能走 `points.adjust_points`,**绝对不要**直接 `user.points += x`

---

## 🛠️ 常用操作

```bash
# 看应用日志
sudo journalctl -u lit-share -f
# 或
tail -f /home/claude/projects/lit-share/app.log

# 重启应用
sudo systemctl restart lit-share

# 重新加载 Caddy
sudo systemctl reload caddy

# 本地测试(开发用)
cd /home/claude/projects/lit-share
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 10800

# 进 venv shell
cd /home/claude/projects/lit-share && source .venv/bin/activate

# 看任务列表（如果当前会话支持）
TaskList  # claude code 内置工具
```

---

## 🌐 整个基建一览（不是 lit-share 项目，但是协作基建）

| 服务 | URL | 监听 |
|---|---|---|
| Dashboard | https://c.xpro.work/dash | 静态文件,30s timer 刷新 |
| 文件上传 | https://c.xpro.work/ | 127.0.0.1:18000 uploadserver |
| 网页终端 | https://c.xpro.work/term/ | 127.0.0.1:17681 ttyd→tmux main |
| lit-share | https://c.xpro.work/preview/lit/ | 127.0.0.1:10800 uvicorn |

凭证：`anna` / 密码在 `/home/claude/apps/web.cred`

详细基建说明：`/home/claude/apps/OPS_GUIDE.md`

---

## 📦 用户已上传到 inbox 的文件

- `/home/claude/inbox/文献互助平台.md`（4.7KB，核心需求文档）

---

### M3 交付物（已完成,完整流程冒烟通过）

**状态机**
```
open ──claim──> claimed ──upload──> awaiting_confirm ──confirm──> completed
  │               │                       │       ╲
  │               └──release──> open      │        └─tick(48h)→ 自动 confirm
  │              (helper 放弃)             │
  │                                       └──reject──> open
  └─tick(7d 后)──> expired (退分给 requester)        (整个求助回大厅,helper 失去 claim)
```

**6 个 endpoint** (`app/routers/requests.py`)
- `POST /requests/{id}/claim` — 认领,owner 不能自认领
- `POST /requests/{id}/release` — 放弃,只允许 helper
- `POST /requests/{id}/upload` — multipart,校验 magic+size,上传时**总是**生成脱敏版,写 Attachment
- `POST /requests/{id}/confirm` — owner 确认,转积分给 helper,沉淀到 library(去重)
- `POST /requests/{id}/reject` — owner 驳回(可填原因记到 app log),清 helper claim,status 回 open
- `GET /requests/{id}/download` — completed 任何登录用户可下;awaiting_confirm 仅 owner+helper

**服务层** (`app/services.py`) — `complete_request`/`expire_request`/`reject_upload`/`tick`,**手动 endpoint 和 scheduler 共用**

**PDF 脱敏** (`app/pdf_redact.py`):
- 元数据清空(title/author/keywords/...) → 最可靠的 PII 通道
- 首尾页 email/IP 正则搜索 + PyMuPDF `add_redact_annot` 涂黑(永久毁原内容)
- 保存用 `garbage=4` 删孤儿对象,脱敏字节不可从 PDF stream 找回
- Caveat: search_for 文字断行 / 连字符会漏。M4 可加 OCR 或更激进扫描

**文件布局**:
- `uploads/req{id}_h{helper}_{ts}.pdf` — 原版
- `uploads/req{id}_h{helper}_{ts}.sanitized.pdf` — 脱敏版(总是生成)
- `library/{paper_id}.pdf` — 沉淀的原版
- `library/{paper_id}.sanitized.pdf` — 沉淀的脱敏版

**下载策略**: `PDF_DESENSITIZE_ENABLED` 控制**下发**哪个文件,不控制是否生成。admin 切换开关零延迟生效(M4 给 UI)

**APScheduler tick** (`app/main.py` lifespan):
- 60s 跑一次,每次扫两组: open & request_deadline 过期 → `expire_request`;awaiting_confirm & confirm_deadline 过期 → `complete_request`
- daemon thread,单 worker 安全。多 worker 时改外部 cron

**库去重** (`services.find_library_match`): 用 `func.lower(title)+lower(authors)+year` 完全匹配。命中复用 `library_paper_id`,不重复落盘

### 全局重要约定 (M3 新增)
- 积分变动只能走 `points.adjust_points`,**绝对不要**直接 `user.points += x`
- 状态机转换只能走 `services.*` helpers,不要在 route 里乱改 status — 否则手动/auto 路径会跑偏
- 上传后总是生成脱敏版,即使 admin 开关关闭。开关只控**下发**

---

### M4 交付物（已完成）

- **`/admin` 仪表板**: 4 项统计(用户/求助/待应助/举报) + PDF 开关当前态 prominent 显示 + 快捷链接
- **`/admin/settings`** (`app/routers/admin.py` `SETTING_KNOBS` 元数据驱动): 10 个 knob 表单,bool/int/str 三种渲染,`PDF_DESENSITIZE_ENABLED` 醒目 toggle 开关。每项可单独 `↺ 重置`(删 system_settings 行 → 恢复 .env 默认)。保存后 `runtime_config` 立刻读到,下次下载立即生效
- **`/admin/gift`**: target 接受 email 或 user_id,delta 允许负数,note 进 ledger。审计完整
- **`/admin/users`**: 分页 + 搜索(email/nickname like),`POST /admin/users/{id}/toggle-active` 启停。不能切换自己。被禁用用户登录会 401(security.current_user 检查 is_active)
- **`/admin/requests`**: 分页 + status 过滤 chip。`POST /admin/requests/{id}/close` 调 `services.force_close_request` 退分给 requester
- **`/admin/reports`**: 关联 request+reporter,显示原因,可忽略(`POST /admin/reports/{id}/dismiss` 删 Report 行)
- **`POST /requests/{id}/report`** (`routers/requests.py`): 门槛 = 累计被采纳应助 ≥ `REPORTER_MIN_HELPS`(默认 30,通过 `count(point_transactions where reason=help_accepted)` 测)。不能自举,不能重复举报。**累计 distinct reporter ≥ `REPORT_THRESHOLD` 自动 `force_close_request`**
- **detail.html 举报区**: viewer 够格(非 owner/helper + 达 MIN_HELPS)才显示 details/summary form
- **flash 系统**: `?msg=ok` (success) + `?err=...` (error),detail handler 接两个 alert 渲染

### 已知小坑 (M5 修)
- ⚠️ **Starlette URL-encoded form 用 latin-1 解码**,curl `-d "key=中文"` 会存成 mojibake。**浏览器没问题**(浏览器永远 percent-encode 非 ASCII)。脚本测试要用 `--data-urlencode`。M5 可以加全局 middleware 修复(读 body 后强制 UTF-8 重解析)
- ⚠️ 上传 PDF 大小下限 1024 字节,小到不合理的测试 PDF 会被拒。真实论文 PDF 永远 >> 1KB,不是问题

### 全局重要约定 (M4 新增)
- admin 路由统一在 `app/routers/admin.py`,prefix=`/admin`,所有路由通过 router-level `dependencies=[Depends(require_admin)]` 二次保护
- 任何 admin 触发的状态变更要走 `services.*` (gift 走 `adjust_points`,close 走 `force_close_request`),不要直接改字段
- 加新运行时配置:`app/routers/admin.py` 的 `SETTING_KNOBS` 加一行,settings.py 加默认值,业务代码用 `runtime_config.get_setting(db, "KEY", settings.KEY, cast=...)` 读

---

## 🚧 M5 路线图(下一个会话开干)

M0–M4 已经把功能闭环跑通了。M5 是**生产化**:把 stub 换成真实集成、补缺失的安全/可靠性,跑端到端自动化测试。

### 待开任务

1. **SMTP 接入** (`app/email_send.py`)
   - 现状: 注册邮箱验证只打 log。M5 改成读 `SMTP_HOST/PORT/USER/PASS/FROM`,有就走真发,无就 fallback 到 log stub
   - 用 stdlib `smtplib` + `email.message`,带 STARTTLS。失败要 fallback 而不是 500
   - 钩子点: `app/routers/auth.py` `_send_verify_email`

2. **CSRF 防护**
   - 当前依赖 SameSite=Lax cookie + POST。够吗?对积分敏感操作(gift/force_close/confirm) M5 加 token: `<input name="_csrf" value="{{ csrf_token }}">`,verify 时校验
   - 简单实现: 签名 cookie 写一个 token,form 渲染时注入,POST 时比对

3. **速率限制 / 反爬**
   - 注册 endpoint: 同 IP 1 分钟 ≥ 3 次拒绝
   - login: 失败 5 次锁 5 分钟
   - 用 stdlib + 进程内 dict 即可,多 worker 才需要 Redis

4. **端到端测试** (`tests/`)
   - pytest + httpx + 真起 uvicorn (或用 TestClient)
   - 覆盖: 注册→验证→登录;签到幂等;发布扣分+频率限制;claim/upload/confirm 完整闭环;reject 后重新认领;tick 触发自动确认/过期;admin gift/force_close/settings;举报阈值自动关闭
   - CI 上可以跑 sqlite,localhost 不挂 caddy

5. **数据库迁移**
   - 目前 `Base.metadata.create_all` 只创建不更新表。M5 接入 Alembic,M6 上 PostgreSQL 时无痛迁移
   - 第一次 alembic init + autogenerate 给当前 schema 打基线

6. **运维补强**
   - logrotate: app.log 现在无 size 限制,会无限增长。加 `logrotate` 配置或 Python logging.handlers.RotatingFileHandler
   - backup: SQLite 数据 + uploads/ + library/ 定期 rsync 到本地或 OSS
   - Prometheus metrics?(可选,M6)

7. **小修小补**
   - Starlette form latin-1 mojibake: 加 middleware 拦截 application/x-www-form-urlencoded 请求,把 body 重解析为 UTF-8
   - 日志 mojibake: `_handler = logging.StreamHandler(stream=sys.stdout)` + `stream.reconfigure(encoding='utf-8')`
   - "我的应助" 不显示被驳回的求助(claimed_by 已清空); M5 可以加 attachment 关联回查或 RejectLog 表
   - 上传 PDF 最小尺寸 1024 字节降到 256 字节(单页 PDF 不一定那么大)
   - admin force-close 是否补偿 helper(已上传的情况):目前不补偿,M5 视情况决定

### 关键设计点
- **SMTP fallback**: 真发邮件可能失败(限流/被拒/超时),不应让注册流程 500。失败时 catch 后 logger.warning + fallback 到 log 打印链接。用户可以看后台日志(M6 给 admin 加邮件队列 UI)
- **CSRF token**: 不要发明轮子,follow OWASP "synchronizer token pattern"。或者更新到 Starlette 的内建 (如果 0.41+ 有)
- **rate limit storage**: 进程内字典加 threading.Lock 就够 demo 用。生产想多 worker 时切 Redis
- **测试 DB 隔离**: 测试用临时 SQLite 文件(tmp_path fixture),不能共用 data/app.db
- **Alembic baseline**: `alembic revision --autogenerate -m "M0-M4 schema"`,然后 `alembic stamp head` 标记现有 DB 为已升级到 baseline

---

**下一个会话开干前**:
1. `cat /home/claude/projects/lit-share/HANDOFF.md`(你正在看)
2. `cd /home/claude/projects/lit-share && git log --oneline`
3. admin 账号 login demo 确认 /admin 后台跑通
4. 从 SMTP 接入开始(改动最隔离),然后写 pytest 把回归保护建好,再做 CSRF/rate-limit
