# 📋 lit-share 项目交接文档

> 给下一个 Claude 会话：读完这份文档，你就有了所有上下文。
> 用户：Anna（annachow250815@gmail.com）
> 服务器：腾讯云 VM，公网 IP `43.173.104.146`，域名 `c.xpro.work`

---

## 🎯 立即要做的事（用户说的）

```
1. git init   # 在 /home/claude/projects/lit-share/
2. 首次 commit M0 baseline
3. 进入 M1：用户系统 + 首页 + 个人中心壳
```

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

## ✅ 已完成：M0（项目脚手架）

### 技术栈（已确认）
- **Python 3.12** + **FastAPI 0.115** + **SQLAlchemy 2.0** + **Alembic**
- **Jinja2** SSR + **HTMX** + **Alpine.js** + 自写 **CSS（学术蓝）**，**不上 SPA**
- **APScheduler**（48h 自动确认 scheduler）
- **PyMuPDF**（PDF 处理，M3 用）
- **SQLite 默认**，`DATABASE_URL` 切换 MySQL/PG。已装 `pymysql`、`psycopg[binary]` 驱动

### 项目结构
```
/home/claude/projects/lit-share/
├── .env / .env.example      # SECRET_KEY/ADMIN_EMAIL/DATABASE_URL/业务默认值
├── requirements.txt
├── run.sh                   # 本地一键 dev 启动
├── HANDOFF.md               # ← 你正在看的文件
├── .venv/                   # 已 pip install -r requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py             # FastAPI 入口,root_path=/preview/lit
│   ├── settings.py         # Pydantic Settings
│   ├── db.py               # 引擎工厂(SQLite/MySQL/PG 适配)
│   ├── models.py           # 7 张表 ORM(下方详列)
│   ├── templates/
│   │   ├── base.html
│   │   └── index.html
│   └── static/app.css
├── data/app.db             # SQLite,表已建空
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
| **M1** | **▶ 下一个** | 用户系统 + 首页 + 个人中心壳 |
| M2 | ⬜ 待开 | 求助发布 + 待应助大厅 + 签到 |
| M3 | ⬜ 待开 | 应助流转 + PDF脱敏(开关) + 自动确认 |
| M4 | ⬜ 待开 | 举报机制 + 管理后台 + 频率限制 |
| M5 | ⬜ 待开 | 端到端测试 + 部署上线 |

### M1 范围（下一步）
- 用户注册（邮箱 + 密码 + nickname）
- 邮箱验证（stub：把验证链接打印到控制台/log，不实际发邮件）
- 登录/登出/会话（itsdangerous 签名 cookie）
- 密码哈希用 `passlib[bcrypt]`
- 首次注册 `ADMIN_EMAIL` 自动 `is_admin=True`
- 个人中心壳页面：显示 email、nickname、points、is_admin、注册时间
- 首页加 "登录/注册" 按钮（已登录则显示 nickname）
- 路由：`/auth/register`、`/auth/login`、`/auth/logout`、`/me`、`/me/profile`
- **重要：所有模板里的 URL 必须用 `{{ base_path }}` 前缀**，因为反代 base path 是 `/preview/lit`

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

**下一个 Claude 会话开干前**：
1. `cat /home/claude/projects/lit-share/HANDOFF.md`（你正在做的事）
2. `cat /home/claude/inbox/文献互助平台.md`（需求原文）
3. `cd /home/claude/projects/lit-share && git init && git add -A && git commit -m "M0: 项目脚手架"`
4. 开 M1
