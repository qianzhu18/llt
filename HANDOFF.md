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
M0 ✅ / M1 ✅ / M2 ✅ / M3 ✅ → 下一步：M4（举报机制 + 管理后台）
```

> **Admin 已就绪**：邮箱 `annachow250815@gmail.com` / 密码 `Wxhz123321!`（首次注册 demo 后改）。
> 初始 200 积分（admin_gift seed），可以直接发布求助。

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

## ✅ 已完成：M0 + M1 + M2 + M3

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
│   ├── services.py         # complete_request/expire_request/reject_upload/tick
│   ├── routers/
│   │   ├── auth.py         # /auth/register|verify|login|logout
│   │   ├── me.py           # /me, /me/profile, /me/signin
│   │   └── requests.py     # /requests + 6 个状态机 endpoint + download
│   ├── templates/
│   │   ├── base.html, index.html
│   │   ├── auth/{register,login,notice}.html
│   │   ├── me/{index,profile}.html
│   │   └── requests/{lobby,new,detail}.html
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
| **M4** | **▶ 下一个** | 举报机制 + 管理后台 (积分赠送/求助管理/用户管理/脱敏开关切换) |
| M5 | ⬜ 待开 | 端到端测试 + 部署优化 + 邮件 SMTP 接入 |

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

## 🚧 M4 路线图(下一个会话开干)

核心是**管理后台 + 举报闭环**。前端基本是表格 + 按钮,后端是 `require_admin` 保护的路由 + `runtime_config.set_setting`。

### 待开任务
1. **`/admin` 后台首页 + 导航** (require_admin):积分赠送 / 用户列表 / 求助管理 / 运行时配置 四个区
2. **积分赠送 `POST /admin/gift`**: 输入 email / user_id + delta + reason note,调 `adjust_points(reason=REASON_ADMIN_GIFT)`。完整审计入 ledger
3. **用户列表 `/admin/users`**: 分页,显示 email/nickname/points/is_active/created_at;支持 toggle is_active(禁用恶意用户)
4. **求助管理 `/admin/requests`**: 分页,任意状态过滤;支持 force-close(退分给 requester,reason=publish_refund_closed),即 `force_close_request(db, req)` (新增到 services.py)
5. **运行时配置 `/admin/settings`**: 表单展示所有 settings.py 的字段(`SIGNIN_POINTS`/`REQUEST_TIMEOUT_DAYS`/`CONFIRM_WINDOW_HOURS`/`MAX_PDF_SIZE_MB`/`SAME_JOURNAL_MONTHLY_LIMIT`/`REPORT_THRESHOLD`/`REPORTER_MIN_HELPS`/**`PDF_DESENSITIZE_ENABLED`**);保存调 `runtime_config.set_setting`。删行恢复 .env 默认
6. **举报机制** (Report model 已建):
   - `POST /requests/{id}/report` (Form): 应助被采纳 ≥ REPORTER_MIN_HELPS 才允许举报,reason 必填。写 reports 行
   - 同一 request 累计举报 ≥ REPORT_THRESHOLD 自动 `force_close_request` (在 report endpoint 或 services.tick 里)
   - admin 后台 `/admin/reports` 查看
7. **/admin/library** (可选): 沉淀文献列表 + 下载量;允许从 library 删除某篇

### 关键设计点
- **是否允许 admin 弹层切换脱敏开关**:这是用户明确要求的关键功能。`/admin/settings` 必须把 `PDF_DESENSITIZE_ENABLED` 做成 prominent toggle,改后立刻生效(下次 download 即看到效果)
- **`reporter` 限制**: `REPORTER_MIN_HELPS` 是「累计被采纳过 N 次的用户才能举报」。查询条件: `func.count(distinct(help_requests.id)) where claimed_by=user and status=completed >= N`
- **审计日志**: admin 操作(gift/force-close/settings change)都应写一条 ledger 或 admin_audit_log。M4 至少保证积分变动有 ledger 行,settings 变动有 system_settings.updated_at
- **Force-close 注意**: 如果 status 是 claimed / awaiting_confirm,可能涉及 helper 已经工作过。是否给 helper 也补偿?**默认不**,但 admin 可以另起 gift 操作

---

**下一个会话开干前**:
1. `cat /home/claude/projects/lit-share/HANDOFF.md`(你正在看)
2. `cat /home/claude/inbox/文献互助平台.md`(需求原文)
3. `cd /home/claude/projects/lit-share && git log --oneline`
4. 用 admin 账号登录 demo,看看现状
5. 从 `/admin/settings` (改运行时配置) 开始,因为它最简单且能立即被其他功能复用
