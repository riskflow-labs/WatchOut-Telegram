# WatchOut-Telegram

WatchOut Telegram 是一个用于 Telegram 群组、频道和私聊的消息采集与监控平台。它通过 Telegram 用户账号完成授权，支持目标导入、历史回爬、实时监听、消息检索、规则命中和通知推送，适合做公开信息留存、风险线索发现和日常监控。

## 主要功能

- **账号授权**：支持 Telegram `api_id`、`api_hash`、手机号验证码、二步密码、代理和健康检测。
- **目标管理**：支持 `@username`、`t.me`、邀请链接、`tg://resolve`、CSV、JSON 数组和账号 dialogs 同步。
- **消息采集**：支持实时监听、手动回爬、启动补采和定时补偿回爬。
- **消息归档**：保存来源、发送人、时间、文本、链接、媒体、阅读量、回复数、转发数和原始 payload。
- **检索筛选**：按关键词、目标、账号、发送人、时间、媒体、链接和风险等级筛选。
- **规则监控**：支持关键词、正则、产品词、信号词、排除词和命中等级。
- **通知推送**：支持 Telegram Bot、飞书、企业微信、钉钉和通用 Webhook，可先测试连通性再启用。
- **多语种翻译**：消息详情中可按需翻译原文，支持百度云、腾讯云等外部翻译接口，密钥由用户自行配置。
- 增强处理：支持平台语言配置、OCR 配置和媒体索引。
- 存储扩展：默认使用 PostgreSQL，可按需接入 JSONL、ClickHouse、Elasticsearch Sink。

## 快速开始

推荐用 Docker Compose 启动完整环境。

### 1. 准备配置

```bash
cp .env.example .env
```

Docker 模式下，`.env` 中数据库地址应使用容器服务名 `postgres`：

```text
WATCHOUT_TELEGRAM_DATABASE_URL=postgresql+psycopg://watchout:watchout_dev_password@postgres:5432/watchout_telegram
```

至少修改这几项：

```text
WATCHOUT_TELEGRAM_SECRET_KEY=replace-with-a-long-random-secret
WATCHOUT_TELEGRAM_DEFAULT_ADMIN_USERNAME=admin
WATCHOUT_TELEGRAM_DEFAULT_ADMIN_PASSWORD=admin123
POSTGRES_PASSWORD=change-me-too
```

### 2. 启动服务

```bash
docker compose up -d --build
```

访问地址：

```text
Frontend  http://127.0.0.1:5173
Backend   http://127.0.0.1:8000
Health    http://127.0.0.1:8000/health
```

后台登录账号来自 `.env`：

```text
username: admin
password: admin123
```

首次登录后，建议进入 **设置 -> 登录密码** 修改默认密码。

### 3. 常用命令

```bash
docker compose logs -f backend
docker compose logs -f frontend
docker compose down
```

## 界面预览

### 采集概览

概览页用于快速查看账号、目标、消息、命中和最近采集状态。日常巡检时，可以先从这里判断采集是否正常、失败任务是否增加，以及最近是否有高风险命中。

<p align="center">
  <img src="./pics/dashboard.png" alt="采集概览" width="760">
</p>

### 账号与目标

账号页负责 Telegram 授权、代理、健康检测和账号级监听；目标页负责批量导入、分组、启停监听、历史回爬和目标元数据同步。

<p align="center">
  <img src="./pics/account.png" alt="账号管理" width="760">
</p>

<p align="center">
  <img src="./pics/targets.png" alt="监控目标" width="760">
</p>

### 采集任务

任务页记录实时监听、手动回爬、定时回爬和失败原因，便于排查账号、代理、目标权限或 Telegram 连接问题。

<p align="center">
  <img src="./pics/task.png" alt="采集任务" width="760">
</p>

### 消息检索与翻译

消息检索页按目标、发送人、时间、关键词、媒体、链接和风险等级筛选消息。消息详情中可以查看原文、结构化字段、媒体归档、命中信息和互动数据。

<p align="center">
  <img src="./pics/messages.png" alt="消息检索" width="760">
</p>

对于跨语言群组或频道，消息详情支持**按需翻译**。配置翻译服务密钥后，可以在查看消息时手动触发翻译，译文会和原文一起展示，便于快速判断消息含义。

<p align="center">
  <img src="./pics/translation.png" alt="消息翻译" width="760">
</p>

### 规则与命中线索

规则页用于维护关键词、正则、产品词、信号词和排除词；命中线索页用于查看规则命中的消息、等级、分数、状态和后续处理结果。

<p align="center">
  <img src="./pics/rules.png" alt="监控规则" width="760">
</p>

<p align="center">
  <img src="./pics/rule-hits.png" alt="命中线索" width="760">
</p>

### 消息推送

推送页统一管理外部通知渠道。规则命中后，可以按渠道状态和推送策略分发到 Telegram Bot、飞书、企业微信、钉钉或通用 Webhook。

<p align="center">
  <img src="./pics/deliver.png" alt="推送渠道" width="760">
</p>

<table>
  <tr>
    <td width="50%" align="center">
      <strong>钉钉</strong><br>
      <img src="./pics/deliver-dingtalk.png" alt="钉钉推送" width="100%">
    </td>
    <td width="50%" align="center">
      <strong>飞书</strong><br>
      <img src="./pics/deliver-feishu.png" alt="飞书推送" width="100%">
    </td>
  </tr>
  <tr>
    <td width="50%" align="center">
      <strong>Telegram Bot</strong><br>
      <img src="./pics/deliver-telegram.png" alt="Telegram Bot 推送" width="100%">
    </td>
    <td width="50%" align="center">
      <strong>企业微信</strong><br>
      <img src="./pics/deliver-wecom.png" alt="企业微信推送" width="100%">
    </td>
  </tr>
</table>

## 基本使用流程

### 创建 Telegram 应用

先到 Telegram 开发者后台创建应用，拿到：

```text
api_id
api_hash
```

它们用于用户账号登录，不是 Telegram Bot Token。

### 添加采集账号

进入「账号管理」填写：

```text
api_id
api_hash
phone
proxy_url，可选
```

授权流程：

```text
发送验证码 -> 输入验证码 -> 验证
```

如果账号开启了二步密码，系统会继续要求输入二步密码。授权成功后，会在 session 目录生成 Telegram session 文件。

### 导入监控目标

进入「监控目标」粘贴一个或多个目标：

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

也可以在账号页同步当前账号已加入的群组、频道和私聊，再选择导入为目标。

### 回爬历史消息

目标列表和目标详情里都可以直接触发回爬。常用范围包含近 3 小时、近 1 天、近 1 周、近 1 个月；更长范围可展开选择，也可以自定义时间和消息上限。

API 示例：

```bash
TOKEN=$(curl -sS -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' \
  | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')

curl -sS -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"limit":5000,"since_days":30}' \
  http://127.0.0.1:8000/api/targets/1/backfill
```

参数说明：

```text
limit       最大拉取消息数
since_days  只拉取最近 N 天，遇到更早消息会停止
since_hours 只拉取最近 N 小时
```

### 启动实时监听

在账号页点击「启动账号监听」，或在目标页启动指定目标。实时监听只处理启动后的新消息，历史消息需要先执行回爬。

当前运行模型是：

```text
account_id -> one Telethon client -> many targets
```

同一账号下多个目标会复用一个 client，减少 session 锁冲突。

### 配置规则和通知

规则可以按三类组织：

```text
产品词：一级分类，例如 Telegram 账号、支付账号、特定品牌。
信号词：意图或风险，例如 出售、低价、封禁、找回、钓鱼。
排除词：降低误报，例如 官方公告、教程、无关广告。
```

消息入库后会进入规则匹配。命中后写入 `rule_hits`，并根据通知渠道配置推送到外部系统。

### 配置按需翻译

进入「设置」->「智能增强」配置翻译引擎和密钥。当前适合接入百度云、腾讯云等外部翻译接口；保存后可在消息详情中点击「翻译」按钮查看译文。

```text
翻译引擎：百度云 / 腾讯云
目标语言：跟随平台语言，或固定为中文、英文、日文、韩文等
密钥配置：使用你自己的服务密钥，不需要额外部署翻译服务
```

## 本地开发

不使用 Docker 时，可以分别启动后端和前端。

### 后端

```bash
cd backend
python3.11 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e .
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

采集测试时不建议使用 `--reload`，避免后端重启打断实时监听。

如果你已经有项目内虚拟环境：

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev -- --port 5173
```

构建检查：

```bash
cd frontend
npm run build
```

## 存储

### PostgreSQL

默认推荐 PostgreSQL。Docker Compose 会启动 `postgres` 服务，数据库配置来自 `.env`：

```text
POSTGRES_DB=watchout_telegram
POSTGRES_USER=watchout
POSTGRES_PASSWORD=watchout_dev_password
POSTGRES_PORT=5432
```

备份数据库：

```bash
docker compose exec postgres pg_dump -U watchout watchout_telegram > data/watchout_telegram_backup.sql
```

查看最近消息：

```bash
docker compose exec postgres psql -U watchout -d watchout_telegram \
  -c "select id,message_uid,source,message_id,message_kind,media_type,left(content,80)
      from telegram_messages
      order by id desc
      limit 10;"
```

### SQLite

SQLite 适合本地演示或轻量测试：

```text
WATCHOUT_TELEGRAM_DATABASE_URL=sqlite:///./data/app.db
```

### ClickHouse

启动 ClickHouse profile：

```bash
docker compose --profile clickhouse up -d --build
```

Compose 会自动执行：

```text
docs/clickhouse_telegram_messages.sql
```

在「设置」里开启 ClickHouse Sink：

```text
url: http://clickhouse:8123
database: watchout_telegram
table: telegram_messages
user: default
password: 与 .env 中 CLICKHOUSE_PASSWORD 一致
```

## 数据流

系统先把消息完整入库，再做规则匹配、增强处理和通知推送。即使不配置规则或通知，也可以作为 Telegram 消息采集、检索和归档工具使用。

```mermaid
flowchart TD
    A["账号授权"] --> B["监控目标"]
    B --> C["实时监听 / 历史回爬"]
    C --> D["消息标准化"]
    D --> E["telegram_messages"]
    E --> F["消息检索"]
    E --> G["规则匹配"]
    G --> H["rule_hits"]
    H --> I["通知推送"]
    E --> J["外部存储 Sink"]
```

## 技术栈

```text
Backend   FastAPI / Telethon / SQLAlchemy / APScheduler
Frontend  React / Vite / Mantine
Storage   PostgreSQL，SQLite 可用于轻量测试
Deploy    Docker Compose 或本地 Python + Node.js
```

## 项目建设

如果你有想法、建议、使用反馈，欢迎通过 **Issue** 或 **Pull Request** 参与项目建设。

也可以加入 Telegram 群一起讨论：

[https://t.me/+Dmh4Z2rtOv1hMTMx](https://t.me/+Dmh4Z2rtOv1hMTMx)
