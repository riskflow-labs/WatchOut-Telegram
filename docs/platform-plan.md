# WatchOut Telegram 三阶段建设说明

## 1. 项目定位

WatchOut Telegram 是从当前 ELK 验证链路中拆出来的独立 Telegram 消息采集平台。

参考取舍：

- Riniba/TelegramMonitor：Web 管理、账号登录、目标启停、规则、消息归档、通知、运行状态。
- NextBSpiders：历史采集、本地归档、批量目标。
- TelegramMessage：轻量监听、Docker 化、匹配后通知。

当前实现优先对齐 Riniba 的产品形态，但技术栈按本地已有能力选择：

```text
FastAPI + Telethon + SQLAlchemy + SQLite + React/Vite + Mantine
```

第一版不依赖 ClickHouse/ELK；ClickHouse、Elasticsearch、JSONL 都作为可选 Sink 预留和实现。

## 2. 第一阶段 MVP

已实现：

- 管理员登录：`/api/auth/login`
- Telegram 账号创建：`/api/telegram/accounts`
- Telegram 发送验证码：`/api/telegram/accounts/{id}/send-code`
- Telegram 验证码登录：`/api/telegram/accounts/{id}/verify-code`
- Telegram 二步密码登录：`/api/telegram/accounts/{id}/verify-password`
- 账号 session 持久化：`data/sessions`
- 账号级启动/停止监听：`/api/telegram/accounts/{id}/start`、`/api/telegram/accounts/{id}/stop`
- 监听目标管理：`/api/targets`
- 目标启动/停止：`/api/targets/{id}/start`、`/api/targets/{id}/stop`
- 关键词规则管理：`/api/rules`
- 消息归档查询：`/api/messages`
- 规则匹配记录：`/api/hits`
- Telegram Bot / Webhook / 飞书机器人通知：`/api/notifications`
- SQLite 本地持久化：`data/app.db`
- Docker Compose：`docker-compose.yml`
- React 管理台：`frontend/src/main.jsx`

MVP 数据表：

```text
users
telegram_accounts
telegram_login_flows
telegram_targets
monitor_rules
telegram_messages
rule_hits
notification_channels
notification_deliveries
monitor_runs
app_settings
```

## 3. 第二阶段稳定性和外部存储

已实现基础版本：

- 多账号分配策略：未绑定账号的 target 自动选择第一个 authorized active account。
- FloodWait 退避：监听 runtime 捕获 `FloodWaitError` 并 sleep。
- 断线自动重连：RPC/Connection 异常后延迟重试。
- 目标健康状态：`/api/targets/health`
- 通知失败重试：`/api/notifications/retry-failed`
- JSONL Sink：`/api/storage/config` 可开启。
- ClickHouse Sink：`/api/storage/config` 可开启。
- Elasticsearch Sink：`/api/storage/config` 可开启。

后续可增强：

- 更细的账号负载均衡。
- per-account FloodWait 预算。
- 通知指数退避和最大重试次数。
- Sink 初始化 SQL / index template 自动创建。
- 后台页面编辑 storage sink config。

## 4. 第三阶段消息分析

已实现本地启发式版本：

- TG 链接提取：`/api/intelligence/tg-links`
- 群关系图谱：`/api/intelligence/group-graph`
- 采集摘要：`/api/intelligence/risk-summary`
- 日报：`/api/intelligence/daily-report`
- 前端存储设置页展示链接提取、采集日报和数据源状态。

后续可增强：

- 接 OpenAI 或本地模型生成更自然的 AI 摘要。
- 消息聚类、相似消息归并。
- 群/频道实体画像。
- 自动把发现的 t.me 链接加入候选目标池。
- 周报、月报、规则匹配趋势。

## 5. 采集合规边界

默认只做账号授权范围内的消息采集、归档、检索和内部通知，不做自动私信或主动打招呼。

推荐工作流：

```text
采集消息 -> 规则匹配 -> Telegram Bot / Webhook / 飞书通知 -> 人工查看 -> 手动处理
```

如果后续增加主动触达，需要强限频、白名单、人工确认和完整审计。
