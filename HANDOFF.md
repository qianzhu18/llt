# 📋 lit-share 项目交接文档

> 给下一个 Claude 会话：读完这份文档，你就有了所有上下文。
> 用户：Anna（annachow250815@gmail.com）
> 服务器：腾讯云 VM，公网 IP `43.173.104.146`，域名 `c.xpro.work`

---

## 🎯 立即要做的事

```
M0 ✅ / M1 ✅ / M2 ✅ → 下一步：M3（应助流转 + PDF 脱敏开关 + 48h 自动确认）
```

> 用户（Anna，`annachow250815@gmail.com`）**尚未注册**。Admin 名额留着等她首次注册时自动激活。

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

## ✅ 已完成：M0 + M1 + M2

### 技术栈（已确认）
- **Python 3.12** + **FastAPI 0.115** + **SQLAlchemy 2.0** + **Alembic**
- **Jinja2** SSR + **HTMX** + **Alpine.js** + 自写 **CSS（学术蓝）**，**不上 SPA**
- **APScheduler**（48h 自动确认 scheduler）
- **PyMuPDF**（PDF 处理，M3 用）
- **SQLite 默认**，`DATABASE_URL` 切换 MySQL/PG。已装 `pymysql`、`psycopg[binary]` 驱动

### 项目结构（M2 后）
```
/home/claude/projects/lit-share/
├── .env / .env.example
├── requirements.txt        # bcrypt 直接用,不走 passlib
├── run.sh
├── HANDOFF.md              # ← 你正在看的文件
├── .venv/
├── app/
│   ├── __init__.py
│   ├── main.py             # FastAPI 入口 + 首页活动流 + 401→login 跳转
│   ├── settings.py         # Pydantic Settings (bootstrap 配置)
│   ├── db.py               # 引擎工厂 + SessionLocal + get_db
│   ├── models.py           # ORM,BigInt 变体跨 DB
│   ├── security.py         # bcrypt + 签名 cookie + current_user/require_login
│   ├── templating.py       # render() 自动注入 base_path/current_user
│   ├── runtime_config.py   # get_setting(db, key, default, cast) — system_settings 读写
│   ├── points.py           # adjust_points + REASON_* 常量 + InsufficientPoints
│   ├── timekit.py          # Asia/Shanghai 时区 + humanize_remaining
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py         # /auth/register|verify|login|logout
│   │   ├── me.py           # /me, /me/profile, /me/signin
│   │   └── requests.py     # /requests, /requests/new, /requests/{id}
│   ├── templates/
│   │   ├── base.html, index.html
│   │   ├── auth/{register,login,notice}.html
│   │   ├── me/{index,profile}.html
│   │   └── requests/{lobby,new,detail}.html
│   └── static/app.css      # 学术蓝 + 表单 + 卡片 + 状态徽章 + 流水
├── data/app.db             # SQLite (M2 测试数据已清空)
└── uploads/                # M3 应助 PDF 落地点
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
- **Caddy 反代**：`https://c.xpro.work/preview/lit/*` → :10800（用 `handle` **不剥前缀**，配合 FastAPI 的 `root_path=/preview/lit`）
- **Dashboard 自动发现**：`https://c.xpro.work/dash` 会显示"→ 预览"链接到 lit-share

### 重要的踩坑记录
- ⚠️ Caddy `handle_path` 会剥前缀，但 FastAPI 的 `root_path` 期望前缀保留。**必须用 `handle` 而不是 `handle_path`** 给 lit-share 路由
- ⚠️ uploadserver 把 `/upload` 当成自己内部路由，**不能挪到 /upload 路径下**——保持在根 `/`
- ⚠️ Caddyfile 里 bcrypt 哈希 **不要做 `$$` 转义**，直接写原文
- ⚠️ **passlib 1.7.4 + bcrypt 5.x 不兼容**（backend detect 用超长 secret 探测会抛 ValueError）。改成直接用 `bcrypt` 库。已从 requirements.txt 移除 passlib
- ⚠️ **SQLite + BigInteger PK 不会触发 ROWID autoincrement**，插入会 `NOT NULL: id` 失败。`models.BigInt = BigInteger().with_variant(Integer(), "sqlite")` 是修复方案——MySQL/PG 仍是 BIGINT
- ⚠️ Cookie 的 `path` 必须等于 `APP_BASE_PATH`（`/preview/lit`），否则浏览器不会回传。`security.cookie_path()` 处理了
- ⚠️ Caddy 上有 basic auth（凭据 `anna` / `/home/claude/apps/web.cred`），curl 测试要 `--user`

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
| **M3** | **▶ 下一个** | 应助流转 + PDF 脱敏(开关) + 48h 自动确认 |
| M4 | ⬜ 待开 | 举报机制 + 管理后台 |
| M5 | ⬜ 待开 | 端到端测试 + 部署上线 |

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
- **模板 URL 必须用 `{{ base_path }}` 前缀**（反代 base 是 `/preview/lit`）
- redirect 在路由里：`(settings.APP_BASE_PATH or "") + "/path"` 给 RedirectResponse
- 业务"数字 / 文案"用 `runtime_config.get_setting`，不要硬编码 `.env` 值
- 跨 DB：PK/FK 用 `models.BigInt`，不要直接 `BigInteger`
- 积分变动只能走 `points.adjust_points`，**绝对不要**直接 `user.points += x`

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

## 🚧 M3 路线图（下一个会话开干）

核心是把求助从 `open` 流转到 `completed`，涉及 PDF 上传、脱敏、自动确认。

### 状态机
```
open ──claim──> claimed ──upload──> awaiting_confirm ──confirm──> completed
   │              │                     │            ╲
   │              └──release──> open    │             └─48h无操作→ 自动确认
   │              (放弃，可重新认领)      │
   │                                    └──reject──> claimed (任务回到应助者)
   └─REQUEST_TIMEOUT_DAYS 后未认领──> expired (退分给 requester)
```

### 待开任务
1. **`POST /requests/{id}/claim`**: 把 status open→claimed，记 claimed_by + claimed_at。同一用户不能认领自己的求助。已认领的不能再 claim
2. **`POST /requests/{id}/release`**: 应助者放弃，claimed→open，清 claimed_*
3. **`POST /requests/{id}/upload`** (multipart): 上传 PDF。校验 size ≤ MAX_PDF_SIZE_MB(默认 50)。落 uploads/{req_id}_{helper_id}_{ts}.pdf。读 `PDF_DESENSITIZE_ENABLED` 决定是否脱敏：用 PyMuPDF 重写元数据(author/title 清空) + 扫描首尾页文本去掉单位/邮箱/IP(正则匹配)，输出到 sanitized_path。写 Attachment 行，状态 claimed→awaiting_confirm，记 uploaded_at + confirm_deadline=now+CONFIRM_WINDOW_HOURS(默认 48)
4. **`POST /requests/{id}/confirm`**: 求助者确认接收。把 bounty `adjust_points` 转给 helper(reason=help_accepted)，**沉淀到 library_papers**（避免重复求助）。状态 awaiting_confirm→completed，写 library_paper_id 回 help_requests
5. **`POST /requests/{id}/reject`**: 求助者驳回。状态回到 claimed，clear uploaded_at/confirm_deadline (helper 可再次上传)
6. **`GET /requests/{id}/download`**: 已完结才允许下载。owner / helper / 已完结的所有人都能下。增 library_papers.download_count
7. **APScheduler 后台任务**: 每分钟扫一次：
   - `request_deadline < now` 且 status=open → 标 expired，退分 requester
   - `confirm_deadline < now` 且 status=awaiting_confirm → 自动确认 (走 confirm 逻辑)
8. **admin 切换 `PDF_DESENSITIZE_ENABLED`**: M4 才做 UI，M3 让 runtime_config 能读到就够了
9. **/me 扩展**: "我的应助" 区显示已认领但未上传的、待求助者确认的、被驳回的

### 关键设计点
- **PDF 脱敏开关**：用户已确认是「关键功能」，admin 后台可一键切换原件/脱敏。不要把脱敏硬编码到上传流程，先 `runtime_config.get_setting(db, "PDF_DESENSITIZE_ENABLED", settings.PDF_DESENSITIZE_ENABLED, as_bool)` 判断
- **库去重**：confirm 时 `LibraryPaper.title+authors+year` 作为查重 key（normalize 后），命中就不重复入库，直接关联现有 `library_paper_id`
- **下载策略**：M3 走 FastAPI `FileResponse` 直接发；流量大了再上 nginx X-Accel-Redirect
- **48h scheduler**: APScheduler 已在 requirements 里。在 `app/main.py` 启动 BackgroundScheduler，跑 `tick()` 任务，跨进程并发是单 uvicorn worker 所以不冲突。多 worker 再切到外部 cron

---

**下一个会话开干前**：
1. `cat /home/claude/projects/lit-share/HANDOFF.md`（你正在看）
2. `cat /home/claude/inbox/文献互助平台.md`（需求原文）
3. `cd /home/claude/projects/lit-share && git log --oneline`
4. 注册 anna 拿到 admin → 注册一个 helper 测试号 → 跑通完整一次求助
5. 开 M3 从 claim/release 两个最小动作入手
