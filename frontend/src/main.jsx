import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ActionIcon,
  Alert,
  Anchor,
  AppShell,
  Badge,
  Box,
  Burger,
  Button,
  Card,
  Checkbox,
  Container,
  Divider,
  Drawer,
  FileButton,
  Grid,
  Group,
  MantineProvider,
  Modal,
  NavLink,
  NumberInput,
  Paper,
  PasswordInput,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Textarea,
  ThemeIcon,
  Title,
  Tooltip
} from "@mantine/core";
import { Notifications, notifications } from "@mantine/notifications";
import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import {
  IconAlertTriangle,
  IconBell,
  IconBrandTelegram,
  IconChevronLeft,
  IconChevronRight,
  IconCircleCheck,
  IconCloudDownload,
  IconDatabase,
  IconDownload,
  IconFileExport,
  IconHistory,
  IconKey,
  IconLayoutDashboard,
  IconListCheck,
  IconLogout,
  IconMessageSearch,
  IconPlayerPlay,
  IconRefresh,
  IconRobot,
  IconSearch,
  IconSend,
  IconSettings,
  IconSquare,
  IconTarget,
  IconTerminal,
  IconUpload,
  IconUsers,
  IconX
} from "@tabler/icons-react";
import { api, clearToken, getToken, login } from "./lib/api";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000/api";

const navItems = [
  { id: "dashboard", label: "采集概览", short: "概览", icon: IconLayoutDashboard, subtitle: "账号、目标、消息归档和最近采集状态" },
  { id: "messages", label: "消息检索", short: "检索", icon: IconMessageSearch, subtitle: "搜索、过滤、查看和导出已采集消息" },
  { id: "accounts", label: "Telegram 账号", short: "账号", icon: IconKey, subtitle: "接入账号并完成验证码登录" },
  { id: "targets", label: "采集目标", short: "目标", icon: IconTarget, subtitle: "配置群组、频道、私聊等采集来源" },
  { id: "runs", label: "采集任务", short: "任务", icon: IconHistory, subtitle: "查看实时监听和历史回填记录" },
  { id: "rules", label: "关键词规则", short: "规则", icon: IconListCheck, subtitle: "用关键词或正则标记消息并触发通知" },
  { id: "matches", label: "规则匹配", short: "匹配", icon: IconCircleCheck, subtitle: "查看规则匹配结果和关联消息" },
  { id: "notifications", label: "通知转发", short: "通知", icon: IconBell, subtitle: "配置 Telegram Bot、Webhook 或飞书通知" },
  { id: "settings", label: "存储设置", short: "存储", icon: IconSettings, subtitle: "查看本地存储和可选外部数据源状态" }
];

const statusColor = (value = "") => {
  const normalized = String(value).toLowerCase();
  if (["authorized", "running", "listening", "success", "delivered", "active", "enabled"].includes(normalized)) return "teal";
  if (["error", "failed", "unauthorized", "disabled"].includes(normalized)) return "red";
  if (["backfilling", "starting", "code_sent", "password_required", "pending", "open"].includes(normalized)) return "yellow";
  if (normalized.startsWith("l")) return Number(normalized.slice(1)) >= 2 ? "orange" : "blue";
  if (normalized.startsWith("r")) return Number(normalized.slice(1)) >= 2 ? "orange" : "blue";
  return "gray";
};

const statusLabel = (value = "") => ({
  listening: "已加入监听",
  running: "运行中",
  idle: "未监听",
  backfilling: "回填中",
  success: "成功",
  failed: "失败",
  error: "异常",
  authorized: "已授权",
  unauthorized: "未授权",
  created: "未登录",
  code_sent: "待验证码",
  password_required: "待二步密码"
}[String(value).toLowerCase()] || value || "-");

function StatusBadge({ value, label }) {
  return <Badge color={statusColor(value)} variant="light">{label || statusLabel(value)}</Badge>;
}

function MatchLevel({ value }) {
  return <StatusBadge value={`L${value || 0}`} label={`L${value || 0}`} />;
}

function notifyError(error) {
  notifications.show({ color: "red", title: "操作失败", message: error?.message || String(error) });
}

function notifyOk(message) {
  notifications.show({ color: "teal", title: "操作完成", message });
}

function formatTime(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function firstNonEmpty(...values) {
  return values.find((value) => value !== undefined && value !== null && String(value).trim() !== "") || "-";
}

function Login({ onDone }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      await login(username, password);
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-shell">
      <Paper className="login-hero" radius={0}>
        <Box>
          <Badge color="cyan" variant="light" mb="md">WatchOut Series</Badge>
          <Title order={1}>WatchOut Telegram</Title>
          <Text className="login-subtitle">面向 Telegram 群组、频道和私聊的消息采集、归档与检索工作台。</Text>
        </Box>
        <SimpleGrid cols={3} spacing="sm" className="login-stats">
          <Paper p="md" radius="lg"><Text fw={800}>SQLite</Text><Text size="xs">本地优先</Text></Paper>
          <Paper p="md" radius="lg"><Text fw={800}>Telethon</Text><Text size="xs">账号采集</Text></Paper>
          <Paper p="md" radius="lg"><Text fw={800}>Export</Text><Text size="xs">CSV / JSON</Text></Paper>
        </SimpleGrid>
        <div className="signal-lines">
          <span />
          <span />
          <span />
        </div>
      </Paper>

      <Paper className="login-card" radius="xl" shadow="xl" p={34} withBorder>
        <Group mb="xl">
          <ThemeIcon size={48} radius="lg" color="cyan">
            <IconBrandTelegram size={28} />
          </ThemeIcon>
          <Box>
            <Title order={2}>登录控制台</Title>
            <Text c="dimmed" size="sm">进入 TG 采集平台</Text>
          </Box>
        </Group>
        <form onSubmit={submit}>
          <Stack>
            <TextInput label="用户名" value={username} onChange={(event) => setUsername(event.currentTarget.value)} required size="md" />
            <PasswordInput label="密码" value={password} onChange={(event) => setPassword(event.currentTarget.value)} required size="md" />
            {error ? <Alert color="red" icon={<IconAlertTriangle size={16} />}>{error}</Alert> : null}
            <Button type="submit" loading={loading} fullWidth size="md" leftSection={<IconSend size={16} />}>登录</Button>
          </Stack>
        </form>
        <Text size="xs" c="dimmed" mt="lg">首次运行请按 `.env.example` 设置管理员账号和密码。</Text>
      </Paper>
    </div>
  );
}

function KpiCard({ icon: Icon, label, value, sub, color = "cyan" }) {
  return (
    <Card withBorder radius="lg" p="lg" className="kpi-card">
      <Group justify="space-between" align="flex-start">
        <Stack gap={3}>
          <Text size="sm" c="dimmed">{label}</Text>
          <Title order={2}>{value}</Title>
          <Text size="xs" c="dimmed">{sub}</Text>
        </Stack>
        <ThemeIcon color={color} variant="light" radius="lg" size={44}>
          <Icon size={23} />
        </ThemeIcon>
      </Group>
    </Card>
  );
}

function Dashboard({ data, setActiveTab }) {
  const d = data.dashboard || {};
  const links = data.intelligence?.links || [];
  const latestMessages = data.messages.slice(0, 6);
  const running = data.runs.filter((run) => ["running", "backfilling", "starting"].includes(String(run.status).toLowerCase()));
  return (
    <Stack>
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 5 }}>
        <KpiCard icon={IconBrandTelegram} label="Telegram 账号" value={`${d.active_accounts || 0}/${d.accounts || 0}`} sub="已授权 / 总数" />
        <KpiCard icon={IconTarget} label="采集目标" value={`${d.enabled_targets || 0}/${d.targets || 0}`} sub="启用 / 总数" color="blue" />
        <KpiCard icon={IconDatabase} label="归档消息" value={d.messages || 0} sub="SQLite 本地存储" color="indigo" />
        <KpiCard icon={IconListCheck} label="规则匹配" value={`${d.open_hits || 0}/${d.hits || 0}`} sub="待处理 / 总匹配" color="orange" />
        <KpiCard icon={IconHistory} label="采集任务" value={d.runs || 0} sub="监听与回填历史" color="grape" />
      </SimpleGrid>

      <Grid>
        <Grid.Col span={{ base: 12, xl: 7 }}>
          <Card withBorder radius="lg" p="lg">
            <Group justify="space-between" mb="md">
              <Box>
                <Title order={3}>最近采集消息</Title>
                <Text size="sm" c="dimmed">最新归档内容，点击消息检索可进一步过滤与导出。</Text>
              </Box>
              <Button variant="light" leftSection={<IconSearch size={16} />} onClick={() => setActiveTab("messages")}>打开检索</Button>
            </Group>
            <Stack gap="xs">
              {latestMessages.map((message) => (
                <Paper key={message.id} withBorder radius="md" p="sm">
                  <Group justify="space-between" wrap="nowrap">
                    <Box className="grow">
                      <Group gap="xs">
                        <Text fw={700}>{message.source}</Text>
                        <Badge variant="light">{message.message_kind}</Badge>
                        {message.links?.length ? <Badge variant="light" color="blue">链接 {message.links.length}</Badge> : null}
                      </Group>
                      <Text size="sm" lineClamp={1}>{message.content || `[${message.message_kind}]`}</Text>
                    </Box>
                    <Text size="xs" c="dimmed" miw={150} ta="right">{formatTime(message.event_time)}</Text>
                  </Group>
                </Paper>
              ))}
              {!latestMessages.length ? <EmptyState text="暂无采集消息。" /> : null}
            </Stack>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, xl: 5 }}>
          <Stack>
            <Card withBorder radius="lg" p="lg">
              <Group justify="space-between" mb="md">
                <Title order={3}>快速操作</Title>
                <Badge color="cyan" variant="light">Workspace</Badge>
              </Group>
              <SimpleGrid cols={2}>
                <Button variant="light" onClick={() => setActiveTab("targets")}>添加采集目标</Button>
                <Button variant="light" onClick={() => setActiveTab("accounts")}>接入账号</Button>
                <Button variant="light" onClick={() => setActiveTab("runs")}>查看任务</Button>
                <Button variant="light" onClick={() => setActiveTab("rules")}>配置规则</Button>
              </SimpleGrid>
            </Card>
            <Card withBorder radius="lg" p="lg">
              <Title order={3} mb="md">链接提取</Title>
              <Stack gap={8}>
                {links.slice(0, 6).map((item) => (
                  <Group key={item.link} justify="space-between" wrap="nowrap">
                    <Anchor size="sm" href={item.link} target="_blank" truncate="end">{item.link}</Anchor>
                    <Badge variant="light">{item.count}</Badge>
                  </Group>
                ))}
                {!links.length ? <Text c="dimmed" size="sm">暂无 t.me 链接。</Text> : null}
              </Stack>
            </Card>
            <Card withBorder radius="lg" p="lg">
              <Title order={3} mb="md">运行中的任务</Title>
              {running.length ? running.slice(0, 4).map((run) => (
                <Group key={run.id} justify="space-between" mb="xs">
                  <Text size="sm">target #{run.target_id || "-"}</Text>
                  <StatusBadge value={run.status} />
                </Group>
              )) : <Text size="sm" c="dimmed">当前没有运行中的采集任务。</Text>}
            </Card>
          </Stack>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}

function Accounts({ accounts, reload }) {
  const [form, setForm] = useState({ label: "", api_id: "", api_hash: "", phone: "", proxy_url: "" });
  const [codeById, setCodeById] = useState({});
  const [passwordById, setPasswordById] = useState({});

  async function create(event) {
    event.preventDefault();
    try {
      await api("/telegram/accounts", { method: "POST", body: { ...form, api_id: Number(form.api_id) } });
      setForm({ label: "", api_id: "", api_hash: "", phone: "", proxy_url: "" });
      notifyOk("账号已新增");
      await reload();
    } catch (error) {
      notifyError(error);
    }
  }

  async function action(id, path, body = {}) {
    try {
      await api(`/telegram/accounts/${id}/${path}`, { method: "POST", body });
      notifyOk("账号操作已提交");
      await reload();
    } catch (error) {
      notifyError(error);
    }
  }

  return (
    <Stack>
      <Card withBorder radius="lg" p="lg">
        <Title order={3} mb="md">添加 Telegram 账号</Title>
        <form onSubmit={create}>
          <Grid align="end">
            <Grid.Col span={{ base: 12, md: 2 }}><TextInput label="标签" value={form.label} onChange={(e) => setForm({ ...form, label: e.currentTarget.value })} /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 2 }}><TextInput label="api_id" value={form.api_id} onChange={(e) => setForm({ ...form, api_id: e.currentTarget.value })} required /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 3 }}><TextInput label="api_hash" value={form.api_hash} onChange={(e) => setForm({ ...form, api_hash: e.currentTarget.value })} required /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 2 }}><TextInput label="手机号" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.currentTarget.value })} required /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 2 }}><TextInput label="代理" placeholder="socks5://127.0.0.1:7890" value={form.proxy_url} onChange={(e) => setForm({ ...form, proxy_url: e.currentTarget.value })} /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 1 }}><Button type="submit" fullWidth>新增</Button></Grid.Col>
          </Grid>
        </form>
      </Card>

      <SimpleGrid cols={{ base: 1, lg: 2 }}>
        {accounts.map((account) => (
          <Card withBorder radius="lg" key={account.id} p="lg">
            <Group justify="space-between" align="flex-start">
              <Stack gap={4}>
                <Title order={4}>{account.label || account.phone}</Title>
                <Text size="sm" c="dimmed">{account.phone}</Text>
                <Text size="xs" c="dimmed">session: {account.session_name}</Text>
              </Stack>
              <StatusBadge value={account.status} />
            </Group>
            {account.last_error ? <Alert mt="md" color="red">{account.last_error}</Alert> : null}
            <Divider my="md" />
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <Button variant="light" onClick={() => action(account.id, "send-code")}>发送验证码</Button>
              <Group gap="xs" wrap="nowrap">
                <TextInput placeholder="验证码" value={codeById[account.id] || ""} onChange={(e) => setCodeById({ ...codeById, [account.id]: e.currentTarget.value })} />
                <Button onClick={() => action(account.id, "verify-code", { code: codeById[account.id] || "" })}>验证</Button>
              </Group>
              <Group gap="xs" wrap="nowrap">
                <PasswordInput placeholder="二步密码" value={passwordById[account.id] || ""} onChange={(e) => setPasswordById({ ...passwordById, [account.id]: e.currentTarget.value })} />
                <Button onClick={() => action(account.id, "verify-password", { password: passwordById[account.id] || "" })}>二步</Button>
              </Group>
              <Group gap="xs">
                <Button leftSection={<IconPlayerPlay size={14} />} onClick={() => action(account.id, "start")}>启动账号监听</Button>
                <Button color="gray" variant="light" leftSection={<IconSquare size={14} />} onClick={() => action(account.id, "stop")}>停止账号监听</Button>
              </Group>
            </SimpleGrid>
          </Card>
        ))}
      </SimpleGrid>
    </Stack>
  );
}

function Targets({ targets, accounts, reload, openMessages }) {
  const sampleInput = "@example_group\nhttps://t.me/example_channel\nhttps://t.me/+AbCdEf123\nhttps://t.me/joinchat/AbCdEf123";
  const [bulkText, setBulkText] = useState(sampleInput);
  const [singleForm, setSingleForm] = useState({ target: "", title: "", account_id: "", target_type: "group" });
  const [bulkOptions, setBulkOptions] = useState({ account_id: "", target_type: "auto", onlyReady: true, autoJoinInvites: false });
  const [parseResult, setParseResult] = useState(null);
  const [parsing, setParsing] = useState(false);
  const [importing, setImporting] = useState(false);
  const [syncingDialogs, setSyncingDialogs] = useState(false);
  const [checkingTargets, setCheckingTargets] = useState(false);
  const [selectedTarget, setSelectedTarget] = useState(null);
  const accountOptions = accounts.map((account) => ({ value: String(account.id), label: account.label || account.phone }));
  const authorizedAccountOptions = accounts
    .filter((account) => account.status === "authorized")
    .map((account) => ({ value: String(account.id), label: account.label || account.phone }));
  const accountName = (id) => accounts.find((account) => account.id === id)?.label || accounts.find((account) => account.id === id)?.phone || "-";
  const targetStats = {
    total: targets.length,
    running: targets.filter((target) => ["listening", "running"].includes(String(target.status).toLowerCase())).length,
    idle: targets.filter((target) => String(target.status).toLowerCase() === "idle").length,
    failed: targets.filter((target) => String(target.status).toLowerCase() === "error").length
  };

  async function create(event) {
    event.preventDefault();
    try {
      await api("/targets", { method: "POST", body: { ...singleForm, account_id: singleForm.account_id ? Number(singleForm.account_id) : null } });
      setSingleForm({ target: "", title: "", account_id: "", target_type: "group" });
      notifyOk("采集目标已新增");
      await reload();
    } catch (error) {
      notifyError(error);
    }
  }

  async function targetAction(id, action, body = {}) {
    try {
      await api(`/targets/${id}/${action}`, { method: "POST", body });
      notifyOk("目标操作已提交");
      await reload();
    } catch (error) {
      notifyError(error);
    }
  }

  async function parseBulkTargets() {
    setParsing(true);
    try {
      const result = await api("/targets/parse", {
        method: "POST",
        body: {
          text: bulkText,
          account_id: bulkOptions.account_id ? Number(bulkOptions.account_id) : null,
          target_type: bulkOptions.target_type
        }
      });
      setParseResult(result);
      notifyOk(`解析完成：可导入 ${result.importable}，重复 ${result.duplicated}，错误 ${result.invalid}`);
    } catch (error) {
      notifyError(error);
    } finally {
      setParsing(false);
    }
  }

  async function importBulkTargets() {
    if (!parseResult?.items?.length) {
      notifyError(new Error("请先解析预览"));
      return;
    }
    const items = bulkOptions.onlyReady
      ? parseResult.items.filter((item) => ["ready", "accessible"].includes(item.status))
      : parseResult.items;
    setImporting(true);
    try {
      const result = await api("/targets/bulk", { method: "POST", body: { items } });
      notifyOk(`导入完成：新增 ${result.created_count}，跳过 ${result.skipped_count}`);
      setParseResult(null);
      await reload();
    } catch (error) {
      notifyError(error);
    } finally {
      setImporting(false);
    }
  }

  async function checkBulkTargets() {
    if (!parseResult?.items?.length) {
      notifyError(new Error("请先解析预览或同步账号群组"));
      return;
    }
    const items = parseResult.items.filter((item) => ["ready", "accessible"].includes(item.status));
    if (!items.length) {
      notifyError(new Error("没有可校验目标"));
      return;
    }
    setCheckingTargets(true);
    try {
      const result = await api("/targets/check-bulk", {
        method: "POST",
        body: {
          items,
          account_id: bulkOptions.account_id ? Number(bulkOptions.account_id) : null,
          auto_join_invites: Boolean(bulkOptions.autoJoinInvites)
        }
      });
      const byKey = new Map(result.items.map((item) => [`${item.line}-${item.raw}`, item]));
      const nextItems = parseResult.items.map((item) => {
        const checked = byKey.get(`${item.line}-${item.raw}`);
        if (!checked) return item;
        return {
          ...item,
          status: checked.status === "accessible" ? "accessible" : "invalid",
          category: checked.category,
          reason: checked.reason,
          title: checked.title || item.title,
          target_type: checked.target_type || item.target_type
        };
      });
      setParseResult({
        items: nextItems,
        total: nextItems.length,
        importable: nextItems.filter((item) => ["ready", "accessible"].includes(item.status)).length,
        duplicated: nextItems.filter((item) => item.status === "duplicate").length,
        invalid: nextItems.filter((item) => item.status === "invalid").length
      });
      notifyOk(`校验完成：可访问 ${result.accessible}，失败 ${result.failed}`);
    } catch (error) {
      notifyError(error);
    } finally {
      setCheckingTargets(false);
    }
  }

  async function syncAccountDialogs() {
    const accountId = bulkOptions.account_id || authorizedAccountOptions[0]?.value;
    if (!accountId) {
      notifyError(new Error("请先选择一个已授权账号"));
      return;
    }
    setSyncingDialogs(true);
    try {
      const dialogs = await api(`/telegram/accounts/${accountId}/dialogs`);
      const items = dialogs.map((dialog, index) => ({
        line: index + 1,
        raw: dialog.target,
        status: dialog.status,
        reason: dialog.reason,
        detected_type: "dialog",
        target_type: dialog.target_type,
        target: dialog.target,
        normalized_target: dialog.normalized_target,
        title: dialog.title,
        account_id: Number(accountId),
        duplicate_of: null
      }));
      setBulkOptions({ ...bulkOptions, account_id: accountId });
      setParseResult({
        items,
        total: items.length,
        importable: items.filter((item) => item.status === "ready").length,
        duplicated: 0,
        invalid: items.filter((item) => item.status === "invalid").length
      });
      notifyOk(`已同步 ${items.length} 个群组/频道，确认后可导入`);
    } catch (error) {
      notifyError(error);
    } finally {
      setSyncingDialogs(false);
    }
  }

  async function importTargetFile(file) {
    if (!file) return;
    const text = await file.text();
    if (file.name.toLowerCase().endsWith(".csv")) {
      const lines = text
        .split(/\r?\n/)
        .map((line) => line.split(",").map((item) => item.trim()).find(Boolean) || "")
        .filter(Boolean);
      setBulkText(lines.join("\n"));
    } else {
      setBulkText(text);
    }
    setParseResult(null);
    notifyOk(`已读取文件：${file.name}`);
  }

  async function exportTargets(format) {
    try {
      const response = await fetch(`${API_BASE}/targets/export?format=${format}`, {
        headers: { Authorization: `Bearer ${getToken()}` }
      });
      if (!response.ok) throw new Error("导出目标失败");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `watchout-telegram-targets.${format}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      notifyError(error);
    }
  }

  const parseStatusColor = (status) => {
    if (["ready", "accessible"].includes(status)) return "teal";
    if (status === "duplicate") return "blue";
    if (status === "invalid") return "red";
    return "gray";
  };

  return (
    <Stack>
      <SimpleGrid cols={{ base: 2, md: 4 }}>
        <KpiCard icon={IconTarget} label="全部目标" value={targetStats.total} sub="已配置采集来源" />
        <KpiCard icon={IconPlayerPlay} label="监听中" value={targetStats.running} sub="已加入账号监听" color="teal" />
        <KpiCard icon={IconHistory} label="空闲" value={targetStats.idle} sub="可回填或启动" color="gray" />
        <KpiCard icon={IconAlertTriangle} label="失败" value={targetStats.failed} sub="需要查看错误" color="red" />
      </SimpleGrid>

      <Card withBorder radius="lg" p="lg" className="target-import-card">
        <Group justify="space-between" align="flex-start" mb="md">
          <Box>
            <Title order={3}>批量导入目标</Title>
            <Text size="sm" c="dimmed">每行一个目标，支持 @群名、t.me 分享链接、邀请链接、joinchat 链接和消息链接。</Text>
          </Box>
          <Group gap="xs">
            <FileButton onChange={importTargetFile} accept=".txt,.csv,text/plain,text/csv">
              {(props) => <Button {...props} variant="light" leftSection={<IconUpload size={15} />}>导入文件</Button>}
            </FileButton>
            <Button variant="light" leftSection={<IconUsers size={15} />} onClick={syncAccountDialogs} loading={syncingDialogs}>同步已加入</Button>
            <Button variant="light" leftSection={<IconFileExport size={15} />} onClick={() => exportTargets("csv")}>导出 CSV</Button>
            <Button variant="light" leftSection={<IconCloudDownload size={15} />} onClick={() => exportTargets("json")}>导出 JSON</Button>
          </Group>
        </Group>
        <Grid align="stretch">
          <Grid.Col span={{ base: 12, lg: 7 }}>
            <Textarea
              minRows={10}
              autosize
              label="粘贴目标"
              description="@example、https://t.me/example、t.me/+invite、tg://join?invite=..."
              value={bulkText}
              onChange={(event) => setBulkText(event.currentTarget.value)}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, lg: 5 }}>
            <Stack h="100%" justify="space-between">
              <SimpleGrid cols={{ base: 1, sm: 2 }}>
                <Select label="绑定账号" placeholder="自动选择" data={accountOptions} value={bulkOptions.account_id} onChange={(value) => setBulkOptions({ ...bulkOptions, account_id: value || "" })} clearable />
                <Select
                  label="目标类型"
                  data={[{ value: "auto", label: "自动识别" }, { value: "group", label: "群组" }, { value: "channel", label: "频道" }, { value: "private", label: "私聊" }]}
                  value={bulkOptions.target_type}
                  onChange={(value) => setBulkOptions({ ...bulkOptions, target_type: value || "auto" })}
                />
              </SimpleGrid>
              <Paper withBorder radius="md" p="md" className="format-help">
                <Text fw={700} mb="xs">支持格式</Text>
                <Text size="sm" c="dimmed">@group_name / t.me/group_name / telegram.me/group_name</Text>
                <Text size="sm" c="dimmed">t.me/+hash / t.me/joinchat/hash / tg://join?invite=hash</Text>
                <Text size="sm" c="dimmed">t.me/group/123 会提取为 group；t.me/c/... 会进入待确认。</Text>
              </Paper>
              <Group justify="space-between">
                <Stack gap={4}>
                  <Checkbox label="仅导入可导入项" checked={bulkOptions.onlyReady} onChange={(event) => setBulkOptions({ ...bulkOptions, onlyReady: event.currentTarget.checked })} />
                  <Checkbox label="校验邀请链接时自动加入" checked={Boolean(bulkOptions.autoJoinInvites)} onChange={(event) => setBulkOptions({ ...bulkOptions, autoJoinInvites: event.currentTarget.checked })} />
                </Stack>
                <Group>
                  <Button variant="light" onClick={parseBulkTargets} loading={parsing}>解析预览</Button>
                  <Button variant="light" onClick={checkBulkTargets} loading={checkingTargets} disabled={!parseResult?.importable}>校验可访问性</Button>
                  <Button onClick={importBulkTargets} loading={importing} disabled={!parseResult?.importable}>确认导入</Button>
                </Group>
              </Group>
            </Stack>
          </Grid.Col>
        </Grid>
        {parseResult ? (
          <Card withBorder radius="md" mt="lg" p="md" className="parse-preview">
            <Group justify="space-between" mb="sm">
              <Group>
                <Badge color="teal">可导入 {parseResult.importable}</Badge>
                <Badge color="blue">重复 {parseResult.duplicated}</Badge>
                <Badge color="red">错误 {parseResult.invalid}</Badge>
              </Group>
              <Text size="sm" c="dimmed">共解析 {parseResult.total} 行</Text>
            </Group>
            <Table.ScrollContainer minWidth={920}>
              <Table verticalSpacing="sm">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>状态</Table.Th>
                    <Table.Th>原始输入</Table.Th>
                    <Table.Th>识别类型</Table.Th>
                    <Table.Th>标准目标</Table.Th>
                    <Table.Th>导入类型</Table.Th>
                    <Table.Th>分类</Table.Th>
                    <Table.Th>说明</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {parseResult.items.map((item) => (
                    <Table.Tr key={`${item.line}-${item.raw}`}>
                      <Table.Td><Badge color={parseStatusColor(item.status)} variant="light">{item.status}</Badge></Table.Td>
                      <Table.Td><Text size="sm" maw={260} truncate="end">{item.raw}</Text></Table.Td>
                      <Table.Td>{item.detected_type}</Table.Td>
                      <Table.Td><Text size="sm" maw={220} truncate="end">{item.normalized_target || "-"}</Text></Table.Td>
                      <Table.Td><Badge variant="light">{item.target_type}</Badge></Table.Td>
                      <Table.Td><Text size="sm" c="dimmed">{item.category || "-"}</Text></Table.Td>
                      <Table.Td><Text size="sm" c={item.status === "invalid" ? "red" : "dimmed"}>{item.reason || "可导入"}</Text></Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </Card>
        ) : null}
      </Card>

      <Card withBorder radius="lg" p="lg">
        <Group justify="space-between" mb="md">
          <Box>
            <Title order={3}>单个目标快速新增</Title>
            <Text size="sm" c="dimmed">适合临时添加一个群组、频道或私聊来源。</Text>
          </Box>
        </Group>
        <form onSubmit={create}>
          <Grid align="end">
            <Grid.Col span={{ base: 12, md: 4 }}><TextInput label="t.me / username / chat id" value={singleForm.target} onChange={(e) => setSingleForm({ ...singleForm, target: e.currentTarget.value })} required /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 2 }}><TextInput label="标题" value={singleForm.title} onChange={(e) => setSingleForm({ ...singleForm, title: e.currentTarget.value })} /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 2 }}><Select label="类型" data={[{ value: "group", label: "群组" }, { value: "channel", label: "频道" }, { value: "private", label: "私聊" }]} value={singleForm.target_type} onChange={(value) => setSingleForm({ ...singleForm, target_type: value || "group" })} /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 3 }}><Select label="账号" placeholder="自动选择" data={accountOptions} value={singleForm.account_id} onChange={(value) => setSingleForm({ ...singleForm, account_id: value || "" })} clearable /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 1 }}><Button type="submit" fullWidth>新增</Button></Grid.Col>
          </Grid>
        </form>
      </Card>

      <Card withBorder radius="lg" p="lg">
        <Group justify="space-between" mb="md">
          <Box>
            <Title order={3}>目标列表</Title>
            <Text size="sm" c="dimmed">表格适合大量目标管理，详情和操作集中在每一行。</Text>
          </Box>
        </Group>
        <Table.ScrollContainer minWidth={1100}>
          <Table verticalSpacing="sm" highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>目标名称</Table.Th>
                <Table.Th>标准目标</Table.Th>
                <Table.Th>类型</Table.Th>
                <Table.Th>账号</Table.Th>
                <Table.Th>状态</Table.Th>
                <Table.Th>最后消息</Table.Th>
                <Table.Th>最近错误</Table.Th>
                <Table.Th>操作</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {targets.map((target) => (
                <Table.Tr key={target.id}>
                  <Table.Td>
                    <Text fw={700}>{target.title || target.target}</Text>
                    <Text size="xs" c="dimmed" maw={260} truncate="end">{target.target}</Text>
                  </Table.Td>
                  <Table.Td><Text size="sm" maw={220} truncate="end">{target.normalized_target}</Text></Table.Td>
                  <Table.Td><Badge variant="light">{target.target_type}</Badge></Table.Td>
                  <Table.Td><Text size="sm" maw={160} truncate="end">{accountName(target.account_id)}</Text></Table.Td>
                  <Table.Td>
                    <Group gap={6}>
                      <StatusBadge value={target.status} />
                      <Badge variant="light" color={target.enabled ? "teal" : "gray"}>{target.enabled ? "启用" : "暂停"}</Badge>
                    </Group>
                  </Table.Td>
                  <Table.Td>{formatTime(target.last_message_at)}</Table.Td>
                  <Table.Td><Text size="sm" c={target.last_error ? "red" : "dimmed"} maw={220} truncate="end">{target.last_error || "-"}</Text></Table.Td>
                  <Table.Td>
                    <Group gap="xs" wrap="nowrap">
                      <Button size="xs" leftSection={<IconPlayerPlay size={13} />} onClick={() => targetAction(target.id, "start")}>加入监听</Button>
                      <Button size="xs" variant="light" leftSection={<IconHistory size={13} />} onClick={() => targetAction(target.id, "backfill", { limit: 20 })}>回填</Button>
                      <Button size="xs" color="gray" variant="light" leftSection={<IconSquare size={13} />} onClick={() => targetAction(target.id, "stop")}>移出监听</Button>
                      <Button size="xs" variant="subtle" onClick={() => openMessages(target.id)}>消息</Button>
                      <Button size="xs" variant="subtle" onClick={() => setSelectedTarget(target)}>详情</Button>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        {!targets.length ? <EmptyState text="暂无采集目标。可以先在上方批量粘贴导入。" /> : null}
      </Card>

      <Drawer opened={Boolean(selectedTarget)} onClose={() => setSelectedTarget(null)} title="采集目标详情" position="right" size="lg">
        {selectedTarget ? (
          <Stack>
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <Text>目标 ID：#{selectedTarget.id}</Text>
              <Text>绑定账号：{accountName(selectedTarget.account_id)}</Text>
              <Text>标题：{selectedTarget.title || "-"}</Text>
              <Text>类型：{selectedTarget.target_type}</Text>
              <Text>原始目标：{selectedTarget.target}</Text>
              <Text>标准目标：{selectedTarget.normalized_target}</Text>
              <Text>状态：{statusLabel(selectedTarget.status)}</Text>
              <Text>最后消息：{formatTime(selectedTarget.last_message_at)}</Text>
            </SimpleGrid>
            <Paper withBorder p="md" radius="md">
              <Text fw={700} mb="xs">错误 / 备注</Text>
              <Text className="message-content" c={selectedTarget.last_error ? "red" : "dimmed"}>{selectedTarget.last_error || "暂无错误。"}</Text>
            </Paper>
            <Group>
              <Button leftSection={<IconPlayerPlay size={14} />} onClick={() => targetAction(selectedTarget.id, "start")}>加入账号监听</Button>
              <Button variant="light" leftSection={<IconHistory size={14} />} onClick={() => targetAction(selectedTarget.id, "backfill", { limit: 20 })}>回填20条</Button>
              <Button variant="subtle" leftSection={<IconMessageSearch size={14} />} onClick={() => openMessages(selectedTarget.id)}>查看消息</Button>
            </Group>
          </Stack>
        ) : null}
      </Drawer>
    </Stack>
  );
}

function Rules({ rules, reload }) {
  const [form, setForm] = useState({ name: "", match_type: "contains", patterns: "", risk_level: 1, priority: 100 });

  async function create(event) {
    event.preventDefault();
    try {
      await api("/rules", {
        method: "POST",
        body: {
          ...form,
          patterns: form.patterns.split(",").map((item) => item.trim()).filter(Boolean),
          risk_level: Number(form.risk_level),
          priority: Number(form.priority)
        }
      });
      setForm({ name: "", match_type: "contains", patterns: "", risk_level: 1, priority: 100 });
      notifyOk("关键词规则已新增");
      await reload();
    } catch (error) {
      notifyError(error);
    }
  }

  return (
    <Stack>
      <Card withBorder radius="lg" p="lg">
        <Title order={3} mb="md">关键词规则构建器</Title>
        <form onSubmit={create}>
          <Grid align="end">
            <Grid.Col span={{ base: 12, md: 3 }}><TextInput label="名称" value={form.name} onChange={(e) => setForm({ ...form, name: e.currentTarget.value })} required /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 2 }}><Select label="匹配方式" data={[{ value: "contains", label: "包含" }, { value: "keyword", label: "关键词" }, { value: "regex", label: "正则" }, { value: "exact", label: "精确匹配" }]} value={form.match_type} onChange={(value) => setForm({ ...form, match_type: value || "contains" })} /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 3 }}><TextInput label="关键词" placeholder="逗号分隔" value={form.patterns} onChange={(e) => setForm({ ...form, patterns: e.currentTarget.value })} /></Grid.Col>
            <Grid.Col span={{ base: 6, md: 1 }}><NumberInput label="等级" min={0} max={5} value={form.risk_level} onChange={(value) => setForm({ ...form, risk_level: value || 0 })} /></Grid.Col>
            <Grid.Col span={{ base: 6, md: 1 }}><NumberInput label="优先级" min={1} value={form.priority} onChange={(value) => setForm({ ...form, priority: value || 100 })} /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 2 }}><Button type="submit" fullWidth>新增规则</Button></Grid.Col>
          </Grid>
        </form>
      </Card>
      <Card withBorder radius="lg" p="lg">
        <Table.ScrollContainer minWidth={760}>
          <Table verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr><Table.Th>规则</Table.Th><Table.Th>方式</Table.Th><Table.Th>关键词</Table.Th><Table.Th>优先级</Table.Th><Table.Th>匹配等级</Table.Th></Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rules.map((rule) => (
                <Table.Tr key={rule.id}>
                  <Table.Td><Text fw={600}>{rule.name}</Text></Table.Td>
                  <Table.Td>{rule.match_type}</Table.Td>
                  <Table.Td><Text size="sm" lineClamp={1}>{rule.patterns.join(", ")}</Text></Table.Td>
                  <Table.Td>{rule.priority}</Table.Td>
                  <Table.Td><MatchLevel value={rule.risk_level} /></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
    </Stack>
  );
}

function Messages({ messages, targets, reload, filters, setFilters }) {
  const [selected, setSelected] = useState(null);
  const targetOptions = targets.map((target) => ({ value: String(target.id), label: target.title || target.target }));

  async function search(event) {
    event.preventDefault();
    await reload(filters);
  }

  function queryString(format) {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== "" && value !== null && value !== undefined) params.set(key, value);
    });
    params.set("format", format);
    params.set("limit", "5000");
    return params.toString();
  }

  async function exportMessages(format) {
    try {
      const response = await fetch(`${API_BASE}/messages/export?${queryString(format)}`, {
        headers: { Authorization: `Bearer ${getToken()}` }
      });
      if (!response.ok) throw new Error("导出失败");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `watchout-telegram-messages.${format}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      notifyError(error);
    }
  }

  return (
    <Stack>
      <Card withBorder radius="lg" p="lg">
        <form onSubmit={search}>
          <Grid align="end">
            <Grid.Col span={{ base: 12, md: 4 }}><TextInput label="关键词" placeholder="消息内容、来源、发送人、链接" value={filters.keyword} onChange={(e) => setFilters({ ...filters, keyword: e.currentTarget.value })} /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 2 }}><Select label="目标" placeholder="全部目标" data={targetOptions} value={filters.target_id} onChange={(value) => setFilters({ ...filters, target_id: value || "" })} clearable /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 2 }}><TextInput label="来源" value={filters.source} onChange={(e) => setFilters({ ...filters, source: e.currentTarget.value })} /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 2 }}><TextInput label="发送人" value={filters.sender} onChange={(e) => setFilters({ ...filters, sender: e.currentTarget.value })} /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 2 }}><NumberInput label="条数" min={1} max={500} value={filters.limit} onChange={(value) => setFilters({ ...filters, limit: value || 100 })} /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 2 }}><TextInput label="开始时间" type="datetime-local" value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.currentTarget.value })} /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 2 }}><TextInput label="结束时间" type="datetime-local" value={filters.date_to} onChange={(e) => setFilters({ ...filters, date_to: e.currentTarget.value })} /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 2 }}><Select label="链接" data={[{ value: "true", label: "含链接" }, { value: "false", label: "不含链接" }]} value={filters.has_links} onChange={(value) => setFilters({ ...filters, has_links: value || "" })} clearable /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 2 }}><Select label="媒体" data={[{ value: "true", label: "含媒体" }, { value: "false", label: "纯文本" }]} value={filters.has_media} onChange={(value) => setFilters({ ...filters, has_media: value || "" })} clearable /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 4 }}>
              <Group justify="flex-end">
                <Button type="submit" leftSection={<IconSearch size={16} />}>搜索消息</Button>
                <Button variant="light" leftSection={<IconDownload size={16} />} onClick={() => exportMessages("csv")}>CSV</Button>
                <Button variant="light" leftSection={<IconCloudDownload size={16} />} onClick={() => exportMessages("json")}>JSON</Button>
              </Group>
            </Grid.Col>
          </Grid>
        </form>
      </Card>

      <Stack gap="sm">
        {messages.map((message) => (
          <Card withBorder radius="lg" key={message.id} p="lg" className="message-card" onClick={() => setSelected(message)}>
            <Group justify="space-between" align="flex-start" wrap="nowrap">
              <Stack gap={4} className="grow">
                <Group gap="xs">
                  <Text fw={800}>{message.source}</Text>
                  <Badge variant="light">{message.message_kind}</Badge>
                  {message.media_type ? <Badge variant="light" color="violet">{message.media_type}</Badge> : null}
                  {message.links?.length ? <Badge variant="light" color="blue">链接 {message.links.length}</Badge> : null}
                  {message.risk_level > 0 ? <MatchLevel value={message.risk_level} /> : null}
                </Group>
                <Text size="xs" c="dimmed">{firstNonEmpty(message.sender_username, message.sender_name, message.sender_id)} · {formatTime(message.event_time)} · msg #{message.message_id}</Text>
                <Text className="message-content" lineClamp={3}>{message.content || `[${message.message_kind}]`}</Text>
              </Stack>
              <Button variant="subtle" size="xs">详情</Button>
            </Group>
          </Card>
        ))}
        {!messages.length ? <EmptyState text="暂无消息。可以先配置采集目标并执行回填。" /> : null}
      </Stack>

      <Modal opened={Boolean(selected)} onClose={() => setSelected(null)} title="消息详情" size="lg">
        {selected ? (
          <Stack>
            <Group gap="xs">
              <Badge>{selected.source}</Badge>
              <Badge variant="light">{selected.message_kind}</Badge>
              {selected.risk_level > 0 ? <MatchLevel value={selected.risk_level} /> : null}
            </Group>
            <Text size="sm" c="dimmed">{firstNonEmpty(selected.sender_username, selected.sender_name, selected.sender_id)} · {formatTime(selected.event_time)}</Text>
            <Paper withBorder p="md" radius="md"><Text className="message-content">{selected.content || `[${selected.message_kind}]`}</Text></Paper>
            <Stack gap={6}>
              <Text fw={700}>链接</Text>
              {selected.links?.length ? selected.links.map((link) => <Anchor key={link} href={link} target="_blank">{link}</Anchor>) : <Text size="sm" c="dimmed">无链接</Text>}
            </Stack>
          </Stack>
        ) : null}
      </Modal>
    </Stack>
  );
}

function Matches({ hits }) {
  return (
    <Card withBorder radius="lg" p="lg">
      <Table.ScrollContainer minWidth={760}>
        <Table verticalSpacing="sm">
          <Table.Thead>
            <Table.Tr><Table.Th>规则</Table.Th><Table.Th>消息</Table.Th><Table.Th>匹配内容</Table.Th><Table.Th>等级</Table.Th><Table.Th>状态</Table.Th><Table.Th>时间</Table.Th></Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {hits.map((hit) => (
              <Table.Tr key={hit.id}>
                <Table.Td><Text fw={600}>{hit.rule_name}</Text></Table.Td>
                <Table.Td>#{hit.message_id}</Table.Td>
                <Table.Td>{hit.matched_patterns.join(", ")}</Table.Td>
                <Table.Td><MatchLevel value={hit.risk_level} /></Table.Td>
                <Table.Td><StatusBadge value={hit.status} label={hit.status === "open" ? "待处理" : hit.status} /></Table.Td>
                <Table.Td>{formatTime(hit.created_at)}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Card>
  );
}

function NotificationsPanel({ channels, reload }) {
  const [form, setForm] = useState({ name: "", type: "telegram_bot", bot_token: "", chat_ids: "", url: "", min_risk_level: 1 });

  async function create(event) {
    event.preventDefault();
    const config = form.type === "telegram_bot"
      ? { bot_token: form.bot_token, chat_ids: form.chat_ids.split(",").map((item) => item.trim()).filter(Boolean) }
      : form.type === "feishu"
        ? { webhook_url: form.url }
        : { url: form.url };
    try {
      await api("/notifications", {
        method: "POST",
        body: { name: form.name, type: form.type, min_risk_level: Number(form.min_risk_level), config }
      });
      setForm({ name: "", type: "telegram_bot", bot_token: "", chat_ids: "", url: "", min_risk_level: 1 });
      notifyOk("通知渠道已新增");
      await reload();
    } catch (error) {
      notifyError(error);
    }
  }

  async function testChannel(id) {
    try {
      const result = await api(`/notifications/${id}/test`, { method: "POST" });
      if (result.status === "delivered") notifyOk("测试通知已发送");
      else notifyError(new Error(result.message || "测试通知失败"));
    } catch (error) {
      notifyError(error);
    }
  }

  return (
    <Stack>
      <Card withBorder radius="lg" p="lg">
        <Title order={3} mb="md">通知转发配置</Title>
        <form onSubmit={create}>
          <Grid align="end">
            <Grid.Col span={{ base: 12, md: 2 }}><TextInput label="名称" value={form.name} onChange={(e) => setForm({ ...form, name: e.currentTarget.value })} required /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 2 }}><Select label="类型" data={[{ value: "telegram_bot", label: "Telegram Bot" }, { value: "webhook", label: "Webhook" }, { value: "feishu", label: "飞书机器人" }]} value={form.type} onChange={(value) => setForm({ ...form, type: value || "telegram_bot" })} /></Grid.Col>
            {form.type === "telegram_bot" ? (
              <>
                <Grid.Col span={{ base: 12, md: 3 }}><TextInput label="Bot Token" value={form.bot_token} onChange={(e) => setForm({ ...form, bot_token: e.currentTarget.value })} required /></Grid.Col>
                <Grid.Col span={{ base: 12, md: 2 }}><TextInput label="Chat IDs" placeholder="逗号分隔" value={form.chat_ids} onChange={(e) => setForm({ ...form, chat_ids: e.currentTarget.value })} required /></Grid.Col>
              </>
            ) : (
              <Grid.Col span={{ base: 12, md: 5 }}><TextInput label={form.type === "feishu" ? "飞书 Webhook" : "Webhook URL"} value={form.url} onChange={(e) => setForm({ ...form, url: e.currentTarget.value })} required /></Grid.Col>
            )}
            <Grid.Col span={{ base: 6, md: 1 }}><NumberInput label="通知等级" min={0} max={5} value={form.min_risk_level} onChange={(value) => setForm({ ...form, min_risk_level: value || 0 })} /></Grid.Col>
            <Grid.Col span={{ base: 6, md: 2 }}><Button type="submit" fullWidth>新增通知</Button></Grid.Col>
          </Grid>
        </form>
      </Card>
      <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }}>
        {channels.map((channel) => (
          <Card withBorder radius="lg" key={channel.id} p="lg">
            <Group justify="space-between">
              <Title order={4}>{channel.name}</Title>
              <StatusBadge value={channel.type} />
            </Group>
            <Text c="dimmed" size="sm" mt="sm">通知等级：L{channel.min_risk_level} · 启用：{String(channel.enabled)}</Text>
            <Button mt="md" variant="light" leftSection={<IconSend size={14} />} onClick={() => testChannel(channel.id)}>测试通知</Button>
          </Card>
        ))}
      </SimpleGrid>
    </Stack>
  );
}

function Runs({ runs }) {
  const [selected, setSelected] = useState(null);

  async function openRun(id) {
    try {
      setSelected(await api(`/runs/${id}`));
    } catch (error) {
      notifyError(error);
    }
  }

  return (
    <>
      <Card withBorder radius="lg" p="lg">
        <Table.ScrollContainer minWidth={860}>
          <Table verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr><Table.Th>目标</Table.Th><Table.Th>模式</Table.Th><Table.Th>读取</Table.Th><Table.Th>写入</Table.Th><Table.Th>开始</Table.Th><Table.Th>状态</Table.Th><Table.Th /></Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {runs.map((run) => (
                <Table.Tr key={run.id}>
                  <Table.Td>target #{run.target_id || "-"}</Table.Td>
                  <Table.Td>{run.mode}</Table.Td>
                  <Table.Td>{run.records_seen}</Table.Td>
                  <Table.Td>{run.records_written}</Table.Td>
                  <Table.Td>{formatTime(run.started_at)}</Table.Td>
                  <Table.Td><StatusBadge value={run.status} /></Table.Td>
                  <Table.Td><Button size="xs" variant="light" onClick={() => openRun(run.id)}>日志详情</Button></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
      <Modal opened={Boolean(selected)} onClose={() => setSelected(null)} title="采集任务详情" size="lg">
        {selected ? (
          <Stack>
            <SimpleGrid cols={2}>
              <Text>任务 ID：#{selected.id}</Text>
              <Text>状态：{selected.status}</Text>
              <Text>账号：{selected.account_id || "-"}</Text>
              <Text>目标：{selected.target_id || "-"}</Text>
              <Text>读取：{selected.records_seen}</Text>
              <Text>写入：{selected.records_written}</Text>
              <Text>开始：{formatTime(selected.started_at)}</Text>
              <Text>结束：{formatTime(selected.finished_at)}</Text>
            </SimpleGrid>
            <Paper withBorder p="md" radius="md">
              <Text fw={700} mb="xs">错误 / 日志</Text>
              <Text className="message-content" c={selected.error ? "red" : "dimmed"}>{selected.error || "暂无错误。当前版本记录任务摘要，后续可扩展逐条日志。"}</Text>
            </Paper>
          </Stack>
        ) : null}
      </Modal>
    </>
  );
}

function SettingsPanel({ sinks, intelligence }) {
  const links = intelligence.links || [];
  const report = intelligence.report || {};
  return (
    <Stack>
      <SimpleGrid cols={{ base: 1, md: 3 }}>
        {sinks.map((sink) => (
          <Card withBorder radius="lg" key={sink.name} p="lg">
            <Group justify="space-between">
              <Title order={4}>{sink.name}</Title>
              <StatusBadge value={sink.status} />
            </Group>
            <Text c="dimmed" size="sm" mt="sm">{sink.note}</Text>
          </Card>
        ))}
      </SimpleGrid>
      <Grid>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Card withBorder radius="lg" h="100%" p="lg">
            <Title order={4} mb="sm">消息链接提取</Title>
            <Stack gap={6}>
              {links.slice(0, 10).map((item) => <Anchor size="sm" key={item.link} href={item.link} target="_blank">{item.link} · {item.count}</Anchor>)}
              {!links.length ? <Text c="dimmed" size="sm">暂无 t.me 链接。</Text> : null}
            </Stack>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Card withBorder radius="lg" h="100%" p="lg">
            <Title order={4} mb="sm">{report.title || "采集日报"}</Title>
            {(report.sections || []).slice(0, 3).map((section) => (
              <Text size="sm" key={section.heading}>{section.heading}: {section.body || `${(section.rows || []).length} rows`}</Text>
            ))}
            {!report.sections?.length ? <Text c="dimmed" size="sm">暂无日报数据。</Text> : null}
          </Card>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}

function EmptyState({ text }) {
  return (
    <Paper withBorder radius="lg" p="xl" ta="center">
      <IconTerminal size={26} color="var(--mantine-color-gray-5)" />
      <Text c="dimmed" mt="xs">{text}</Text>
    </Paper>
  );
}

const defaultMessageFilters = {
  keyword: "",
  source: "",
  sender: "",
  target_id: "",
  has_links: "",
  has_media: "",
  date_from: "",
  date_to: "",
  min_risk_level: "",
  limit: 100
};

function MainApp() {
  const [authed, setAuthed] = useState(Boolean(getToken()));
  const [activeTab, setActiveTab] = useState("dashboard");
  const [collapsed, setCollapsed] = useState(false);
  const [data, setData] = useState({ accounts: [], targets: [], rules: [], messages: [], hits: [], notifications: [], runs: [], sinks: [], intelligence: {}, dashboard: {} });
  const [messageFilters, setMessageFilters] = useState(defaultMessageFilters);
  const [error, setError] = useState("");

  const current = useMemo(() => navItems.find((item) => item.id === activeTab) || navItems[0], [activeTab]);

  function messageQuery(filters = messageFilters) {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== "" && value !== null && value !== undefined) params.set(key, value);
    });
    return params.toString();
  }

  async function load(filters = messageFilters) {
    if (!getToken()) return;
    setError("");
    try {
      const [dashboard, accounts, targets, rules, messages, hits, notificationChannels, runs, sinks, tgLinks, riskSummary, dailyReport] = await Promise.all([
        api("/dashboard"),
        api("/telegram/accounts"),
        api("/targets"),
        api("/rules"),
        api(`/messages?${messageQuery(filters)}`),
        api("/hits"),
        api("/notifications"),
        api("/runs"),
        api("/storage/sinks"),
        api("/intelligence/tg-links"),
        api("/intelligence/risk-summary"),
        api("/intelligence/daily-report")
      ]);
      setData({
        dashboard,
        accounts,
        targets,
        rules,
        messages,
        hits,
        notifications: notificationChannels,
        runs,
        sinks,
        intelligence: { links: tgLinks, summary: riskSummary, report: dailyReport }
      });
    } catch (err) {
      setError(err.message);
      if (/auth|token/i.test(err.message)) {
        clearToken();
        setAuthed(false);
      }
    }
  }

  function openMessagesForTarget(targetId) {
    const nextFilters = { ...messageFilters, target_id: String(targetId) };
    setMessageFilters(nextFilters);
    setActiveTab("messages");
    load(nextFilters);
  }

  useEffect(() => { if (authed) load(); }, [authed]);

  if (!authed) return <Login onDone={() => setAuthed(true)} />;

  return (
    <AppShell navbar={{ width: collapsed ? 88 : 300, breakpoint: "sm" }} padding="md">
      <AppShell.Navbar className="nav" p="md">
        <Group mb="lg" gap="sm" justify={collapsed ? "center" : "space-between"}>
          <Group gap="sm" wrap="nowrap">
            <ThemeIcon color="cyan" size={46} radius="lg">
              <IconRobot size={25} />
            </ThemeIcon>
            {!collapsed ? (
              <Stack gap={0}>
                <Text fw={900} c="white">WatchOut Telegram</Text>
                <Text size="xs" c="cyan.1">TG 采集平台</Text>
              </Stack>
            ) : null}
          </Group>
          {!collapsed ? (
            <Tooltip label="折叠侧栏">
              <ActionIcon variant="subtle" color="gray" onClick={() => setCollapsed(true)}>
                <IconChevronLeft size={18} />
              </ActionIcon>
            </Tooltip>
          ) : null}
        </Group>
        {collapsed ? (
          <Tooltip label="展开侧栏" position="right">
            <ActionIcon mb="md" variant="light" color="cyan" onClick={() => setCollapsed(false)} mx="auto">
              <IconChevronRight size={18} />
            </ActionIcon>
          </Tooltip>
        ) : null}
        <ScrollArea className="nav-scroll">
          <Stack gap={4}>
            {navItems.map((item) => {
              const Icon = item.icon;
              const link = (
                <NavLink
                  key={item.id}
                  active={activeTab === item.id}
                  label={collapsed ? null : item.label}
                  leftSection={<Icon size={19} />}
                  onClick={() => setActiveTab(item.id)}
                  className="nav-link"
                />
              );
              return collapsed ? <Tooltip key={item.id} label={item.label} position="right">{link}</Tooltip> : link;
            })}
          </Stack>
        </ScrollArea>
        <Button
          mt="auto"
          variant="subtle"
          color="gray"
          leftSection={<IconLogout size={16} />}
          onClick={() => { clearToken(); setAuthed(false); }}
          px={collapsed ? 0 : "md"}
        >
          {collapsed ? null : "退出"}
        </Button>
      </AppShell.Navbar>

      <AppShell.Main className="main">
        <Container size="xl" py="lg">
          <Group justify="space-between" mb="xl" align="flex-start" className="page-header">
            <Stack gap={4}>
              <Badge color="cyan" variant="light">WatchOut Telegram</Badge>
              <Title order={1}>{current.label}</Title>
              <Text c="dimmed">{current.subtitle}</Text>
            </Stack>
            <Group>
              <Burger opened={!collapsed} onClick={() => setCollapsed((value) => !value)} hiddenFrom="sm" />
              <ActionIcon size="lg" variant="light" color="cyan" onClick={() => load()}>
                <IconRefresh size={18} />
              </ActionIcon>
            </Group>
          </Group>
          {error ? <Alert color="red" icon={<IconAlertTriangle size={16} />} mb="md" withCloseButton onClose={() => setError("")}>{error}</Alert> : null}
          {activeTab === "dashboard" && <Dashboard data={data} setActiveTab={setActiveTab} />}
          {activeTab === "messages" && <Messages messages={data.messages} targets={data.targets} reload={load} filters={messageFilters} setFilters={setMessageFilters} />}
          {activeTab === "accounts" && <Accounts accounts={data.accounts} reload={load} />}
          {activeTab === "targets" && <Targets targets={data.targets} accounts={data.accounts} reload={load} openMessages={openMessagesForTarget} />}
          {activeTab === "runs" && <Runs runs={data.runs} />}
          {activeTab === "rules" && <Rules rules={data.rules} reload={load} />}
          {activeTab === "matches" && <Matches hits={data.hits} />}
          {activeTab === "notifications" && <NotificationsPanel channels={data.notifications} reload={load} />}
          {activeTab === "settings" && <SettingsPanel sinks={data.sinks} intelligence={data.intelligence} />}
        </Container>
      </AppShell.Main>
    </AppShell>
  );
}

const theme = {
  primaryColor: "cyan",
  defaultRadius: "md",
  fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
};

createRoot(document.getElementById("root")).render(
  <MantineProvider defaultColorScheme="light" theme={theme}>
    <Notifications position="top-right" />
    <MainApp />
  </MantineProvider>
);
