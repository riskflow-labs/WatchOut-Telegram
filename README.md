# WatchOut Telegram

WatchOut Telegram 是 WatchOut 系列下的 Telegram 消息采集与检索平台。它基于 Telegram 用户账号采集群组、频道消息，支持批量导入目标、历史回爬、实时监听、本地归档、消息检索、规则命中和通知扩展。

> 当前仓库不包含任何 Telegram session、数据库、账号配置或采集数据。运行数据默认保存在 `data/` 或 `backend/data/`，这些目录已被 `.gitignore` 排除。

## 功能特性

- Telegram 账号登录：支持验证码和二步密码流程。
- 批量目标导入：支持 `@username`、`t.me/username`、`telegram.me/username`、邀请链接、`tg://resolve`、CSV、JSON 数组等格式。
- 账号级采集：同一个 Telegram 账号只保留一个 Telethon client，可监听多个群组/频道，减少 session 锁冲突。
- 历史回爬：支持手动回爬、按最近 N 天回爬、定时自动回爬。
- 标准化入库：为每条消息生成 `message_uid` 和 `content_md5`。
- 消息类型标记：支持 `text`、`photo`、`video`、`document`、`audio`、`sticker`、`service` 等类型。
- 本地检索：按关键词、目标、发送人、时间范围、媒体、链接、风险等级检索。
- 规则匹配：关键词/正则规则命中后写入命中记录。
- 通知扩展：支持 Telegram Bot、Webhook、飞书机器人等通知通道配置。
- 存储扩展：默认 SQLite，可选 JSONL、ClickHouse、Elasticsearch Sink。

## 技术栈

```text
Backend:  FastAPI + Telethon + SQLAlchemy + APScheduler
Frontend: React + Vite + Mantine
Storage:  SQLite by default, optional ClickHouse / JSONL / Elasticsearch
```

## 目录结构

```text
WatchOut-Telegram/
  backend/                 FastAPI 后端
  backend/app/             API、模型、采集 runtime、回爬 worker
  backend/data/            本地后端运行数据，已忽略
  frontend/                React + Mantine 前端
  data/                    Docker Compose 运行数据，已忽略
  docs/                    架构、ClickHouse 建表 SQL、阶段方案
  docker-compose.yml       本地容器启动配置
```

## Docker 部署

Docker Compose 是推荐部署方式。运行数据会写入项目根目录的 `data/`，包括 SQLite 数据库、Telegram session、日志和可选 ClickHouse 数据。

### 1. 准备配置

```bash
cp .env.example .env
```

建议至少修改：

```text
WATCHOUT_TELEGRAM_SECRET_KEY=replace-with-a-long-random-secret
WATCHOUT_TELEGRAM_DEFAULT_ADMIN_USERNAME=admin
WATCHOUT_TELEGRAM_DEFAULT_ADMIN_PASSWORD=change-me-before-first-run
VITE_API_BASE=http://127.0.0.1:8000/api
```

如果部署到服务器，请把 `VITE_API_BASE` 改成后端公网地址，例如：

```bash
VITE_API_BASE=https://your-domain.example/api
```

同时把 CORS 加入 `.env`：

```text
WATCHOUT_TELEGRAM_CORS_ORIGINS=["https://your-domain.example","http://127.0.0.1:5173"]
```

### 2. 启动服务

```bash
docker compose up -d --build
```

访问：

```text
Frontend: http://127.0.0.1:5173
Backend:  http://127.0.0.1:8000
Health:   http://127.0.0.1:8000/health
```

查看日志：

```bash
docker compose logs -f backend
docker compose logs -f frontend
```

停止：

```bash
docker compose down
```

升级：

```bash
git pull
docker compose up -d --build
```

### 3. 数据目录

```text
data/app.db            SQLite 主库
data/sessions/         Telegram session
data/logs/             日志目录
data/clickhouse/       可选 ClickHouse 数据
```

这些文件含有账号 session、采集数据和运行状态，已经被 `.gitignore` 排除。

备份 SQLite：

```bash
docker compose exec backend python - <<'PY'
import sqlite3
src = sqlite3.connect('/app/data/app.db')
dst = sqlite3.connect('/app/data/app_backup.db')
src.backup(dst)
dst.close()
src.close()
PY
```

### 4. 可选 ClickHouse

启动 ClickHouse：

```bash
docker compose --profile clickhouse up -d --build
```

Compose 会自动执行：

```text
docs/clickhouse_telegram_messages.sql
```

然后在「存储设置」中开启 ClickHouse Sink：

```text
url: http://clickhouse:8123
database: watchout_telegram
table: telegram_messages
user: default
password: 与 .env 中 CLICKHOUSE_PASSWORD 一致
```

## 本地开发启动

不使用 Docker 时，可以本地分别启动后端和前端。

### 1. 后端

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e .
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

采集测试时不建议使用 `--reload`，避免后端重启打断实时监听。

### 2. 前端

```bash
cd frontend
npm install
npm run dev -- --port 5173
```

访问：

```text
http://127.0.0.1:5173
```

## 使用流程

### 1. 添加 Telegram 账号

进入「账号」页面，填写 Telegram API 信息：

```text
api_id
api_hash
phone
proxy_url，可选
```

点击：

```text
发送验证码 -> 输入验证码 -> 验证
```

如果账号开启了二步密码，再输入二步密码完成授权。

### 2. 导入采集目标

进入「采集目标」页面，支持粘贴多种格式：

```text
@example_group
example_group
https://t.me/example_group
telegram.me/example_group
https://t.me/+invite_hash
https://t.me/joinchat/invite_hash
tg://resolve?domain=example_group
["https://t.me/example_group", {"target":"telegram.me/another_group"}]
```

也可以在账号页同步当前账号已加入的群组/频道 dialogs，再导入为目标。

### 3. 历史回爬

单个目标回爬：

```bash
TOKEN=$(curl -sS -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"change-me-before-first-run"}' \
  | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')

curl -sS -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"limit":5000,"since_days":30}' \
  http://127.0.0.1:8000/api/targets/1/backfill
```

参数说明：

```text
limit: 最大拉取消息数
since_days: 只拉取最近 N 天，遇到更早消息会停止
```

### 4. 实时监听

在账号页点击「启动账号监听」，或在目标页点击「加入监听」。实时监听只采集新消息，历史消息需要通过回爬补齐。

当前 runtime 是账号级模型：

```text
account_id -> one Telethon client -> many targets
```

同一个账号下多个目标不会各自创建独立 client。

## 标准消息字段

核心去重字段：

```text
message_uid = md5("tg:{source_id}:{message_id}")
content_md5 = md5(content)
```

推荐含义：

```text
message_uid: Telegram 消息级唯一 ID
content_md5: 内容级去重 ID
data_id: 默认等于 content_md5
similar_id: 默认等于 content_md5
```

主要字段：

```text
channel, source, source_id, source_type, sub_channel
message_id, event_time, insert_time
sender_id, sender_username, sender_name
content, content_md5, data_id, similar_id, original_content
message_kind, media_type, media_count, links_json, raw_payload
views_count, replies_count, forwards_count
risk_level, score, hit, keyword_type, keyword_source, status
```

消息类型：

```text
message_kind: text / photo / video / document / audio / sticker / poll / service / media / empty
media_type: none / image / video / file / audio / sticker / poll
```

## 定时回爬

配置项：

```text
WATCHOUT_TELEGRAM_BACKFILL_ENABLED=true
WATCHOUT_TELEGRAM_BACKFILL_INTERVAL_SECONDS=1800
WATCHOUT_TELEGRAM_BACKFILL_STARTUP_DELAY_SECONDS=120
WATCHOUT_TELEGRAM_BACKFILL_LIMIT_PER_TARGET=50
```

定时回爬按账号串行执行，避免同一个 Telegram session 被并发回爬任务争用。

## 存储配置

默认使用 SQLite：

```text
WATCHOUT_TELEGRAM_DATABASE_URL=sqlite:///./data/app.db
```

可选 ClickHouse 建表 SQL：

```bash
clickhouse-client < docs/clickhouse_telegram_messages.sql
```

可在「存储设置」里开启 ClickHouse、JSONL、Elasticsearch Sink。

## 数据验证

查看最近消息：

```bash
sqlite3 backend/data/app.db \
  "select id,message_uid,content_md5,source,message_id,message_kind,media_type,substr(content,1,80)
   from telegram_messages
   order by id desc
   limit 10;"
```

验证 MD5 字段：

```bash
sqlite3 backend/data/app.db \
  "select count(*) total,
          count(distinct message_uid) unique_uid,
          sum(case when length(message_uid)=32 then 1 else 0 end) valid_uid,
          sum(case when length(content_md5)=32 then 1 else 0 end) valid_content_md5
   from telegram_messages;"
```

查看回爬错误：

```bash
curl -sS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8000/api/runs/errors?limit=20"
```

## 安全说明

不要提交以下文件：

```text
.env
*.session
*.db / *.sqlite / *.sqlite3
*.db-wal / *.db-shm
messages.jsonl
采集导出的 CSV / JSON
```

这些文件已经在 `.gitignore` 中排除。
