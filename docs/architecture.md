# 架构说明

## 当前架构

```text
React Mantine 采集工作台
  -> FastAPI
  -> SQLite
  -> Telethon sessions
  -> Telegram
```

MVP 默认不连接 ClickHouse/ELK。SQLite 保存：

- 管理员用户
- Telegram 账号和登录状态
- Telegram session 文件路径
- 监听目标
- 规则
- 消息
- 规则匹配
- 通知渠道和投递记录
- 运行记录

## 存储策略

第一阶段：

```text
SQLite = primary store
```

第二阶段：

```text
SQLite = 配置和运行状态
JSONL = 本地原始导出
ClickHouse = 大体量分析
Elasticsearch = 全文检索
```

## 运行时

每个 target 可以启动一个 Telethon listener。后续多账号调度会把 target 分配给健康账号，并根据 FloodWait、断线、账号状态动态退避。
