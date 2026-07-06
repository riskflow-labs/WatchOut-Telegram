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
  Collapse,
  Container,
  Divider,
  Drawer,
  FileButton,
  Grid,
  Group,
  MantineProvider,
  Menu,
  Modal,
  MultiSelect,
  NavLink,
  NumberInput,
  Pagination,
  Paper,
  PasswordInput,
  SegmentedControl,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Table,
  Tabs,
  Text,
  TextInput,
  Textarea,
  ThemeIcon,
  Title,
  Tooltip,
  UnstyledButton
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
  IconCode,
  IconCloudDownload,
  IconCopy,
  IconDatabase,
  IconDotsVertical,
  IconDownload,
  IconEdit,
  IconEye,
  IconFileExport,
  IconHistory,
  IconKey,
  IconLayoutDashboard,
  IconListCheck,
  IconLogout,
  IconExternalLink,
  IconMessageSearch,
  IconPlayerPlay,
  IconRefresh,
  IconServer,
  IconSearch,
  IconSend,
  IconSettings,
  IconTrash,
  IconSquare,
  IconTableExport,
  IconTarget,
  IconTerminal,
  IconUpload,
  IconUsers,
  IconX
} from "@tabler/icons-react";
import { API_BASE, api, clearToken, getToken, login } from "./lib/api";
import "./styles.css";

const navItems = [
  { id: "dashboard", label: "采集概览", short: "概览", icon: IconLayoutDashboard, subtitle: "账号、目标、消息归档和最近采集状态" },
  { id: "accounts", label: "账号管理", short: "账号", icon: IconKey, subtitle: "管理 Telegram 采集账号、授权状态、代理连通性和监听任务" },
  { id: "targets", label: "监控目标", short: "目标", icon: IconTarget, subtitle: "配置要监控的群组、频道、私聊和邀请链接" },
  { id: "runs", label: "采集任务", short: "任务", icon: IconHistory, subtitle: "查看实时监听和历史回填记录" },
  { id: "messages", label: "消息检索", short: "检索", icon: IconMessageSearch, subtitle: "搜索、过滤、查看和导出已采集消息" },
  { id: "rules", label: "监控规则", short: "规则", icon: IconListCheck, subtitle: "用主题词和信号词把海量消息自动归类、分级和触发通知" },
  { id: "matches", label: "命中线索", short: "线索", icon: IconCircleCheck, subtitle: "查看规则命中的消息、信号词、风险等级和处理状态" },
  { id: "notifications", label: "推送渠道", short: "推送", icon: IconBell, subtitle: "管理 Telegram、飞书、企业微信、钉钉、Webhook 等推送渠道" },
  { id: "settings", label: "设置", short: "设置", icon: IconSettings, subtitle: "配置主数据库，查看数据表设计和可选外部存储状态" }
];

const navIds = new Set(navItems.map((item) => item.id));
const UI_THEME_OPTIONS = ["light", "soft", "dark", "midnight", "auto"];
const UI_PREFS_DEFAULTS = { colorScheme: "light", pageSize: "50" };

function loadUiPrefs() {
  const saved = localStorage.getItem("watchout_telegram_ui_prefs");
  if (!saved) return UI_PREFS_DEFAULTS;
  try {
    const parsed = JSON.parse(saved);
    return {
      colorScheme: UI_THEME_OPTIONS.includes(parsed.colorScheme) ? parsed.colorScheme : UI_PREFS_DEFAULTS.colorScheme,
      pageSize: ["25", "50", "100", "200"].includes(String(parsed.pageSize)) ? String(parsed.pageSize) : UI_PREFS_DEFAULTS.pageSize
    };
  } catch {
    return UI_PREFS_DEFAULTS;
  }
}

function saveUiPrefs(nextPrefs) {
  const normalized = {
    ...UI_PREFS_DEFAULTS,
    colorScheme: UI_THEME_OPTIONS.includes(nextPrefs.colorScheme) ? nextPrefs.colorScheme : UI_PREFS_DEFAULTS.colorScheme,
    pageSize: ["25", "50", "100", "200"].includes(String(nextPrefs.pageSize)) ? String(nextPrefs.pageSize) : UI_PREFS_DEFAULTS.pageSize
  };
  localStorage.setItem("watchout_telegram_ui_prefs", JSON.stringify(normalized));
  document.documentElement.dataset.themePref = normalized.colorScheme;
  window.dispatchEvent(new CustomEvent("watchout-ui-prefs", { detail: normalized }));
  return normalized;
}

function tabFromHash() {
  const id = window.location.hash.replace(/^#\/?/, "");
  return navIds.has(id) ? id : "dashboard";
}

function setTabHash(tab) {
  const nextHash = `#/${tab}`;
  if (window.location.hash !== nextHash) {
    window.history.pushState(null, "", nextHash);
  }
}

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
  stopped: "已停止",
  success: "成功",
  failed: "失败",
  error: "异常",
  open: "待处理",
  muted: "只标记",
  confirmed: "已确认",
  ignored: "已忽略",
  archived: "已归档",
  notified: "已通知",
  metadata_only: "仅元数据",
  downloaded: "已下载",
  skipped: "已跳过",
  translated: "已翻译",
  authorized: "已授权",
  unauthorized: "未授权",
  created: "未登录",
  code_sent: "待验证码",
  password_required: "待二步密码"
}[String(value).toLowerCase()] || value || "-");

function StatusBadge({ value, label }) {
  return <Badge color={statusColor(value)} variant="light">{label || statusLabel(value)}</Badge>;
}

function MetricCard({ icon: Icon, label, value, sub, color = "cyan" }) {
  return (
    <Paper withBorder radius="md" p="md" className="dashboard-metric">
      <Group justify="space-between" align="flex-start">
        <Stack gap={2}>
          <Text c="dimmed" size="sm">{label}</Text>
          <Text fw={900} size="xl">{value}</Text>
          {sub ? <Text c="dimmed" size="xs">{sub}</Text> : null}
        </Stack>
        {Icon ? (
          <ThemeIcon color={color} variant="light" radius="md" size="lg">
            <Icon size={18} />
          </ThemeIcon>
        ) : null}
      </Group>
    </Paper>
  );
}

const backfillQuickRanges = [
  { label: "近3小时", hours: 3 },
  { label: "近1天", hours: 24 },
  { label: "近1周", hours: 24 * 7 },
  { label: "近1个月", days: 30 }
];
const backfillExtendedRanges = [
  { label: "近3个月", days: 90 },
  { label: "近6个月", days: 180 },
  { label: "近1年", days: 365 }
];
const defaultCustomBackfill = { targetId: null, amount: 90, unit: "days", limit: 10000 };

function customBackfillLabel(value) {
  const amount = Number(value?.amount) || 1;
  const unit = value?.unit || "days";
  if (unit === "hours") return `近${amount}小时`;
  if (unit === "months") return `近${amount}个月`;
  return `近${amount}天`;
}

function buildCustomBackfillRange(value) {
  const amount = Math.max(1, Number(value?.amount) || 1);
  const unit = value?.unit || "days";
  if (unit === "hours") return { label: customBackfillLabel(value), hours: Math.min(amount, 168) };
  if (unit === "months") return { label: customBackfillLabel(value), days: Math.min(amount * 30, 365) };
  return { label: customBackfillLabel(value), days: Math.min(amount, 365) };
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

function notifyWarning(message, title = "需要关注") {
  notifications.show({ color: "yellow", title, message });
}

function notifyIssue(message) {
  notifications.show({ color: "red", title: "发现异常", message });
}

function parseTelegramTime(value) {
  if (!value) return null;
  if (value instanceof Date) return value;
  const text = String(value);
  if (/[zZ]|[+-]\d{2}:?\d{2}$/.test(text)) return new Date(text);
  return new Date(`${text.replace(" ", "T")}Z`);
}

function formatTime(value) {
  if (!value) return "-";
  return parseTelegramTime(value)?.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  }) || "-";
}

function formatCompactTime(value) {
  if (!value) return "暂无消息";
  return parseTelegramTime(value)?.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }) || "获取失败";
}

function targetActivityInfo(value) {
  const date = parseTelegramTime(value);
  if (!date) {
    return {
      level: "none",
      color: "gray",
      label: "暂无消息",
      relative: "暂无消息",
      detail: "尚未成功采集到消息",
      days: null
    };
  }
  const diffMs = Date.now() - date.getTime();
  const hours = Math.max(0, diffMs / 3600000);
  const days = Math.floor(hours / 24);
  const relative = relativeTimeLabel(value);
  if (hours <= 24) {
    return { level: "active", color: "teal", label: `${relative}有消息`, relative, detail: "24小时内有新消息", days };
  }
  if (hours <= 72) {
    return { level: "quiet", color: "orange", label: `${days || 1}天无消息`, relative, detail: "1-3天无新消息", days };
  }
  const staleDays = Math.max(4, Math.ceil(hours / 24));
  return { level: "stale", color: "red", label: `${staleDays}天无消息，需关注`, relative, detail: "超过3天无新消息", days: staleDays };
}

function targetActivityColor(value) {
  return targetActivityInfo(value).color;
}

function firstNonEmpty(...values) {
  return values.find((value) => value !== undefined && value !== null && String(value).trim() !== "") || "-";
}

function normalizePhoneInput(countryCode = "", phone = "") {
  const code = String(countryCode || "").trim().replace(/[^\d+]/g, "");
  const number = String(phone || "").trim().replace(/[^\d]/g, "");
  const prefix = code.startsWith("+") ? code : `+${code}`;
  return `${prefix}${number}`;
}

function phoneNeedsCountryCode(phone = "") {
  return !/^\+[1-9]\d{6,14}$/.test(String(phone || "").trim());
}

function maskSecretUrl(value = "") {
  const text = String(value || "").trim();
  if (!text) return "";
  try {
    const parsed = new URL(text);
    const auth = parsed.username ? "***:***@" : "";
    return `${parsed.protocol}//${auth}${parsed.hostname}${parsed.port ? `:${parsed.port}` : ""}`;
  } catch {
    return text.length > 18 ? `${text.slice(0, 8)}...${text.slice(-6)}` : "***";
  }
}

function compactTargetName(value = "") {
  return String(value || "")
    .replace(/^Telegram\s*\/\s*/i, "")
    .replace(/^https?:\/\/t\.me\//i, "")
    .replace(/^@/, "")
    .trim() || "-";
}

function messageUrl(message) {
  const source = compactTargetName(message.source || "");
  const id = String(message.message_id || "").trim();
  if (!source || source === "-" || !id) return "";
  if (/^-?\d+$/.test(source)) return "";
  return `https://t.me/${source}/${id}`;
}

function extractedLinks(message) {
  const sourceUrl = messageUrl(message);
  return (message.links || []).filter((link) => link && link !== sourceUrl);
}

function serviceActionLabel(value = "") {
  return ({
    MessageActionChatAddUser: "成员加入",
    MessageActionChatJoinedByLink: "通过链接加入",
    MessageActionChatDeleteUser: "成员离开",
    MessageActionPinMessage: "置顶消息",
    MessageActionGroupCall: "群组通话",
    MessageActionChannelCreate: "频道创建",
    MessageActionChatCreate: "群组创建",
    MessageActionTopicCreate: "话题创建",
    MessageActionTopicEdit: "话题编辑"
  })[value] || value;
}

function mediaKindLabel(message) {
  const kind = message.message_kind || "";
  const media = message.media_type || "";
  if (kind === "service") return "服务";
  if (kind === "document" || media === "file") return "文件";
  if (media === "image" || kind === "photo") return "图片";
  if (media === "video") return "视频";
  if (media === "audio") return "音频";
  if (media === "MessageMediaWebPage") return "网页";
  if (kind === "text") return "文本";
  return kind || media || "消息";
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (!Number.isFinite(bytes) || bytes <= 0) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let size = bytes;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size >= 10 || unitIndex === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[unitIndex]}`;
}

function MessageTypeBadges({ message, size = "xs" }) {
  return (
    <Group gap={4}>
      <Badge size={size} variant="light">{message.message_kind}</Badge>
      {message.media_type && message.media_type !== "none" ? <Badge size={size} variant="light" color="violet">{message.media_type}</Badge> : null}
      {message.links?.length ? <Badge size={size} variant="light" color="blue">LINK {message.links.length}</Badge> : null}
    </Group>
  );
}

function messageDisplayText(message) {
  return firstNonEmpty(message.content, message.media_name, serviceActionLabel(message.raw_name), `[${mediaKindLabel(message)}]`);
}

function messageTargetName(message, targetById = new Map()) {
  const target = message.target_id ? targetById.get(String(message.target_id)) : null;
  const targetName = target ? targetDisplayName(target) : "";
  return firstNonEmpty(
    message.target_title,
    targetName && targetName !== "-" ? targetName : "",
    compactTargetName(message.source)
  );
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

function KpiCard({ icon: Icon, label, value, sub, color = "cyan", onClick, tone = "default" }) {
  return (
    <Card
      withBorder
      radius="md"
      p="md"
      className={("kpi-card dashboard-kpi-card " + (onClick ? "clickable " : "") + "dashboard-kpi-" + tone).trim()}
      onClick={onClick}
    >
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Stack gap={4} className="grow">
          <Text size="xs" c="dimmed" fw={800}>{label}</Text>
          <Title order={2} className="dashboard-kpi-value">{value}</Title>
        </Stack>
        <ThemeIcon color={color} variant="light" radius="md" size={38}>
          <Icon size={20} />
        </ThemeIcon>
      </Group>
    </Card>
  );
}

const dashboardRangeOptions = [
  { value: "24h", label: "24小时" },
  { value: "48h", label: "48小时" },
  { value: "7d", label: "7天" },
  { value: "30d", label: "30天" }
];

const dashboardCollectionOptions = [
  { value: "all", label: "全部采集" },
  { value: "live", label: "实时监听" },
  { value: "backfill", label: "历史回爬" }
];

function dashboardRangeLabel(value) {
  return dashboardRangeOptions.find((item) => item.value === String(value))?.label || "24小时";
}

function dashboardStatusColor(level = "normal") {
  return ({ normal: "teal", warning: "orange", critical: "red" }[level] || "gray");
}

function dashboardHealthLabel(value = "") {
  return ({ normal: "正常", low_activity: "低活跃", stale: "疑似断流", error: "异常", idle: "等待调度", disabled: "已禁用" }[String(value)] || statusLabel(value));
}

function dashboardHealthColor(value = "") {
  return ({ normal: "teal", low_activity: "yellow", stale: "orange", error: "red", idle: "gray", disabled: "gray" }[String(value)] || statusColor(value));
}

function compareAccounts(a, b, sort) {
  const direction = sort.direction === "asc" ? 1 : -1;
  const value = (account) => {
    const state = account.state || {};
    if (sort.key === "label") return String(account.label || account.phone || "").toLowerCase();
    if (sort.key === "overall") return String(state.overall?.label || "").toLowerCase();
    if (sort.key === "auth") return String(state.auth?.label || "").toLowerCase();
    if (sort.key === "runtime") return String(state.runtime?.label || "").toLowerCase();
    if (sort.key === "targets") return Number(state.targetCount || 0);
    if (sort.key === "proxy") return String(state.proxy?.label || "").toLowerCase();
    if (sort.key === "activity") return parseTelegramTime(state.lastActivityAt)?.getTime() || 0;
    if (sort.key === "error") return String(account.last_error || "").toLowerCase();
    return account.id || 0;
  };
  const left = value(a);
  const right = value(b);
  if (typeof left === "number" && typeof right === "number") {
    return (left - right) * direction || ((a.id || 0) - (b.id || 0));
  }
  return String(left).localeCompare(String(right), "zh-CN") * direction || ((a.id || 0) - (b.id || 0));
}

function percentText(value) {
  if (value === null || value === undefined) return "无前期数据";
  const number = Number(value) || 0;
  return (number > 0 ? "+" : "") + number + "%";
}

function sumBy(rows = [], key) {
  return rows.reduce((total, row) => total + (Number(row?.[key]) || 0), 0);
}

function formatMinutes(value) {
  if (value === null || value === undefined || value === "") return "暂无数据";
  const minutes = Math.max(0, Math.round(Number(value) || 0));
  if (minutes < 60) return minutes + "m";
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours < 24) return rest ? hours + "h" + rest + "m" : hours + "h";
  const days = Math.floor(hours / 24);
  const dayHours = hours % 24;
  return days + "d" + (dayHours ? dayHours + "h" : "");
}

function relativeUpdateText(value) {
  const date = parseTelegramTime(value);
  if (!date) return "尚未更新";
  const diff = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));
  if (diff < 1) return "刚刚更新";
  if (diff < 60) return "更新于 " + diff + " 分钟前";
  return "更新于 " + Math.floor(diff / 60) + " 小时前";
}

function toLocalInputValue(value) {
  const date = parseTelegramTime(value);
  if (!date) return "";
  const pad = (item) => String(item).padStart(2, "0");
  return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate()) + "T" + pad(date.getHours()) + ":" + pad(date.getMinutes());
}

function trendAxisIndexes(length, mode = "1") {
  if (!length) return [];
  const maxTicks = mode === "30" ? 7 : mode === "7" ? 6 : 7;
  if (length <= maxTicks) return Array.from({ length }, (_, index) => index);
  const indexes = new Set([0, length - 1]);
  const steps = maxTicks - 1;
  for (let tick = 1; tick < steps; tick += 1) {
    indexes.add(Math.round((tick * (length - 1)) / steps));
  }
  return Array.from(indexes).sort((a, b) => a - b);
}

function trendTimeLabel(value, withMinutes = false) {
  const date = parseTelegramTime(value);
  if (!date) return "-";
  const pad = (item) => String(item).padStart(2, "0");
  const monthDay = pad(date.getMonth() + 1) + "/" + pad(date.getDate());
  if (withMinutes) return monthDay + " " + pad(date.getHours()) + ":" + pad(date.getMinutes());
  return monthDay + " " + pad(date.getHours()) + "时";
}

function trendAxisLabel(value, mode = "1") {
  const date = parseTelegramTime(value);
  if (!date) return "-";
  const pad = (item) => String(item).padStart(2, "0");
  const monthDay = pad(date.getMonth() + 1) + "/" + pad(date.getDate());
  if (mode === "30") return monthDay;
  return monthDay + " " + pad(date.getHours()) + ":00";
}

function DashboardMetricCard({ icon, label, metric, value, color = "cyan", onClick }) {
  const Icon = icon;
  const tone = color === "red" ? "critical" : color === "orange" ? "warning" : "default";
  return <KpiCard icon={Icon} label={label} value={value} color={color} tone={tone} onClick={onClick} sub={metric?.scope || "当前状态"} />;
}

function CollectionTrendChart({ rows = [], range, onPointClick }) {
  const [hoverIndex, setHoverIndex] = useState(null);
  const data = rows || [];
  const width = 860;
  const height = 330;
  const padLeft = 46;
  const padRight = 48;
  const padTop = 24;
  const padBottom = 48;
  const maxMessages = Math.max(1, ...data.map((row) => Number(row.messages) || 0));
  const band = data.length ? (width - padLeft - padRight) / data.length : 0;
  const xCenter = (index) => padLeft + band * index + band / 2;
  const yMessages = (value) => height - padBottom - ((Number(value) || 0) / maxMessages) * (height - padTop - padBottom);
  const yRate = (value) => height - padBottom - ((Number(value) || 0) / 100) * (height - padTop - padBottom);
  const ratePoints = data.map((row, index) => [xCenter(index), yRate(row.hit_rate)]);
  const linePath = ratePoints.map(([x, y], index) => (index ? "L" : "M") + " " + x.toFixed(1) + " " + y.toFixed(1)).join(" ");
  const axisTicks = trendAxisIndexes(data.length, range === "30d" ? "30" : range === "7d" ? "7" : "1");
  const hover = hoverIndex === null ? null : data[hoverIndex];
  const messageTotal = sumBy(data, "messages");
  const hitTotal = sumBy(data, "hits");
  const failedTotal = sumBy(data, "failed_runs");

  if (!data.length) return <EmptyState text="暂无趋势数据。当前筛选条件下没有采集记录。" />;

  return (
    <Box className="dashboard-trend-chart">
      <Group justify="space-between" mb="xs"><Group gap="xs"><Badge color="cyan" variant="light">新增消息 {messageTotal}</Badge><Badge color="orange" variant="light">命中 {hitTotal}</Badge><Badge color={failedTotal ? "red" : "gray"} variant="light">失败事件 {failedTotal}</Badge></Group><Text size="xs" c="dimmed">柱形：消息 / 命中，折线：命中率</Text></Group>
      <Box className="trend-chart-canvas">
        <svg viewBox={"0 0 " + width + " " + height} role="img" aria-label="消息采集趋势" onMouseLeave={() => setHoverIndex(null)}>
          {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
            const y = padTop + ratio * (height - padTop - padBottom);
            const leftLabel = Math.round(maxMessages * (1 - ratio));
            const rightLabel = Math.round(100 * (1 - ratio));
            return <g key={ratio}><line x1={padLeft} x2={width - padRight} y1={y} y2={y} className="trend-grid-line" /><text x={padLeft - 10} y={y + 4} textAnchor="end" className="dashboard-axis-label">{leftLabel}</text><text x={width - padRight + 10} y={y + 4} textAnchor="start" className="dashboard-axis-label">{rightLabel}%</text></g>;
          })}
          <text x={padLeft} y={14} className="dashboard-axis-title">消息数</text><text x={width - padRight} y={14} textAnchor="end" className="dashboard-axis-title">命中率</text>
          {data.map((row, index) => {
            const x = padLeft + band * index + Math.max(3, band * 0.18);
            const barWidth = Math.max(3, band * 0.42);
            const hitWidth = Math.max(2, band * 0.18);
            const messageY = yMessages(row.messages);
            const hitY = yMessages(row.hits);
            return <g key={row.start || index} onMouseEnter={() => setHoverIndex(index)} onClick={() => onPointClick?.(row)} className="dashboard-chart-hit-area"><rect x={padLeft + band * index} y={0} width={Math.max(4, band)} height={height} fill="transparent" /><rect x={x} y={messageY} width={barWidth} height={height - padBottom - messageY} rx="3" className="dashboard-message-bar" /><rect x={x + barWidth + 2} y={hitY} width={hitWidth} height={height - padBottom - hitY} rx="3" className="dashboard-hit-bar" /></g>;
          })}
          {linePath ? <path d={linePath} fill="none" stroke="#2563eb" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /> : null}
          {ratePoints.map(([x, y], index) => index % Math.max(1, Math.ceil(ratePoints.length / 9)) === 0 ? <circle key={index} cx={x} cy={y} r="3.5" className="dashboard-rate-dot" /> : null)}
          {axisTicks.map((index) => { const row = data[index]; const x = xCenter(index); return <text key={row.start || index} x={x} y={height - 16} textAnchor="middle" className="dashboard-axis-label">{trendAxisLabel(row.start, range === "30d" ? "30" : range === "7d" ? "7" : "1")}</text>; })}
          {hoverIndex !== null ? <line x1={xCenter(hoverIndex)} x2={xCenter(hoverIndex)} y1={padTop} y2={height - padBottom} className="trend-hover-line" /> : null}
        </svg>
        {hover ? <Box className="trend-tooltip" style={{ left: ((xCenter(hoverIndex) / width) * 100) + "%", top: "22%" }}><Text size="xs" fw={800}>{trendTimeLabel(hover.start, true)} - {trendTimeLabel(hover.end, true)}</Text><Stack gap={3} mt={5}><Text size="xs">新增消息：{hover.messages || 0}</Text><Text size="xs">规则命中：{hover.hits || 0}</Text><Text size="xs">命中率：{hover.hit_rate || 0}%</Text><Text size="xs">实时 / 回爬：{hover.live_messages || 0} / {hover.backfill_messages || 0}</Text><Text size="xs">失败事件：{hover.failed_runs || 0}</Text></Stack></Box> : null}
      </Box>
    </Box>
  );
}

function InsightList({ rows = [], labelKey = "name", valueKey = "messages", empty = "暂无数据", onClick }) {
  const maxValue = Math.max(1, ...rows.map((row) => Number(row[valueKey]) || 0));
  if (!rows.length) return <Text c="dimmed" size="sm">{empty}</Text>;
  return <Stack gap="sm">{rows.map((row) => { const value = Number(row[valueKey]) || 0; return <Box key={String(row[labelKey]) + "-" + value} className={"insight-row " + (onClick ? "clickable" : "")} onClick={() => onClick?.(row)}><Group justify="space-between" mb={5} wrap="nowrap"><Tooltip label={row[labelKey]} disabled={String(row[labelKey] || "").length < 18}><Text size="sm" fw={700} truncate="end">{row[labelKey]}</Text></Tooltip><Badge variant="light">{value}</Badge></Group><Box className="insight-track"><Box className="insight-fill" style={{ width: Math.max(4, (value / maxValue) * 100) + "%" }} /></Box></Box>; })}</Stack>;
}

function HealthOverview({ overview, onTargetClick }) {
  const counts = overview?.target_health?.counts || {};
  const rows = [
    { key: "normal", label: "正常", color: "teal" }, { key: "low_activity", label: "低活跃", color: "yellow" }, { key: "idle", label: "等待调度", color: "gray" }, { key: "stale", label: "疑似断流", color: "orange" }, { key: "error", label: "异常", color: "red" }, { key: "disabled", label: "已禁用", color: "gray" }
  ].map((row) => ({ ...row, value: Number(counts[row.key]) || 0 }));
  const total = rows.reduce((sum, row) => sum + row.value, 0);
  return <Stack gap="md" className="dashboard-health-summary"><Group justify="space-between"><Text size="sm" fw={800}>状态汇总</Text><Badge variant="light">{total} 个目标</Badge></Group><Box className="dashboard-health-strip">{rows.map((row) => row.value ? <Box key={row.key} className={"dashboard-health-segment health-" + row.color} style={{ width: ((row.value / Math.max(1, total)) * 100) + "%" }} /> : null)}</Box><SimpleGrid cols={2} spacing={10}>{rows.map((row) => <Group key={row.key} gap={8} wrap="nowrap"><Box className={"health-dot health-" + row.color} /><Text size="sm" c="dimmed">{row.label}</Text><Text size="sm" fw={800}>{row.value}</Text></Group>)}</SimpleGrid></Stack>;
}

function AnomalyPanel({ anomalies = [], setActiveTab }) {
  if (!anomalies.length) return <Alert color="teal" icon={<IconCircleCheck size={16} />}>当前没有需要处理的采集异常</Alert>;
  const renderItem = (item, index) => <Paper key={item.type + "-" + (item.object_id || item.object_name || index)} withBorder radius="md" p="xs" className="dashboard-issue-row dashboard-anomaly-item clickable" onClick={() => item.action && setActiveTab(item.action)}><Group align="center" gap="xs" wrap="nowrap"><Badge size="sm" color={item.severity === "critical" ? "red" : item.severity === "warning" ? "orange" : "blue"} variant="light">{item.severity === "critical" ? "严重" : item.severity === "warning" ? "警告" : "提示"}</Badge><Stack gap={1} className="grow"><Group justify="space-between" gap="xs" wrap="nowrap"><Group gap={6} wrap="nowrap" className="grow"><Text size="sm" fw={800} lineClamp={1}>{item.title}</Text>{item.merged_count ? <Badge size="xs" color="gray" variant="light" className="shrink-0">合并 {item.merged_count} 条</Badge> : null}</Group><Text size="xs" c="dimmed" className="shrink-0">{formatCompactTime(item.occurred_at)}</Text></Group><Text size="xs" c="dimmed" lineClamp={1}>{item.object_name ? item.object_name + "：" : ""}{item.description}</Text></Stack></Group></Paper>;
  return (
    <ScrollArea.Autosize mah={390} offsetScrollbars className="dashboard-anomaly-list">
      <Stack gap="xs">{anomalies.map(renderItem)}</Stack>
    </ScrollArea.Autosize>
  );
}

function Dashboard({ data, setActiveTab, targets = [], accounts = [], openMessagesForTarget, setMessageFilters }) {
  const [filters, setFilters] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return { range: params.get("dashboard_range") || "24h", account_id: params.get("account_id") || "", target_id: params.get("target_id") || "", collection_type: params.get("collection_type") || "all" };
  });
  const [overview, setOverview] = useState(data.dashboardOverview || {});
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [lastLoadedAt, setLastLoadedAt] = useState("");

  async function loadOverview(nextFilters = filters) {
    setLoading(true); setLoadError("");
    try {
      const params = new URLSearchParams();
      params.set("range", nextFilters.range || "24h"); params.set("collection_type", nextFilters.collection_type || "all"); params.set("timezone", Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Shanghai");
      if (nextFilters.account_id) params.set("account_id", nextFilters.account_id); if (nextFilters.target_id) params.set("target_id", nextFilters.target_id);
      const payload = await api("/dashboard/overview?" + params.toString());
      setOverview(payload); setLastLoadedAt(payload.generated_at || new Date().toISOString());
      const query = new URLSearchParams(window.location.search);
      query.set("dashboard_range", nextFilters.range || "24h");
      if (nextFilters.account_id) query.set("account_id", nextFilters.account_id); else query.delete("account_id");
      if (nextFilters.target_id) query.set("target_id", nextFilters.target_id); else query.delete("target_id");
      if (nextFilters.collection_type && nextFilters.collection_type !== "all") query.set("collection_type", nextFilters.collection_type); else query.delete("collection_type");
      window.history.replaceState(null, "", window.location.pathname + (query.toString() ? "?" + query.toString() : "") + (window.location.hash || "#/dashboard"));
    } catch (error) { setLoadError(error.message || "Dashboard 数据加载失败"); notifyError(error); }
    finally { setLoading(false); }
  }

  useEffect(() => { loadOverview(filters); }, [filters.range, filters.account_id, filters.target_id, filters.collection_type]);
  useEffect(() => { if (data.dashboardOverview?.generated_at) { setOverview(data.dashboardOverview); setLastLoadedAt(data.dashboardOverview.generated_at); } }, [data.dashboardOverview]);

  function openMessagesForRange(row) { setMessageFilters?.({ ...defaultMessageFilters, date_from: toLocalInputValue(row.start), date_to: toLocalInputValue(row.end), target_id: filters.target_id || "" }); setActiveTab("messages"); }

  const summary = overview.summary || {};
  const status = overview.system_status || { level: "normal", label: "正常" };
  const task = summary.task_success || {};
  const delay = summary.collection_delay || {};
  const trendRows = overview.collection_trend || [];
  const rangeLabel = overview.time_range?.label || dashboardRangeLabel(filters.range);

  return (
    <Stack className="dashboard-view" gap="md">
      {loadError ? <Alert color="red" icon={<IconAlertTriangle size={16} />}>Dashboard 数据加载失败：{loadError}</Alert> : null}
      <SimpleGrid cols={{ base: 1, sm: 2, xl: 6 }} spacing="sm">
        <DashboardMetricCard icon={IconBrandTelegram} label="账号健康" value={(summary.account_health?.authorized ?? 0) + "/" + (summary.account_health?.total ?? 0)} metric={summary.account_health} color={(summary.account_health?.abnormal || 0) ? "orange" : "teal"} onClick={() => setActiveTab("accounts")} />
        <DashboardMetricCard icon={IconTarget} label="目标健康" value={(summary.target_health?.normal ?? 0) + "/" + (summary.target_health?.enabled ?? 0)} metric={summary.target_health} color={(summary.target_health?.abnormal || 0) ? "orange" : "teal"} onClick={() => setActiveTab("targets")} />
        <DashboardMetricCard icon={IconMessageSearch} label="新增消息" value={formatCount(summary.new_messages?.value || 0)} metric={{ scope: rangeLabel + "，环比 " + percentText(summary.new_messages?.change_percent) }} color="blue" onClick={() => setActiveTab("messages")} />
        <DashboardMetricCard icon={IconListCheck} label="风险命中" value={formatCount(summary.risk_hits?.value || 0)} metric={{ scope: rangeLabel + "，命中率 " + (summary.risk_hits?.hit_rate || 0) + "%" }} color={(summary.risk_hits?.value || 0) ? "orange" : "gray"} onClick={() => setActiveTab("matches")} />
        <DashboardMetricCard icon={IconHistory} label="任务成功率" value={(task.success || 0) + "/" + (task.total || 0)} metric={{ scope: "成功率 " + (task.success_rate || 0) + "%；失败 " + (task.failed || 0) + "；运行中 " + (task.running || 0) + "；其他 " + (task.other || 0) }} color={(task.failed || 0) ? "red" : "teal"} onClick={() => setActiveTab("runs")} />
        <DashboardMetricCard icon={IconDatabase} label="采集延迟" value={formatMinutes(delay.minutes)} metric={{ scope: "最近入库：" + formatTime(delay.last_insert_time) }} color={(delay.minutes || 0) > 120 ? "orange" : "teal"} onClick={() => setActiveTab("messages")} />
      </SimpleGrid>
      <Grid align="stretch">
        <Grid.Col span={{ base: 12, xl: 8 }}>
          <Card withBorder radius="md" p="md" className="dashboard-panel trend-panel">
            <Group justify="space-between" mb="sm" align="flex-start" gap="sm">
              <Box>
                <Group gap="xs">
                  <Title order={3}>消息采集趋势</Title>
                  <Tooltip label={`动态粒度：${overview.time_range?.granularity_hours || 1} 小时；柱形为消息/命中，折线为命中率。统计时区：${overview.timezone || "Asia/Shanghai"}`}>
                    <Badge color="gray" variant="light">口径</Badge>
                  </Tooltip>
                </Group>
              </Box>
              <SegmentedControl
                size="xs"
                value={filters.range}
                data={dashboardRangeOptions}
                onChange={(value) => setFilters((current) => ({ ...current, range: value || "24h" }))}
              />
            </Group>
            {loading && !trendRows.length ? <Text c="dimmed" size="sm">趋势加载中...</Text> : <CollectionTrendChart rows={trendRows} range={filters.range} onPointClick={openMessagesForRange} />}
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, xl: 4 }}>
          <Card id="dashboard-anomalies" withBorder radius="md" p="md" className="dashboard-panel">
            <Group justify="space-between" mb="sm">
              <Title order={3}>异常与待办</Title>
              <Button size="xs" variant="subtle" onClick={() => setActiveTab("runs")}>处理入口</Button>
            </Group>
            <AnomalyPanel anomalies={overview.anomalies || []} setActiveTab={setActiveTab} />
          </Card>
        </Grid.Col>
      </Grid>
      <Grid align="stretch" className="dashboard-compact-panels">
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Card withBorder radius="md" p="md" className="dashboard-panel dashboard-equal-panel">
            <Group justify="space-between" mb="sm"><Title order={3}>采集健康</Title><Button size="xs" variant="subtle" onClick={() => setActiveTab("targets")}>查看目标</Button></Group>
            <HealthOverview overview={overview} onTargetClick={(id) => openMessagesForTarget?.(id)} />
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Card withBorder radius="md" p="md" className="dashboard-panel dashboard-equal-panel">
            <Group justify="space-between" mb="sm"><Title order={3}>风险命中</Title><Button size="xs" variant="subtle" onClick={() => setActiveTab("matches")}>线索页</Button></Group>
            <InsightList rows={overview.risk_distribution?.levels || []} labelKey="label" valueKey="count" empty="暂无风险命中。" onClick={() => setActiveTab("matches")} />
            <Text size="xs" c="dimmed" mt="xs">L1=低风险，L2=中风险，L3+=高风险。</Text>
          </Card>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}

function Accounts({ accounts, reload, collectionConfig = {} }) {
  const defaultAccountFilters = {
    quick: "all",
    query: "",
    auth: "all",
    health: "all",
    runtime: "all",
    proxy: "all",
    bound: "all",
    enabled: "all"
  };
  const readAccountFilters = () => {
    const params = new URLSearchParams(window.location.search);
    return {
      quick: params.get("accountQuick") || "all",
      query: params.get("accountQuery") || "",
      auth: params.get("accountAuth") || "all",
      health: params.get("accountHealth") || "all",
      runtime: params.get("accountRuntime") || "all",
      proxy: params.get("accountProxy") || "all",
      bound: params.get("accountBound") || "all",
      enabled: params.get("accountEnabled") || "all"
    };
  };
  const [form, setForm] = useState({ label: "", api_id: "", api_hash: "", country_code: "+1", phone: "", proxy_type: "socks5", proxy_host: "", proxy_port: "", proxy_username: "", proxy_password: "", proxy_url: "" });
  const [accountFilters, setAccountFilters] = useState(defaultAccountFilters);
  const [codeById, setCodeById] = useState({});
  const [passwordById, setPasswordById] = useState({});
  const [showCreate, setShowCreate] = useState(false);
  const [createStep, setCreateStep] = useState("basic");
  const [selectedAccount, setSelectedAccount] = useState(null);
  const [healthById, setHealthById] = useState({});
  const [checkingId, setCheckingId] = useState(null);
  const [bulkAccountAction, setBulkAccountAction] = useState("");
  const [selectedAccountIds, setSelectedAccountIds] = useState([]);
  const [authModeId, setAuthModeId] = useState(null);
  const [diagnosticsById, setDiagnosticsById] = useState({});
  const [eventsById, setEventsById] = useState({});
  const [accountEdit, setAccountEdit] = useState({ label: "", proxy_url: "" });
  const [deletingId, setDeletingId] = useState(null);
  const [accountSort, setAccountSort] = useState({ key: "label", direction: "asc" });
  const accountTargetLimit = Math.max(1, Number(collectionConfig?.max_targets_per_account || 80));
  const enrichedAccounts = accounts.map((account) => ({ ...account, state: accountState(account) }));
  const filteredAccounts = enrichedAccounts;
  const sortedAccounts = [...filteredAccounts].sort((a, b) => compareAccounts(a, b, accountSort));
  const availableAccounts = enrichedAccounts.filter((account) => account.state.available);
  const listeningAccounts = enrichedAccounts.filter((account) => account.state.runtime.value === "listening");
  const attentionAccounts = enrichedAccounts.filter((account) => account.state.needsAttention);
  const totalTargets = enrichedAccounts.reduce((sum, account) => sum + account.state.targetCount, 0);
  const maxLoad = enrichedAccounts.reduce((max, account) => Math.max(max, account.state.targetCount), 0);
  const accountStats = {
    total: accounts.length,
    available: availableAccounts.length,
    listening: listeningAccounts.length,
    attention: attentionAccounts.length,
    totalTargets,
    maxLoad
  };
  const selectedAccountSet = new Set(selectedAccountIds);
  const selectedAccounts = sortedAccounts.filter((account) => selectedAccountSet.has(account.id));
  const allVisibleSelected = sortedAccounts.length > 0 && sortedAccounts.every((account) => selectedAccountSet.has(account.id));

  useEffect(() => {
    if (!selectedAccount) return;
    const latest = accounts.find((account) => account.id === selectedAccount.id);
    if (latest) {
      setSelectedAccount(latest);
    } else {
      setSelectedAccount(null);
    }
  }, [accounts, selectedAccount?.id]);

  function accountState(account) {
    const health = healthById[account.id];
    const status = String(account.authorization_status || account.status || "").toLowerCase();
    const persistedHealth = String(account.health_status || "unchecked").toLowerCase();
    const runtimeStatus = String(account.runtime_status || "").toLowerCase();
    const proxyStatus = String(account.proxy_status || (account.proxy_url ? "unchecked" : "none")).toLowerCase();
    const targetCount = health?.target_count ?? account.bound_target_count ?? account.health_target_count ?? 0;
    const listeningTargetCount = health?.listening_target_count ?? account.listening_target_count ?? account.health_listening_target_count ?? 0;
    const checkedAt = health ? new Date().toISOString() : account.last_checked_at || account.health_checked_at;
    const me = health?.me || account.health_me || "";
    const message = health?.message || account.health_message || "";
    const authorized = status === "authorized";
    const auth = status === "code_sent"
      ? { value: "code_sent", label: "等待验证码", color: "yellow" }
      : status === "password_required"
        ? { value: "password_required", label: "等待二步", color: "yellow" }
        : authorized
          ? { value: "authorized", label: "已授权", color: "teal" }
          : status === "unauthorized"
            ? { value: "unauthorized", label: "授权失效", color: "red" }
            : { value: "created", label: "未授权", color: "gray" };
    const runtime = runtimeStatus === "listening" || persistedHealth === "listening" || health?.listening
      ? { value: "listening", label: "监听中", color: "teal" }
      : runtimeStatus === "error"
        ? { value: "error", label: "运行异常", color: "red" }
      : { value: "stopped", label: "已停止", color: "gray" };
    const healthState = persistedHealth === "listening" || persistedHealth === "available" || health?.healthy
      ? { value: "ok", label: "正常", color: "teal" }
      : persistedHealth === "error" || status === "error"
        ? { value: "error", label: "异常", color: "red" }
        : checkedAt
          ? { value: "warning", label: "警告", color: "yellow" }
          : { value: "unchecked", label: "未检测", color: "blue" };
    const proxy = proxyStatus === "ok"
      ? { value: "ok", label: account.proxy_latency_ms ? `正常 ${account.proxy_latency_ms}ms` : "正常", color: "teal" }
      : proxyStatus === "slow"
        ? { value: "slow", label: account.proxy_latency_ms ? `缓慢 ${account.proxy_latency_ms}ms` : "连接缓慢", color: "yellow" }
        : proxyStatus === "failed"
          ? { value: "failed", label: "连接失败", color: "red" }
          : proxyStatus === "none"
            ? { value: "none", label: "未配置", color: "gray" }
            : { value: "unchecked", label: "未检测", color: "gray" };
    let overall = { value: "normal", label: "正常", color: "teal", reason: "账号已授权且状态正常" };
    if (!account.is_active) overall = { value: "disabled", label: "已禁用", color: "gray", reason: "账号不会参与自动检测和采集" };
    else if (auth.value === "created" || auth.value === "code_sent" || auth.value === "password_required" || auth.value === "unauthorized") overall = { value: "auth", label: "需要授权", color: "orange", reason: auth.label };
    else if (proxy.value === "failed") overall = { value: "proxy", label: "代理异常", color: "red", reason: account.proxy_message || "代理连接失败" };
    else if (runtime.value === "error") overall = { value: "runtime", label: "监听异常", color: "red", reason: account.last_error || "Runtime 异常" };
    else if (healthState.value === "error") overall = { value: "error", label: "需要处理", color: "red", reason: account.last_error || message || "最近检测失败" };
    else if (healthState.value === "unchecked") overall = { value: "unchecked", label: "待检测", color: "blue", reason: "尚未完成状态检测" };
    return {
      auth,
      runtime,
      health: healthState,
      proxy,
      overall,
      available: account.is_active && authorized && healthState.value !== "error" && proxy.value !== "failed",
      needsAttention: ["auth", "error", "disabled", "proxy", "runtime"].includes(overall.value),
      targetCount,
      listeningTargetCount,
      checkedAt,
      me,
      message,
      lastActivityAt: account.last_message_at || checkedAt || account.updated_at
    };
  }

  function accountMatchesFilters(account) {
    const state = account.state || accountState(account);
    const query = accountFilters.query.trim().toLowerCase();
    if (query) {
      const haystack = [
        account.label,
        account.phone,
        account.health_me,
        state.me
      ].filter(Boolean).join(" ").toLowerCase();
      if (!haystack.includes(query)) return false;
    }
    if (accountFilters.auth !== "all" && state.auth.value !== accountFilters.auth) return false;
    if (accountFilters.health !== "all" && state.health.value !== accountFilters.health) return false;
    if (accountFilters.runtime !== "all" && state.runtime.value !== accountFilters.runtime) return false;
    if (accountFilters.proxy !== "all" && state.proxy.value !== accountFilters.proxy) return false;
    if (accountFilters.bound === "bound" && state.targetCount <= 0) return false;
    if (accountFilters.bound === "unbound" && state.targetCount > 0) return false;
    if (accountFilters.enabled === "enabled" && !account.is_active) return false;
    if (accountFilters.enabled === "disabled" && account.is_active) return false;
    if (accountFilters.quick === "listening" && state.runtime.value !== "listening") return false;
    if (accountFilters.quick === "unauthorized" && state.auth.value === "authorized") return false;
    if (accountFilters.quick === "attention" && !state.needsAttention) return false;
    if (accountFilters.quick === "unbound" && state.targetCount > 0) return false;
    return true;
  }

  async function create(event) {
    event.preventDefault();
    try {
      const proxyAuth = form.proxy_username ? `${encodeURIComponent(form.proxy_username)}${form.proxy_password ? `:${encodeURIComponent(form.proxy_password)}` : ""}@` : "";
      const proxyUrl = form.proxy_host && form.proxy_port ? `${form.proxy_type}://${proxyAuth}${form.proxy_host}:${form.proxy_port}` : "";
      const payload = {
        label: form.label,
        api_id: Number(form.api_id),
        api_hash: form.api_hash,
        phone: normalizePhoneInput(form.country_code, form.phone),
        proxy_url: proxyUrl || form.proxy_url
      };
      await api("/telegram/accounts", { method: "POST", body: payload });
      setForm({ label: "", api_id: "", api_hash: "", country_code: "+1", phone: "", proxy_type: "socks5", proxy_host: "", proxy_port: "", proxy_username: "", proxy_password: "", proxy_url: "" });
      setCreateStep("basic");
      setShowCreate(false);
      notifyOk("账号已新增");
      await reload();
    } catch (error) {
      notifyError(error);
    }
  }

  async function action(id, path, body = {}, successMessage = "账号操作已提交") {
    try {
      await api(`/telegram/accounts/${id}/${path}`, { method: "POST", body });
      notifyOk(successMessage);
      await reload();
    } catch (error) {
      notifyError(error);
    }
  }

  async function sendAccountCode(account) {
    setAuthModeId(account.id);
    await action(account.id, "send-code", {}, "验证码已发送");
  }

  async function verifyAccountCode(account) {
    await action(account.id, "verify-code", { code: codeById[account.id] || "" }, "验证码已提交");
    setCodeById((current) => ({ ...current, [account.id]: "" }));
  }

  async function verifyAccountPassword(account) {
    await action(account.id, "verify-password", { password: passwordById[account.id] || "" }, "二步密码已提交");
    setPasswordById((current) => ({ ...current, [account.id]: "" }));
  }

  async function checkHealth(account) {
    setCheckingId(account.id);
    try {
      const result = await api(`/telegram/accounts/${account.id}/diagnostics`, { method: "POST" });
      setDiagnosticsById((current) => ({ ...current, [account.id]: result }));
      const items = result?.items || [];
      const failedCount = items.filter((item) => ["failed", "error"].includes(item.status)).length;
      const warningCount = items.filter((item) => ["warning", "slow"].includes(item.status)).length;
      if (failedCount > 0) {
        notifyIssue(`诊断完成，发现 ${failedCount} 项异常`);
      } else if (warningCount > 0) {
        notifyWarning(`诊断完成，发现 ${warningCount} 项需要关注`);
      } else {
        notifyOk("状态诊断正常");
      }
      await reload();
    } catch (error) {
      notifyError(error);
    } finally {
      setCheckingId(null);
    }
  }

  function bulkSummary(actionName, rows) {
    const eligible = rows.filter((account) => {
      if (actionName === "check") return account.is_active;
      if (actionName === "start") return account.state.auth.value === "authorized" && account.is_active && account.state.runtime.value !== "listening";
      if (actionName === "stop") return account.state.runtime.value === "listening";
      if (actionName === "enable") return !account.is_active;
      if (actionName === "disable") return account.is_active;
      return false;
    });
    return { eligible, skipped: rows.length - eligible.length };
  }

  async function runBulkAccountAction(actionName) {
    const { eligible, skipped } = bulkSummary(actionName, selectedAccounts);
    const label = ({ check: "检测", start: "启动监听", stop: "停止监听", enable: "启用", disable: "禁用" })[actionName] || actionName;
    if (!selectedAccounts.length || !eligible.length) return;
    if (!window.confirm(`已选择 ${selectedAccounts.length} 个账号，其中 ${eligible.length} 个可${label}，${skipped} 个不符合条件。本次将逐条执行并返回结果。`)) return;
    setBulkAccountAction(actionName);
    try {
      const result = await api("/telegram/accounts/bulk", {
        method: "POST",
        body: { account_ids: selectedAccountIds, action: actionName }
      });
      notifyOk(`批量${label}完成：成功 ${result.succeeded}，失败 ${result.failed}，跳过 ${result.skipped}`);
      await reload();
    } catch (error) {
      notifyError(error);
      await reload();
    } finally {
      setBulkAccountAction("");
    }
  }

  async function loadAccountEvents(account) {
    try {
      const events = await api(`/telegram/accounts/${account.id}/events`);
      setEventsById((current) => ({ ...current, [account.id]: events }));
    } catch (error) {
      notifyError(error);
    }
  }

  function toggleAccountSelection(id, checked) {
    setSelectedAccountIds((current) => checked ? [...new Set([...current, id])] : current.filter((item) => item !== id));
  }

  function toggleAllVisible(checked) {
    setSelectedAccountIds((current) => {
      const visibleIds = new Set(sortedAccounts.map((account) => account.id));
      if (checked) return [...new Set([...current, ...visibleIds])];
      return current.filter((id) => !visibleIds.has(id));
    });
  }

  function setAccountSortKey(key) {
    setAccountSort((current) => ({
      key,
      direction: current.key === key && current.direction === "asc" ? "desc" : "asc"
    }));
  }

  function AccountSortHeader({ label, sortKey, width }) {
    const active = accountSort.key === sortKey;
    return (
      <Table.Th w={width}>
        <UnstyledButton className={`target-sort-header ${active ? "active" : ""}`} onClick={() => setAccountSortKey(sortKey)}>
          <span>{label}</span>
          <span className="target-sort-indicator">{active ? (accountSort.direction === "asc" ? "↑" : "↓") : "↕"}</span>
        </UnstyledButton>
      </Table.Th>
    );
  }

  function openAccount(account) {
    setSelectedAccount(account);
    setAccountEdit({ label: account.label || "", proxy_url: "" });
    loadAccountEvents(account);
  }

  async function saveAccountEdit() {
    if (!selectedAccount) return;
    try {
      const updated = await api(`/telegram/accounts/${selectedAccount.id}`, {
        method: "PATCH",
        body: {
          label: accountEdit.label,
          ...(accountEdit.proxy_url.trim() ? { proxy_url: accountEdit.proxy_url.trim() } : {})
        }
      });
      setSelectedAccount(updated);
      notifyOk("账号信息已更新");
      await reload();
    } catch (error) {
      notifyError(error);
    }
  }

  async function saveAccountActive(account, isActive) {
    try {
      await api(`/telegram/accounts/${account.id}`, {
        method: "PATCH",
        body: { is_active: isActive }
      });
      setSelectedAccount((current) => current?.id === account.id ? { ...current, is_active: isActive } : current);
      notifyOk(isActive ? "账号已启用" : "账号已禁用");
      await reload();
    } catch (error) {
      notifyError(error);
    }
  }

  async function deleteAccount(account) {
    if (!account?.id) return;
    const label = account.label || account.phone || `账号 #${account.id}`;
    if (!window.confirm(`确认删除账号「${label}」？\n\n删除后会停止监听，并把绑定目标改为自动分配。历史消息会保留。`)) return;
    setDeletingId(account.id);
    try {
      await api(`/telegram/accounts/${account.id}`, { method: "DELETE" });
      setSelectedAccount((current) => current?.id === account.id ? null : current);
      notifyOk("账号已删除");
      await reload();
    } catch (error) {
      notifyError(error);
    } finally {
      setDeletingId(null);
    }
  }

  function healthLabel(account) {
    return accountState(account).health;
  }

  function accountHealthSnapshot(account) {
    const health = healthById[account.id];
    return {
      me: health?.me || account.health_me || "",
      message: health?.message || account.health_message || "",
      target_count: health?.target_count ?? account.health_target_count ?? 0,
      listening_target_count: health?.listening_target_count ?? account.health_listening_target_count ?? 0,
      checked_at: health ? new Date().toISOString() : account.health_checked_at
    };
  }

  function accountDiagnosisRows(account) {
    const remote = diagnosticsById[account.id]?.items;
    if (remote?.length) {
      const colorMap = { ok: "teal", success: "teal", slow: "yellow", warning: "yellow", failed: "red", error: "red", none: "gray", unchecked: "gray", listening: "teal", stopped: "gray" };
      return remote.map((item) => ({
        item: item.label || item.key,
        color: colorMap[item.status] || "blue",
        result: item.duration_ms ? `${item.result || "-"}（${item.duration_ms}ms）` : item.result || "-",
        suggestion: item.suggestion
      }));
    }
    const state = accountState(account);
    const checks = [
      {
        item: "手机号格式",
        color: phoneNeedsCountryCode(account.phone) ? "yellow" : "teal",
        result: account.phone || "-",
        suggestion: phoneNeedsCountryCode(account.phone) ? "建议重新补录为 +区号手机号，避免授权与 Session 命名不稳定。" : "格式符合 E.164 展示要求。"
      },
      {
        item: "授权状态",
        color: state.auth.color,
        result: state.auth.label,
        suggestion: state.auth.value === "authorized" ? "Session 可用于采集；如果后续失效，可在设置中重新登录。" : "先完成验证码/二步验证，再启动监听。"
      },
      {
        item: "代理配置",
        color: state.proxy.color,
        result: state.proxy.label,
        suggestion: account.proxy_message || (state.proxy.value === "none" ? "服务器不能直连 Telegram 时需要配置代理。" : "可点击立即检测获取代理连通性。")
      },
      {
        item: "健康检测",
        color: state.health.color,
        result: state.health.label,
        suggestion: state.health.value === "ok" ? "最近一次检测正常。" : "建议手动检测一次，检测结果会同步列表和 KPI。"
      },
      {
        item: "运行状态",
        color: state.runtime.color,
        result: state.runtime.label,
        suggestion: state.runtime.value === "listening" ? `正在监听 ${state.listeningTargetCount} 个目标。` : "只有已授权且启用的账号才显示启动监听。"
      },
      {
        item: "目标负载",
        color: state.targetCount > 20 ? "orange" : "blue",
        result: `${state.targetCount} 个目标 / ${state.listeningTargetCount} 个监听中`,
        suggestion: state.targetCount > 20 ? "负载偏高时建议拆分到更多账号，降低限流风险。" : "当前负载可控。"
      }
    ];
    if (phoneNeedsCountryCode(account.phone)) {
      checks.push({ item: "修复建议", color: "yellow", result: "需要补区号", suggestion: "现有 Session 可继续使用；后续新增账号必须先选区号再输入手机号。" });
    }
    if (!account.is_active) {
      checks.push({ item: "启用状态", color: "gray", result: "已禁用", suggestion: "禁用账号不会参与每日检测、自动分配和采集任务。" });
    }
    return checks;
  }

  return (
    <Stack gap="md" className="accounts-view">
      <SimpleGrid cols={{ base: 2, md: 4 }}>
        <KpiCard icon={IconCircleCheck} label="可用账号" value={`${accountStats.available}/${accountStats.total}`} sub="已启用且 Session 有效" />
        <KpiCard icon={IconPlayerPlay} label="监听中" value={accountStats.listening} sub="来自最近运行态快照" color="teal" />
        <KpiCard icon={IconAlertTriangle} label="需要处理" value={accountStats.attention} sub="授权、异常或禁用" color="orange" />
        <KpiCard icon={IconTarget} label="目标负载" value={accountStats.totalTargets} sub={`最高 ${accountStats.maxLoad}/${accountTargetLimit} 个/账号`} color="blue" />
      </SimpleGrid>

      <Drawer opened={showCreate} onClose={() => setShowCreate(false)} title="新增 Telegram 账号" position="right" size="lg">
        <form onSubmit={create}>
          <Stack gap="md">
            <SegmentedControl
              value={createStep}
              onChange={setCreateStep}
              data={[
                { value: "basic", label: "基础信息" },
                { value: "proxy", label: "代理配置（可选）" },
                { value: "auth", label: "授权准备" }
              ]}
            />
            {createStep === "basic" ? (
              <Stack gap="sm">
                <TextInput label="账号名称" placeholder="例如：土耳其采集号 A" value={form.label} onChange={(e) => setForm({ ...form, label: e.currentTarget.value })} required />
                <SimpleGrid cols={{ base: 1, sm: 2 }}>
                  <TextInput label="api_id" value={form.api_id} onChange={(e) => setForm({ ...form, api_id: e.currentTarget.value.replace(/\D/g, "") })} required />
                  <PasswordInput label="api_hash" value={form.api_hash} onChange={(e) => setForm({ ...form, api_hash: e.currentTarget.value })} required />
                </SimpleGrid>
                <SimpleGrid cols={{ base: 1, sm: 2 }}>
                  <TextInput label="国家/地区区号" placeholder="+1" value={form.country_code} onChange={(e) => setForm({ ...form, country_code: e.currentTarget.value })} required />
                  <TextInput label="手机号" placeholder="6513909110" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.currentTarget.value.replace(/\D/g, "") })} required />
                </SimpleGrid>
                <Alert color="blue">保存时会统一为 E.164 格式：{normalizePhoneInput(form.country_code, form.phone) || "+区号手机号"}</Alert>
              </Stack>
            ) : null}
            {createStep === "proxy" ? (
              <Stack gap="sm">
                <Select label="代理类型" value={form.proxy_type} onChange={(value) => setForm({ ...form, proxy_type: value || "socks5" })} data={[{ value: "socks5", label: "SOCKS5" }, { value: "http", label: "HTTP" }, { value: "none", label: "无代理" }]} />
                {form.proxy_type !== "none" ? (
                  <>
                    <SimpleGrid cols={{ base: 1, sm: 2 }}>
                      <TextInput label="主机" placeholder="host.docker.internal" value={form.proxy_host} onChange={(e) => setForm({ ...form, proxy_host: e.currentTarget.value })} />
                      <TextInput label="端口" placeholder="7891" value={form.proxy_port} onChange={(e) => setForm({ ...form, proxy_port: e.currentTarget.value.replace(/\D/g, "") })} />
                    </SimpleGrid>
                    <SimpleGrid cols={{ base: 1, sm: 2 }}>
                      <TextInput label="用户名" value={form.proxy_username} onChange={(e) => setForm({ ...form, proxy_username: e.currentTarget.value })} />
                      <PasswordInput label="密码" value={form.proxy_password} onChange={(e) => setForm({ ...form, proxy_password: e.currentTarget.value })} />
                    </SimpleGrid>
                  </>
                ) : <Alert color="gray">不配置代理时，后端需要能够直连 Telegram；Docker 中连接宿主机代理请使用 host.docker.internal。</Alert>}
              </Stack>
            ) : null}
            {createStep === "auth" ? (
              <Stack gap="sm">
                <Alert color="cyan">保存后可在账号详情的“设置”中完成 Telegram 授权。</Alert>
                <Text size="sm" c="dimmed">验证码、二步密码不会持久化保存；api_hash 和代理密码保存后不在界面明文回显。</Text>
              </Stack>
            ) : null}
            <Group justify="space-between" mt="md">
              <Button variant="subtle" color="gray" onClick={() => setShowCreate(false)}>取消</Button>
              <Group gap="xs">
                {createStep !== "basic" ? <Button variant="light" onClick={() => setCreateStep(createStep === "auth" ? "proxy" : "basic")}>上一步</Button> : null}
                {createStep !== "auth" ? <Button onClick={() => setCreateStep(createStep === "basic" ? "proxy" : "auth")}>下一步</Button> : <Button type="submit">保存账号</Button>}
              </Group>
            </Group>
          </Stack>
        </form>
      </Drawer>

      <Card withBorder radius="lg" p={0} className="account-table-card">
        <Group justify="space-between" px="md" py="sm" className="account-table-toolbar">
          <Box>
            <Text fw={800}>账号列表</Text>
            <Text size="sm" c="dimmed">账号总数 {accountStats.total}，当前显示 {sortedAccounts.length}。</Text>
          </Box>
          {selectedAccounts.length ? (
            <Group gap="xs" className="account-bulk-actions">
              <Badge variant="light">已选 {selectedAccounts.length}</Badge>
              <Button size="xs" variant="light" loading={bulkAccountAction === "check"} onClick={() => runBulkAccountAction("check")}>批量检测</Button>
              <Button size="xs" leftSection={<IconPlayerPlay size={13} />} loading={bulkAccountAction === "start"} onClick={() => runBulkAccountAction("start")}>批量启动</Button>
              <Button size="xs" color="gray" variant="light" leftSection={<IconSquare size={13} />} loading={bulkAccountAction === "stop"} onClick={() => runBulkAccountAction("stop")}>批量停止</Button>
              <Button size="xs" color="teal" variant="light" loading={bulkAccountAction === "enable"} onClick={() => runBulkAccountAction("enable")}>批量启用</Button>
              <Button size="xs" color="gray" variant="light" loading={bulkAccountAction === "disable"} onClick={() => runBulkAccountAction("disable")}>批量禁用</Button>
              <Button size="xs" variant="subtle" onClick={() => setSelectedAccountIds([])}>清空</Button>
            </Group>
          ) : (
            <Button onClick={() => { setCreateStep("basic"); setShowCreate(true); }}>新增账号</Button>
          )}
        </Group>
        <Table.ScrollContainer minWidth={920}>
          <Table verticalSpacing="sm" horizontalSpacing="md" striped highlightOnHover className="account-table">
            <Table.Thead>
              <Table.Tr>
                <Table.Th w={36}><Checkbox size="xs" checked={allVisibleSelected} indeterminate={!allVisibleSelected && selectedAccounts.length > 0} onChange={(event) => toggleAllVisible(event.currentTarget.checked)} /></Table.Th>
                <AccountSortHeader label="账号" sortKey="label" width={230} />
                <AccountSortHeader label="状态" sortKey="overall" width={220} />
                <AccountSortHeader label="目标负载" sortKey="targets" width={180} />
                <AccountSortHeader label="代理" sortKey="proxy" width={130} />
                <AccountSortHeader label="最近活动" sortKey="activity" width={120} />
                <Table.Th w={160}>操作</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {sortedAccounts.map((account) => {
                const health = accountHealthSnapshot(account);
                const state = account.state;
                const canStart = state.auth.value === "authorized" && account.is_active && state.runtime.value !== "listening";
                const canStop = state.runtime.value === "listening";
                const needsAuth = ["created", "code_sent", "password_required", "unauthorized"].includes(state.auth.value);
                return (
                  <Table.Tr key={account.id} className="account-table-row" onClick={() => openAccount(account)}>
                    <Table.Td onClick={(event) => event.stopPropagation()}>
                      <Checkbox size="xs" checked={selectedAccountSet.has(account.id)} onChange={(event) => toggleAccountSelection(account.id, event.currentTarget.checked)} />
                    </Table.Td>
                    <Table.Td>
                      <Text fw={800}>{account.label || account.phone}</Text>
                      <Group gap={6}>
                        <Text size="xs" c="dimmed">{account.phone || "-"}</Text>
                        {health.me ? <Text size="xs" c="dimmed">{health.me}</Text> : null}
                        {phoneNeedsCountryCode(account.phone) ? <Badge size="xs" color="yellow" variant="light">待补区号</Badge> : null}
                        {!account.is_active ? <Badge size="xs" color="gray" variant="light">已禁用</Badge> : null}
                      </Group>
                    </Table.Td>
                    <Table.Td>
                      <Stack gap={4}>
                        <Group gap={6}>
                          <Tooltip label={state.overall.reason}>
                            <Badge variant="light" color={state.overall.color}>{state.overall.label}</Badge>
                          </Tooltip>
                        </Group>
                        <Text size="xs" c="dimmed">{state.auth.label}｜{state.runtime.label}</Text>
                        {account.last_error ? <Text size="xs" c="red" lineClamp={1}>{account.last_error}</Text> : state.health.value === "unchecked" ? <Text size="xs" c="dimmed">尚未检测</Text> : null}
                      </Stack>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{state.targetCount}/{accountTargetLimit} 个目标｜监听 {state.listeningTargetCount}</Text>
                      <Box className="account-load-track"><Box className="account-load-fill" style={{ width: `${Math.min(100, Math.max(6, (state.targetCount / accountTargetLimit) * 100))}%` }} /></Box>
                    </Table.Td>
                    <Table.Td>
                      <Tooltip label={account.proxy_message || (account.proxy_checked_at ? `检测时间：${formatTime(account.proxy_checked_at)}` : "尚未检测代理")}>
                        <Badge variant="light" color={state.proxy.color}>{state.proxy.label}</Badge>
                      </Tooltip>
                    </Table.Td>
                    <Table.Td><Text size="sm" c="dimmed">{state.lastActivityAt ? relativeTimeLabel(state.lastActivityAt) : "暂无活动"}</Text></Table.Td>
                    <Table.Td onClick={(event) => event.stopPropagation()}>
                      <Group gap="xs">
                        {needsAuth ? (
                          <Button size="compact-xs" variant="light" onClick={() => openAccount(account)}>去授权</Button>
                        ) : canStop ? (
                          <Button size="compact-xs" color="gray" variant="light" leftSection={<IconSquare size={12} />} onClick={() => action(account.id, "stop", {}, "监听已停止")}>停止监听</Button>
                        ) : canStart ? (
                          <Button size="compact-xs" leftSection={<IconPlayerPlay size={12} />} onClick={() => action(account.id, "start", {}, "监听已启动")}>启动监听</Button>
                        ) : (
                          <Button size="compact-xs" variant="light" loading={checkingId === account.id} onClick={() => checkHealth(account)}>状态检测</Button>
                        )}
                        <Menu shadow="md" width={150} position="bottom-end">
                          <Menu.Target>
                            <ActionIcon variant="subtle" aria-label="更多操作"><IconEdit size={15} /></ActionIcon>
                          </Menu.Target>
                          <Menu.Dropdown>
                            <Menu.Item onClick={(event) => { event.stopPropagation(); checkHealth(account); }}>状态检测</Menu.Item>
                            <Menu.Item onClick={(event) => { event.stopPropagation(); openAccount(account); }}>编辑</Menu.Item>
                            <Menu.Item onClick={(event) => { event.stopPropagation(); saveAccountActive(account, !account.is_active); }}>{account.is_active ? "禁用账号" : "启用账号"}</Menu.Item>
                            <Menu.Item color="red" leftSection={<IconTrash size={14} />} onClick={(event) => { event.stopPropagation(); deleteAccount(account); }}>删除账号</Menu.Item>
                          </Menu.Dropdown>
                        </Menu>
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        {!accounts.length ? <EmptyState text="暂无账号。新增并完成授权后即可绑定监控目标。" /> : null}
        {accounts.length && !filteredAccounts.length ? <EmptyState text="没有符合筛选条件的账号。" /> : null}
      </Card>

      <Drawer opened={Boolean(selectedAccount)} onClose={() => setSelectedAccount(null)} title="账号详情" position="right" size="xl" className="account-ops-drawer">
        {selectedAccount ? (
          (() => {
            const state = accountState(selectedAccount);
            const health = accountHealthSnapshot(selectedAccount);
            const showAuthForm = state.auth.value !== "authorized" || authModeId === selectedAccount.id;
            const canStart = state.auth.value === "authorized" && selectedAccount.is_active && state.runtime.value !== "listening";
            const canStop = state.runtime.value === "listening";
            return (
              <Stack gap="md" className="account-ops-panel">
                <Paper withBorder radius="md" p="sm" className="account-summary-panel">
                  <Group justify="space-between" align="center" gap="sm">
                    <Group gap="xs" wrap="wrap">
                      <Text fw={900}>{selectedAccount.label || selectedAccount.phone}</Text>
                      <Badge variant="light" color={state.overall.color}>{state.overall.label}</Badge>
                      <Text size="sm" c="dimmed">{selectedAccount.phone || "-"}</Text>
                      {state.me ? <Text size="sm" c="dimmed">{state.me}</Text> : null}
                    </Group>
                    <Group gap="xs">
                      <Button variant="light" loading={checkingId === selectedAccount.id} onClick={() => checkHealth(selectedAccount)}>状态检测</Button>
                      {canStop ? <Button color="gray" variant="light" leftSection={<IconSquare size={14} />} onClick={() => action(selectedAccount.id, "stop", {}, "监听已停止")}>停止监听</Button> : null}
                      {canStart ? <Button leftSection={<IconPlayerPlay size={14} />} onClick={() => action(selectedAccount.id, "start", {}, "监听已启动")}>启动监听</Button> : null}
                    </Group>
                  </Group>
                </Paper>

                <Tabs defaultValue="overview" keepMounted={false} className="account-tabs">
                  <Tabs.List grow>
                    <Tabs.Tab value="overview">概览</Tabs.Tab>
                    <Tabs.Tab value="config">设置</Tabs.Tab>
                    <Tabs.Tab value="diagnosis">诊断</Tabs.Tab>
                  </Tabs.List>

                  <Tabs.Panel value="overview" pt="md">
                    <Stack gap="md">
                      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="sm">
                        <Paper withBorder radius="md" p="sm" className="account-status-tile">
                          <Text size="xs" c="dimmed">授权</Text>
                          <Badge mt={6} color={state.auth.color} variant="light">{state.auth.label}</Badge>
                        </Paper>
                        <Paper withBorder radius="md" p="sm" className="account-status-tile">
                          <Text size="xs" c="dimmed">健康</Text>
                          <Badge mt={6} color={state.health.color} variant="light">{state.health.label}</Badge>
                        </Paper>
                        <Paper withBorder radius="md" p="sm" className="account-status-tile">
                          <Text size="xs" c="dimmed">运行</Text>
                          <Badge mt={6} color={state.runtime.color} variant="light">{state.runtime.label}</Badge>
                        </Paper>
                        <Paper withBorder radius="md" p="sm" className="account-status-tile">
                          <Text size="xs" c="dimmed">代理</Text>
                          <Badge mt={6} color={state.proxy.color} variant="light">{state.proxy.label}</Badge>
                        </Paper>
                      </SimpleGrid>
                      {selectedAccount.last_error ? <Alert color="red">{selectedAccount.last_error}</Alert> : null}
                      <Paper withBorder radius="md" p="md">
                        <Group justify="space-between" align="flex-start">
                          <Box>
                            <Text fw={800}>最近检测</Text>
                            <Text size="sm" mt={4}>{health.message || "暂无检测详情"}</Text>
                            <Text size="sm" c="dimmed">绑定目标：{health.target_count}，监听目标：{health.listening_target_count}</Text>
                          </Box>
                          <Stack gap={2} align="flex-end">
                            <Badge color={state.health.color} variant="light">{state.health.label}</Badge>
                            <Text size="xs" c="dimmed">{health.checked_at ? formatTime(health.checked_at) : "尚未检测"}</Text>
                          </Stack>
                        </Group>
                      </Paper>
                      <Paper withBorder radius="md" p="md">
                        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
                          <InfoLine label="创建时间" value={formatTime(selectedAccount.created_at)} />
                          <InfoLine label="更新时间" value={formatTime(selectedAccount.updated_at)} />
                          <InfoLine label="最近消息" value={selectedAccount.last_message_at ? formatTime(selectedAccount.last_message_at) : "暂无消息"} />
                          <InfoLine label="代理检测" value={selectedAccount.proxy_checked_at ? `${formatTime(selectedAccount.proxy_checked_at)}，${state.proxy.label}` : state.proxy.label} />
                          <InfoLine label="最近活动" value={state.lastActivityAt ? relativeTimeLabel(state.lastActivityAt) : "暂无活动"} />
                          <InfoLine label="状态原因" value={state.overall.reason} />
                        </SimpleGrid>
                      </Paper>
                      <Paper withBorder radius="md" p="md">
                        <Group justify="space-between" align="flex-start">
                          <Box>
                            <Text fw={800}>监听控制</Text>
                            <Text size="sm" c="dimmed">未授权账号不显示启动入口；已监听账号只保留停止入口。</Text>
                          </Box>
                          <Group gap="xs">
                            {canStart ? <Button leftSection={<IconPlayerPlay size={14} />} onClick={() => action(selectedAccount.id, "start", {}, "监听已启动")}>启动监听</Button> : null}
                            {canStop ? <Button color="gray" variant="light" leftSection={<IconSquare size={14} />} onClick={() => action(selectedAccount.id, "stop", {}, "监听已停止")}>停止监听</Button> : null}
                            {!canStart && !canStop ? <Badge color="gray" variant="light">暂无可执行运行操作</Badge> : null}
                          </Group>
                        </Group>
                      </Paper>
                      <Paper withBorder radius="md" p="md">
                        <Stack gap="xs">
                          <Group justify="space-between">
                            <Text fw={800}>运行记录</Text>
                            <Button size="xs" variant="subtle" onClick={() => loadAccountEvents(selectedAccount)}>刷新</Button>
                          </Group>
                          {(eventsById[selectedAccount.id] || []).length ? (
                            <Table.ScrollContainer minWidth={520}>
                              <Table verticalSpacing="xs" className="account-events-table">
                                <Table.Thead>
                                  <Table.Tr>
                                    <Table.Th>时间</Table.Th>
                                    <Table.Th>事件</Table.Th>
                                    <Table.Th>结果</Table.Th>
                                  </Table.Tr>
                                </Table.Thead>
                                <Table.Tbody>
                                  {(eventsById[selectedAccount.id] || []).map((event) => (
                                    <Table.Tr key={event.id}>
                                      <Table.Td><Text size="xs" c="dimmed">{formatCompactTime(event.created_at)}</Text></Table.Td>
                                      <Table.Td><Text size="sm">{event.summary || event.event_type}</Text></Table.Td>
                                      <Table.Td><Badge size="xs" color={event.status === "failed" ? "red" : event.status === "pending" ? "yellow" : "teal"} variant="light">{event.status}</Badge></Table.Td>
                                    </Table.Tr>
                                  ))}
                                </Table.Tbody>
                              </Table>
                            </Table.ScrollContainer>
                          ) : <Text size="sm" c="dimmed">暂无运行事件。</Text>}
                        </Stack>
                      </Paper>
                    </Stack>
                  </Tabs.Panel>

                  <Tabs.Panel value="config" pt="md">
                    <Stack gap="md">
                      <Alert color="blue">配置页会明文显示手机号；代理认证信息和 Session 名称不会从后端回显。</Alert>
                      <Paper withBorder radius="md" p="md">
                        <Stack gap="sm">
                          <Text fw={800}>基础配置</Text>
                          <TextInput label="账号名称" value={accountEdit.label} onChange={(event) => setAccountEdit({ ...accountEdit, label: event.currentTarget.value })} />
                          <TextInput label="手机号" value={selectedAccount.phone || ""} readOnly />
                          <TextInput label="当前代理" value={selectedAccount.proxy_status === "none" ? "未配置代理" : state.proxy.label} readOnly />
                          <TextInput label="更新代理" placeholder="socks5://host.docker.internal:7891，留空则不修改" value={accountEdit.proxy_url} onChange={(event) => setAccountEdit({ ...accountEdit, proxy_url: event.currentTarget.value })} />
                          <Text size="xs" c="dimmed">完整代理不会从后端回显；修改时请重新输入完整代理地址。</Text>
                          <Switch label="启用账号" checked={Boolean(selectedAccount.is_active)} onChange={(event) => saveAccountActive(selectedAccount, event.currentTarget.checked)} />
                          <Group justify="flex-end">
                            <Button size="sm" onClick={saveAccountEdit}>保存配置</Button>
                          </Group>
                        </Stack>
                      </Paper>
                      <Paper withBorder radius="md" p="md">
                        <Stack gap="md">
                          <Group justify="space-between" align="flex-start">
                            <Box>
                              <Text fw={800}>授权管理</Text>
                              <Text size="sm" c="dimmed">{state.auth.value === "authorized" && authModeId !== selectedAccount.id ? "当前账号已授权，Session 有效时无需重复登录。" : "先发送验证码；如果 Telegram 开启二步验证，再提交二步密码。"}</Text>
                            </Box>
                            {state.auth.value === "authorized" && authModeId !== selectedAccount.id ? <Button variant="light" onClick={() => setAuthModeId(selectedAccount.id)}>重新授权</Button> : <Button variant="light" onClick={() => sendAccountCode(selectedAccount)}>发送验证码</Button>}
                          </Group>
                          {showAuthForm ? (
                            <SimpleGrid cols={{ base: 1, sm: 2 }}>
                              <Paper withBorder radius="md" p="sm" className="account-auth-step">
                                <Stack gap="xs">
                                  <Text size="sm" fw={800}>短信 / Telegram 验证码</Text>
                                  <Group gap="xs" wrap="nowrap" align="flex-end">
                                    <TextInput className="account-auth-input" size="md" label="验证码" placeholder="输入收到的验证码" value={codeById[selectedAccount.id] || ""} onChange={(e) => setCodeById({ ...codeById, [selectedAccount.id]: e.currentTarget.value })} />
                                    <Button size="md" miw={96} onClick={() => verifyAccountCode(selectedAccount)}>提交验证</Button>
                                  </Group>
                                </Stack>
                              </Paper>
                              <Paper withBorder radius="md" p="sm" className="account-auth-step">
                                <Stack gap="xs">
                                  <Text size="sm" fw={800}>二步验证密码</Text>
                                  <Group gap="xs" wrap="nowrap" align="flex-end">
                                    <PasswordInput className="account-auth-input" size="md" label="二步密码" placeholder="输入 Telegram 二步密码" value={passwordById[selectedAccount.id] || ""} onChange={(e) => setPasswordById({ ...passwordById, [selectedAccount.id]: e.currentTarget.value })} />
                                    <Button size="md" miw={112} onClick={() => verifyAccountPassword(selectedAccount)}>提交二步</Button>
                                  </Group>
                                </Stack>
                              </Paper>
                            </SimpleGrid>
                          ) : null}
                        </Stack>
                      </Paper>
                      <Paper withBorder radius="md" p="md" className="account-danger-zone">
                        <Group justify="space-between" align="center">
                          <Box>
                            <Text fw={800}>危险操作</Text>
                            <Text size="sm" c="dimmed">删除账号会停止监听，并把绑定目标改为自动分配。历史消息会保留。</Text>
                          </Box>
                          <Button color="red" variant="light" loading={deletingId === selectedAccount.id} leftSection={<IconTrash size={14} />} onClick={() => deleteAccount(selectedAccount)}>删除账号</Button>
                        </Group>
                      </Paper>
                    </Stack>
                  </Tabs.Panel>

                  <Tabs.Panel value="diagnosis" pt="md">
                    <Stack gap="sm">
                      <Group justify="space-between">
                        <Box>
                          <Text fw={800}>状态诊断</Text>
                          <Text size="sm" c="dimmed">按手机号、授权、代理、健康、运行、负载拆开看，减少“已授权但不可用”的误判。</Text>
                        </Box>
                        <Button variant="light" loading={checkingId === selectedAccount.id} onClick={() => checkHealth(selectedAccount)}>立即检测</Button>
                      </Group>
                      <Table.ScrollContainer minWidth={620}>
                        <Table verticalSpacing="sm" className="account-diagnosis-table">
                          <Table.Thead>
                            <Table.Tr>
                              <Table.Th>项目</Table.Th>
                              <Table.Th>结果</Table.Th>
                              <Table.Th>建议</Table.Th>
                            </Table.Tr>
                          </Table.Thead>
                          <Table.Tbody>
                            {accountDiagnosisRows(selectedAccount).map((item) => (
                              <Table.Tr key={item.item}>
                                <Table.Td><Badge color={item.color} variant="light">{item.item}</Badge></Table.Td>
                                <Table.Td><Text size="sm">{item.result}</Text></Table.Td>
                                <Table.Td><Text size="sm" c="dimmed">{item.suggestion}</Text></Table.Td>
                              </Table.Tr>
                            ))}
                          </Table.Tbody>
                        </Table>
                      </Table.ScrollContainer>
                    </Stack>
                  </Tabs.Panel>

                </Tabs>
              </Stack>
            );
          })()
        ) : null}
      </Drawer>

    </Stack>
  );
}

function Targets({ targets, accounts, reload, openMessages, defaultPageSize = "50" }) {
  const [bulkText, setBulkText] = useState("");
  const [bulkOptions, setBulkOptions] = useState({ account_id: "", target_type: "auto", target_group: "", onlyReady: true, autoJoinInvites: false });
  const [parseResult, setParseResult] = useState(null);
  const [parsing, setParsing] = useState(false);
  const [importing, setImporting] = useState(false);
  const [syncingDialogs, setSyncingDialogs] = useState(false);
  const [checkingTargets, setCheckingTargets] = useState(false);
  const [syncingTargetMetadata, setSyncingTargetMetadata] = useState(false);
  const [importDrawerOpen, setImportDrawerOpen] = useState(false);
  const [selectedTarget, setSelectedTarget] = useState(null);
  const [targetEdit, setTargetEdit] = useState({ account_id: "", target_group: "", enabled: true });
  const [syncingTitleId, setSyncingTitleId] = useState(null);
  const [targetActionKey, setTargetActionKey] = useState("");
  const [selectedTargetIds, setSelectedTargetIds] = useState([]);
  const [targetDeleteOpen, setTargetDeleteOpen] = useState(false);
  const [deleteTargetMessages, setDeleteTargetMessages] = useState(false);
  const [deletingTargets, setDeletingTargets] = useState(false);
  const [targetPage, setTargetPage] = useState(1);
  const [targetPageSize, setTargetPageSize] = useState(defaultPageSize);
  const [targetSearch, setTargetSearch] = useState("");
  const [targetStatusFilter, setTargetStatusFilter] = useState("all");
  const [targetGroupFilter, setTargetGroupFilter] = useState("all");
  const [targetSort, setTargetSort] = useState({ key: "last_run_at", direction: "desc" });
  const [targetLastUpdatedAt, setTargetLastUpdatedAt] = useState(new Date());
  const [refreshingTargets, setRefreshingTargets] = useState(false);
  const [aboutExpanded, setAboutExpanded] = useState(false);
  const [extendedBackfillOpen, setExtendedBackfillOpen] = useState(false);
  const [customBackfillOpen, setCustomBackfillOpen] = useState(false);
  const [customBackfill, setCustomBackfill] = useState(defaultCustomBackfill);
  const accountOptions = accounts.map((account) => ({ value: String(account.id), label: account.label || account.phone }));
  const authorizedAccountOptions = accounts
    .filter((account) => account.status === "authorized")
    .map((account) => ({ value: String(account.id), label: account.label || account.phone }));
  const accountName = (id) => accounts.find((account) => account.id === id)?.label || accounts.find((account) => account.id === id)?.phone || "自动";
  const targetGroupOptions = useMemo(() => {
    const groups = [...new Set(targets.map((target) => String(target.target_group || "").trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-CN"));
    return groups.map((group) => ({ value: group, label: group }));
  }, [targets]);
  const importTargetGroupOptions = useMemo(() => {
    const group = String(bulkOptions.target_group || "").trim();
    const exists = targetGroupOptions.some((option) => option.value === group);
    return group && !exists ? [{ value: group, label: `创建：${group}` }, ...targetGroupOptions] : targetGroupOptions;
  }, [targetGroupOptions, bulkOptions.target_group]);
  const targetGroupFilterOptions = [{ value: "all", label: "全部分组" }, { value: "__none__", label: "未分组" }, ...targetGroupOptions];
  const enabledTargets = targets.filter((target) => target.enabled);
  const targetStats = {
    total: targets.length,
    enabled: enabledTargets.length,
    running: targets.filter((target) => ["listening", "running"].includes(String(target.status).toLowerCase())).length,
    idle: targets.filter((target) => target.enabled && !isTargetListening(target) && !target.last_error).length,
    failed: targets.filter((target) => ["error", "failed"].includes(String(target.status).toLowerCase()) || target.last_error).length,
    recent: targets.filter((target) => {
      const date = parseTelegramTime(target.last_message_at);
      return date && Date.now() - date.getTime() <= 24 * 60 * 60 * 1000;
    }).length
  };
  const longQuietCount = targets.filter((target) => target.enabled && targetActivityInfo(target.last_message_at).level === "stale").length;
  const filteredTargets = targets.filter((target) => {
    const keyword = targetSearch.trim().toLowerCase();
    const targetGroup = String(target.target_group || "").trim();
    const text = [target.title, target.target, target.normalized_target, targetGroup, accountName(target.account_id)].join(" ").toLowerCase();
    const activity = targetActivityInfo(target.last_message_at);
    const matchesKeyword = !keyword || text.includes(keyword);
    const matchesStatus = targetStatusFilter === "all"
      || (targetStatusFilter === "normal" && target.enabled && !target.last_error && activity.level === "active")
      || (targetStatusFilter === "stale" && target.enabled && activity.level === "stale")
      || (targetStatusFilter === "error" && Boolean(target.last_error))
      || (targetStatusFilter === "stopped" && (!target.enabled || (!isTargetListening(target) && !target.last_error)));
    const matchesGroup = targetGroupFilter === "all"
      || (targetGroupFilter === "__none__" && !targetGroup)
      || targetGroup === targetGroupFilter;
    return matchesKeyword && matchesStatus && matchesGroup;
  });
  const sortedTargets = [...filteredTargets].sort((a, b) => compareTargets(a, b, targetSort, accountName));
  const pageSize = Number(targetPageSize);
  const totalPages = Math.max(1, Math.ceil(sortedTargets.length / pageSize));
  const currentPage = Math.min(targetPage, totalPages);
  const pageStart = (currentPage - 1) * pageSize;
  const pagedTargets = sortedTargets.slice(pageStart, pageStart + pageSize);
  const targetSelectedSet = new Set(selectedTargetIds);
  const pageTargetIds = pagedTargets.map((target) => target.id);
  const allTargetsPageSelected = pageTargetIds.length > 0 && pageTargetIds.every((id) => targetSelectedSet.has(id));
  const someTargetsPageSelected = pageTargetIds.some((id) => targetSelectedSet.has(id));

  useEffect(() => {
    setTargetPage(1);
    setSelectedTargetIds([]);
  }, [targetPageSize, targetSearch, targetStatusFilter, targetGroupFilter, targets.length]);

  useEffect(() => {
    setTargetPageSize(defaultPageSize);
  }, [defaultPageSize]);

  useEffect(() => {
    setTargetLastUpdatedAt(new Date());
  }, [targets]);

  function openTarget(target) {
    setSelectedTarget(target);
    setAboutExpanded(false);
    setTargetEdit({
      account_id: target.account_id ? String(target.account_id) : "",
      target_group: target.target_group || "",
      enabled: Boolean(target.enabled)
    });
  }

  function setTargetSortKey(key) {
    setTargetSort((current) => ({
      key,
      direction: current.key === key && current.direction === "asc" ? "desc" : "asc"
    }));
  }

  function SortHeader({ label, sortKey, width }) {
    const active = targetSort.key === sortKey;
    return (
      <Table.Th w={width}>
        <UnstyledButton className={`target-sort-header ${active ? "active" : ""}`} onClick={() => setTargetSortKey(sortKey)}>
          <span>{label}</span>
          <span className="target-sort-indicator">{active ? (targetSort.direction === "asc" ? "↑" : "↓") : "↕"}</span>
        </UnstyledButton>
      </Table.Th>
    );
  }

  function toggleTargetPage(checked) {
    setSelectedTargetIds((current) => {
      const next = new Set(current);
      pageTargetIds.forEach((id) => {
        if (checked) next.add(id);
        else next.delete(id);
      });
      return [...next];
    });
  }

  function toggleTarget(id, checked) {
    setSelectedTargetIds((current) => {
      const next = new Set(current);
      if (checked) next.add(id);
      else next.delete(id);
      return [...next];
    });
  }

  function openDeleteTargets(ids) {
    setSelectedTargetIds(ids);
    setDeleteTargetMessages(false);
    setTargetDeleteOpen(true);
  }

  async function deleteTargets() {
    if (!selectedTargetIds.length) return;
    setDeletingTargets(true);
    try {
      const result = selectedTargetIds.length === 1
        ? await api(`/targets/${selectedTargetIds[0]}`, { method: "DELETE", body: { delete_messages: deleteTargetMessages } })
        : await api("/targets/bulk", { method: "DELETE", body: { target_ids: selectedTargetIds, delete_messages: deleteTargetMessages } });
      notifyOk(deleteTargetMessages
        ? `已删除 ${result.deleted || 0} 个目标和 ${result.deleted_messages || 0} 条消息`
        : `已删除 ${result.deleted || 0} 个目标，历史消息已保留`);
      setTargetDeleteOpen(false);
      setSelectedTargetIds([]);
      if (selectedTarget && selectedTargetIds.includes(selectedTarget.id)) setSelectedTarget(null);
      await reload();
    } catch (error) {
      notifyError(error);
    } finally {
      setDeletingTargets(false);
    }
  }

  async function refreshTargetList() {
    setRefreshingTargets(true);
    try {
      await reload();
      setTargetLastUpdatedAt(new Date());
      notifyOk("目标列表已刷新");
    } catch (error) {
      notifyError(error);
    } finally {
      setRefreshingTargets(false);
    }
  }

  async function targetAction(id, action, body = {}, successMessage = "目标操作已提交") {
    const actionKey = `${id}-${action}`;
    setTargetActionKey(actionKey);
    try {
      const result = await api(
        "/targets/" + id + "/" + action,
        { method: "POST", body }
      );
      const records = Number(result?.records_seen ?? result?.records_written);
      if (Number.isFinite(records) && action === "backfill") {
        notifyOk(records > 0 ? `${successMessage}，处理 ${records} 条` : `${successMessage}，暂无新消息`);
      } else {
        notifyOk(successMessage);
      }
      await reload();
    } catch (error) {
      notifyError(error);
    } finally {
      setTargetActionKey("");
    }
  }

  function targetBackfill(id, range) {
    const body = { limit: Math.max(1, Math.min(20000, Number(range.limit) || 10000)) };
    if (range.days) body.since_days = range.days;
    else body.since_hours = range.hours;
    return targetAction(
      id,
      "backfill",
      body,
      `${range.label}采集完成`
    );
  }

  function openCustomBackfill(targetId) {
    setCustomBackfill({ ...defaultCustomBackfill, targetId });
    setCustomBackfillOpen(true);
  }

  function updateCustomBackfill(key, value) {
    setCustomBackfill((current) => ({ ...current, [key]: value }));
  }

  async function submitCustomBackfill() {
    const targetId = customBackfill.targetId || selectedTarget?.id;
    if (!targetId) return;
    const range = buildCustomBackfillRange(customBackfill);
    const limit = Math.max(1, Math.min(20000, Number(customBackfill.limit) || 10000));
    setCustomBackfillOpen(false);
    await targetBackfill(targetId, { ...range, limit });
  }

  async function saveTargetEdit() {
    if (!selectedTarget) return;
    try {
      const updated = await api("/targets/" + selectedTarget.id, {
        method: "PATCH",
        body: {
          account_id: targetEdit.account_id ? Number(targetEdit.account_id) : null,
          account_id_set: true,
          target_group: targetEdit.target_group || "",
          enabled: Boolean(targetEdit.enabled)
        }
      });
      setSelectedTarget(updated);
      notifyOk("监控目标已更新");
      await reload();
    } catch (error) {
      notifyError(error);
    }
  }

  async function syncTargetTitle(target) {
    setSyncingTitleId(target.id);
    try {
      const updated = await api("/targets/" + target.id + "/sync-title", { method: "POST" });
      setSelectedTarget(updated);
      notifyOk("已同步 Telegram 群组/频道名称");
      await reload();
    } catch (error) {
      notifyError(error);
    } finally {
      setSyncingTitleId(null);
    }
  }

  async function syncAllTargetMetadata() {
    setSyncingTargetMetadata(true);
    try {
      const result = await api("/targets/sync-metadata", { method: "POST" });
      notifyOk(`群组信息已刷新：成功 ${result.updated || 0}，失败 ${result.failed || 0}`);
      await reload();
      if (selectedTarget) {
        const latest = await api("/targets");
        const updated = latest.find((target) => target.id === selectedTarget.id);
        if (updated) setSelectedTarget(updated);
      }
    } catch (error) {
      notifyError(error);
    } finally {
      setSyncingTargetMetadata(false);
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
          target_type: bulkOptions.target_type,
          target_group: bulkOptions.target_group || ""
        }
      });
      const checkedItems = result.items.filter((item) => ["ready", "accessible"].includes(item.status));
      if (!checkedItems.length) {
        setParseResult(result);
        notifyOk("解析完成：可导入 " + result.importable + "，重复 " + result.duplicated + "，错误 " + result.invalid);
        return;
      }
      try {
        const checked = await api("/targets/check-bulk", {
          method: "POST",
          body: {
            items: checkedItems,
            account_id: bulkOptions.account_id ? Number(bulkOptions.account_id) : null,
            auto_join_invites: Boolean(bulkOptions.autoJoinInvites)
          }
        });
        const nextResult = buildCheckedParseResult(result.items, checked.items, bulkOptions.target_group, result.raw_total ?? result.total);
        setParseResult(nextResult);
        notifyOk("解析并检测完成：可导入 " + nextResult.importable + "，重复 " + nextResult.duplicated + "，错误 " + nextResult.invalid);
      } catch (checkError) {
        setParseResult(result);
        notifyError(checkError);
      }
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
    let sourceItems = parseResult.items;
    setImporting(true);
    try {
      const items = bulkOptions.onlyReady
        ? sourceItems.filter((item) => ["ready", "accessible"].includes(item.status))
        : sourceItems;
      const targetGroup = bulkOptions.target_group || "";
      const result = await api("/targets/bulk", { method: "POST", body: { items: items.map((item) => ({ ...item, target_group: targetGroup })) } });
      notifyOk("导入完成：新增 " + result.created_count + "，跳过 " + result.skipped_count + "，已加入初始化队列");
      setParseResult(null);
      await reload();
      refreshAfterImport();
    } catch (error) {
      notifyError(error);
    } finally {
      setImporting(false);
    }
  }

  function refreshAfterImport() {
    [2000, 5000, 10000, 20000, 40000, 60000].forEach((delay) => {
      window.setTimeout(() => {
        reload().catch(() => {});
      }, delay);
    });
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
      setParseResult(buildCheckedParseResult(parseResult.items, result.items, bulkOptions.target_group, parseResult.raw_total ?? parseResult.total));
      notifyOk("校验完成：可访问 " + result.accessible + "，失败 " + result.failed);
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
      const dialogs = await api("/telegram/accounts/" + accountId + "/dialogs");
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
      setImportDrawerOpen(true);
      notifyOk("已同步 " + items.length + " 个群组/频道，确认后可导入");
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
    setImportDrawerOpen(true);
    notifyOk("已读取文件：" + file.name);
  }

  async function exportTargets(format) {
    try {
      const response = await fetch(API_BASE + "/targets/export?format=" + format, {
        headers: { Authorization: "Bearer " + getToken() }
      });
      if (!response.ok) throw new Error("导出目标失败");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "watchout-telegram-targets." + format;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      notifyError(error);
    }
  }

  const clearImport = () => {
    setBulkText("");
    setParseResult(null);
  };

  const parseStatusColor = (status) => {
    if (["ready", "accessible"].includes(status)) return "teal";
    if (status === "duplicate") return "blue";
    if (["invalid", "failed"].includes(status)) return "red";
    return "gray";
  };

  return (
    <Stack className="targets-view" gap="md">
      <Group justify="space-between" align="flex-end">
        <Stack gap={4}>
          <Title order={3}>目标概览</Title>
          <Text size="sm" c="dimmed">启用目标会在服务启动后自动恢复监听，并纳入定时回爬与补偿采集。</Text>
        </Stack>
        <Group gap="xs">
          <Button leftSection={<IconUpload size={15} />} onClick={() => setImportDrawerOpen(true)}>批量导入</Button>
          <Button variant="light" leftSection={<IconUsers size={15} />} onClick={syncAccountDialogs} loading={syncingDialogs}>同步已加入</Button>
          <Menu shadow="md" width={150} position="bottom-end">
            <Menu.Target>
              <Button variant="light" leftSection={<IconTableExport size={15} />}>导出</Button>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item onClick={() => exportTargets("csv")}>CSV</Menu.Item>
              <Menu.Item onClick={() => exportTargets("json")}>JSON</Menu.Item>
            </Menu.Dropdown>
          </Menu>
        </Group>
      </Group>

      <SimpleGrid cols={{ base: 2, md: 5 }}>
        <KpiCard icon={IconTarget} label="目标总数" value={targetStats.total} sub={`已启用 ${targetStats.enabled}`} />
        <KpiCard icon={IconPlayerPlay} label="监听中" value={targetStats.running} sub="Runtime运行状态，不等于采集正常" color="teal" />
        <KpiCard icon={IconHistory} label="等待回爬" value={targetStats.idle} sub="未监听，等待定时或手动回爬" color="gray" />
        <KpiCard icon={IconAlertTriangle} label="异常" value={targetStats.failed} sub={longQuietCount ? `另有 ${longQuietCount} 个长期无消息` : "需排查账号或权限"} color="red" />
        <KpiCard icon={IconMessageSearch} label="24小时活跃目标" value={`${targetStats.recent}/${Math.max(targetStats.enabled, targetStats.total) || 0}`} sub="近24小时有新消息的目标" color="blue" />
      </SimpleGrid>

      <Card withBorder radius="lg" p={0} className="target-table-card">
        <Stack gap="sm" px="md" py="md" className="target-table-toolbar">
          <Group justify="space-between" align="flex-start">
            <Box>
              <Title order={3}>监控目标列表</Title>
              <Text size="sm" c="dimmed">当前显示 {pagedTargets.length} / {filteredTargets.length} 个匹配目标，共 {targets.length} 个目标，已选 {selectedTargetIds.length} 个。</Text>
            </Box>
            <Text size="xs" c="dimmed" className="target-refresh-time">更新于 {relativeTimeLabel(targetLastUpdatedAt)}</Text>
          </Group>
          <Group justify="space-between" align="center" gap="md" className="target-toolbar-row">
            <Group gap="sm" className="target-filter-controls">
              <TextInput w={220} leftSection={<IconSearch size={15} />} placeholder="搜索群组、链接、账号" value={targetSearch} onChange={(event) => setTargetSearch(event.currentTarget.value)} />
              <Select
                w={150}
                value={targetStatusFilter}
                onChange={(value) => setTargetStatusFilter(value || "all")}
                data={[
                  { value: "all", label: "全部状态" },
                  { value: "normal", label: "正常" },
                  { value: "stale", label: "长期无消息" },
                  { value: "error", label: "异常" },
                  { value: "stopped", label: "已停止" }
                ]}
              />
              <Select
                w={150}
                value={targetGroupFilter}
                onChange={(value) => setTargetGroupFilter(value || "all")}
                data={targetGroupFilterOptions}
                searchable
              />
              <SegmentedControl
                size="xs"
                className="page-size-control"
                value={targetPageSize}
                onChange={setTargetPageSize}
                data={[
                  { value: "25", label: "25" },
                  { value: "50", label: "50" },
                  { value: "100", label: "100" },
                  { value: "200", label: "200" }
                ]}
              />
            </Group>
            <Group gap="sm" className="target-action-controls">
              <Tooltip label="从 Telegram 更新名称、成员数、简介等信息">
                <Button variant="light" loading={syncingTargetMetadata} leftSection={<IconCloudDownload size={15} />} onClick={syncAllTargetMetadata}>同步群组信息</Button>
              </Tooltip>
              <Button color="red" variant="light" leftSection={<IconTrash size={15} />} disabled={!selectedTargetIds.length} onClick={() => openDeleteTargets(selectedTargetIds)}>删除选中</Button>
            </Group>
          </Group>
        </Stack>
        <Table.ScrollContainer minWidth={1120}>
          <Table verticalSpacing="sm" horizontalSpacing="md" striped highlightOnHover className="target-table">
            <Table.Thead>
              <Table.Tr>
                <Table.Th w={38}><Checkbox size="xs" checked={allTargetsPageSelected} indeterminate={!allTargetsPageSelected && someTargetsPageSelected} onChange={(event) => toggleTargetPage(event.currentTarget.checked)} /></Table.Th>
                <SortHeader label="群组 / 频道" sortKey="name" width={270} />
                <SortHeader label="所在分组" sortKey="group" width={110} />
                <SortHeader label="成员数" sortKey="participants" width={86} />
                <SortHeader label="优先账号" sortKey="account" width={120} />
                <SortHeader label="最近消息" sortKey="last_message_at" width={118} />
                <SortHeader label="监控状态" sortKey="status" width={190} />
                <SortHeader label="上次回爬任务" sortKey="last_run_at" width={170} />
                <Table.Th w={116}>操作</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {pagedTargets.map((target) => {
                const activity = targetActivityInfo(target.last_message_at);
                const listening = isTargetListening(target);
                const statusHint = targetStatusHint(target);
                return (
                <Table.Tr key={target.id} className="target-table-row" onClick={() => openTarget(target)}>
                  <Table.Td onClick={(event) => event.stopPropagation()}>
                    <Checkbox size="xs" checked={targetSelectedSet.has(target.id)} onChange={(event) => toggleTarget(target.id, event.currentTarget.checked)} />
                  </Table.Td>
                  <Table.Td>
                    <Group gap="xs" wrap="nowrap">
                      <ThemeIcon size={30} radius="md" variant="light" color={targetDisplayColor(target)}>
                        <IconBrandTelegram size={16} />
                      </ThemeIcon>
                      <Box className="grow">
                        <Group gap={6} wrap="nowrap">
                          <Text fw={800} truncate="end" maw={190}>{targetDisplayName(target)}</Text>
                        </Group>
                        <Text size="xs" c="dimmed" maw={210} truncate="end">{targetDisplayHandle(target)}</Text>
                      </Box>
                    </Group>
                  </Table.Td>
                  <Table.Td>
                    {target.target_group ? <Badge variant="light" color="cyan">{target.target_group}</Badge> : <Text size="xs" c="dimmed">未分组</Text>}
                  </Table.Td>
                  <Table.Td>{formatCount(target.participants_count)}</Table.Td>
                  <Table.Td><Text size="sm" maw={110} truncate="end">{target.account_id ? accountName(target.account_id) : "未分配"}</Text></Table.Td>
                  <Table.Td>
                    <Stack gap={2}>
                      <Text size="sm" c={targetActivityColor(target.last_message_at)}>{formatCompactTime(target.last_message_at)}</Text>
                      <Text size="xs" c={activity.color}>{activity.relative}</Text>
                    </Stack>
                  </Table.Td>
                  <Table.Td>
                    <Stack gap={3}>
                      <StatusBadge value={target.enabled ? target.status : "disabled"} label={targetRuntimeLabel(target)} />
                      {listening ? <Text size="xs" c={activity.color} maw={170} truncate="end">监听中｜{activity.label}</Text> : null}
                      {statusHint ? <Text size="xs" c={target.last_error ? "red" : "dimmed"} maw={170} truncate="end">{statusHint}</Text> : null}
                    </Stack>
                  </Table.Td>
                  <Table.Td>
                    <LastRunSummary target={target} />
                  </Table.Td>
                  <Table.Td onClick={(event) => event.stopPropagation()}>
                    <Group gap={4} wrap="nowrap" className="target-row-actions">
                      {listening ? (
                        <Tooltip label="停止实时监听">
                          <ActionIcon aria-label="停止实时监听" size="sm" color="gray" variant="light" loading={targetActionKey === `${target.id}-stop`} disabled={Boolean(targetActionKey)} onClick={() => targetAction(target.id, "stop", {}, "监听已停止")}>
                            <IconSquare size={15} />
                          </ActionIcon>
                        </Tooltip>
                      ) : (
                        <Tooltip label="启动实时监听并采集近4小时">
                          <ActionIcon aria-label="启动实时监听" size="sm" variant="light" loading={targetActionKey === `${target.id}-start`} disabled={!target.enabled || Boolean(targetActionKey)} onClick={() => targetAction(target.id, "start", {}, "实时监听已启动，已采集近4小时")}>
                            <IconPlayerPlay size={15} />
                          </ActionIcon>
                        </Tooltip>
                      )}
                      <Tooltip label="查看消息">
                        <ActionIcon aria-label="查看目标消息" size="sm" variant="subtle" onClick={() => openMessages(target.id)}>
                          <IconMessageSearch size={15} />
                        </ActionIcon>
                      </Tooltip>
                      <Menu shadow="md" width={170} position="bottom-end">
                        <Menu.Target>
                          <Tooltip label="更多操作">
                            <ActionIcon aria-label="更多目标操作" size="sm" variant="light" disabled={Boolean(targetActionKey)}>
                              <IconDotsVertical size={15} />
                            </ActionIcon>
                          </Tooltip>
                        </Menu.Target>
                        <Menu.Dropdown>
                          <Menu.Label>快捷回爬</Menu.Label>
                          {backfillQuickRanges.map((range) => (
                            <Menu.Item key={range.label} leftSection={<IconHistory size={14} />} disabled={!target.enabled || Boolean(targetActionKey)} onClick={() => targetBackfill(target.id, range)}>立即回爬：{range.label}</Menu.Item>
                          ))}
                          <Menu.Divider />
                          <Menu.Item
                            closeMenuOnClick={false}
                            leftSection={extendedBackfillOpen ? <IconChevronLeft size={14} /> : <IconChevronRight size={14} />}
                            disabled={!target.enabled || Boolean(targetActionKey)}
                            onClick={() => setExtendedBackfillOpen((value) => !value)}
                          >
                            更长范围
                          </Menu.Item>
                          <Collapse in={extendedBackfillOpen}>
                            {backfillExtendedRanges.map((range) => (
                              <Menu.Item key={range.label} leftSection={<IconHistory size={14} />} disabled={!target.enabled || Boolean(targetActionKey)} onClick={() => targetBackfill(target.id, range)}>立即回爬：{range.label}</Menu.Item>
                            ))}
                          </Collapse>
                          <Menu.Item leftSection={<IconEdit size={14} />} disabled={!target.enabled || Boolean(targetActionKey)} onClick={() => openCustomBackfill(target.id)}>自定义时间...</Menu.Item>
                          <Menu.Divider />
                          <Menu.Item leftSection={<IconRefresh size={14} />} disabled={syncingTitleId === target.id} onClick={() => syncTargetTitle(target)}>同步群组信息</Menu.Item>
                          <Menu.Item color="red" leftSection={<IconTrash size={14} />} onClick={() => openDeleteTargets([target.id])}>删除目标</Menu.Item>
                          <Menu.Item leftSection={<IconCircleCheck size={14} />} disabled>可访问性检测（导入页可用）</Menu.Item>
                        </Menu.Dropdown>
                      </Menu>
                    </Group>
                  </Table.Td>
                </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        {!filteredTargets.length ? <EmptyState text="没有匹配的监控目标。可以调整筛选，或点击批量导入新增目标。" /> : null}
        {filteredTargets.length ? (
          <Group justify="space-between" px="md" py="sm" className="target-table-footer">
            <Text size="sm" c="dimmed">第 {currentPage} / {totalPages} 页，{pageStart + 1}-{Math.min(pageStart + pageSize, filteredTargets.length)} / {filteredTargets.length}</Text>
            <Pagination size="sm" total={totalPages} value={currentPage} onChange={setTargetPage} />
          </Group>
        ) : null}
      </Card>

      <Drawer opened={importDrawerOpen} onClose={() => setImportDrawerOpen(false)} title="导入监控目标" position="right" size="xl">
        <Stack gap="md">
          <Alert color="cyan" variant="light">支持 @username、t.me 链接、邀请链接、CSV/JSON 粘贴。建议先解析预览，再做可访问性检测，最后导入。</Alert>
          <SimpleGrid cols={{ base: 1, md: 3 }}>
            <Select label="优先采集账号" placeholder="自动分配可用账号" data={accountOptions} value={bulkOptions.account_id} onChange={(value) => setBulkOptions({ ...bulkOptions, account_id: value || "" })} clearable searchable />
            <Select
              label="目标类型"
              data={[{ value: "auto", label: "自动识别" }, { value: "group", label: "群组" }, { value: "channel", label: "频道" }, { value: "private", label: "私聊" }]}
              value={bulkOptions.target_type}
              onChange={(value) => setBulkOptions({ ...bulkOptions, target_type: value || "auto" })}
            />
            <Select
              label="创建/选择分组"
              placeholder="输入新分组，或选择已有分组"
              data={importTargetGroupOptions}
              value={bulkOptions.target_group}
              onChange={(value) => setBulkOptions({ ...bulkOptions, target_group: value || "" })}
              searchValue={bulkOptions.target_group}
              onSearchChange={(value) => setBulkOptions({ ...bulkOptions, target_group: value })}
              searchable
              clearable
            />
          </SimpleGrid>
          <Textarea
            minRows={7}
            maxRows={14}
            autosize
            label="目标列表"
            description="一行一个目标；也可以直接粘贴 CSV 第一列或 JSON 数组"
            placeholder="在这里粘贴要导入的真实 Telegram 目标，每行一个"
            value={bulkText}
            onChange={(event) => setBulkText(event.currentTarget.value)}
          />
          <Paper withBorder radius="md" p="md" className="format-help">
            <Group justify="space-between" align="flex-start">
              <Stack gap="xs">
                <Checkbox label="自动加入邀请链接" checked={Boolean(bulkOptions.autoJoinInvites)} onChange={(event) => setBulkOptions({ ...bulkOptions, autoJoinInvites: event.currentTarget.checked })} />
                <Checkbox label="仅导入可用目标" checked={bulkOptions.onlyReady} onChange={(event) => setBulkOptions({ ...bulkOptions, onlyReady: event.currentTarget.checked })} />
              </Stack>
              <FileButton onChange={importTargetFile} accept=".txt,.csv,.json,text/plain,text/csv,application/json">
                {(props) => <Button {...props} variant="light" leftSection={<IconUpload size={15} />}>选择文件</Button>}
              </FileButton>
            </Group>
          </Paper>
          <Group justify="flex-end" gap="xs">
            <Button variant="subtle" color="gray" leftSection={<IconX size={15} />} onClick={clearImport}>清空</Button>
            <Button variant="light" onClick={parseBulkTargets} loading={parsing}>解析并检测</Button>
            <Button variant="light" onClick={checkBulkTargets} loading={checkingTargets} disabled={!parseResult?.importable}>重新检测</Button>
            <Button onClick={importBulkTargets} loading={importing} disabled={!parseResult?.importable}>导入目标</Button>
          </Group>
          {parseResult ? (
            <Card withBorder radius="md" p="md" className="parse-preview">
              <Group justify="space-between" mb="sm">
                <Group>
                  <Badge color="teal">可导入 {parseResult.importable}</Badge>
                  <Badge color="blue">重复 {parseResult.duplicated}</Badge>
                  <Badge color="red">错误 {parseResult.invalid}</Badge>
                </Group>
                <Text size="sm" c="dimmed">
                  共解析{parseResult.raw_total ?? parseResult.total}条｜展示{parseResult.total}条｜可导入{parseResult.importable}条｜重复{parseResult.duplicated}条｜失败{parseResult.invalid}条
                </Text>
              </Group>
              <Table.ScrollContainer minWidth={920}>
                <Table verticalSpacing="sm" className="target-preview-table">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>原始输入</Table.Th>
                      <Table.Th>识别结果</Table.Th>
                      <Table.Th>类型</Table.Th>
                      <Table.Th>所在分组</Table.Th>
                      <Table.Th>成员数</Table.Th>
                      <Table.Th>状态</Table.Th>
                      <Table.Th>原因</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {parseResult.items.map((item) => (
                      <Table.Tr key={item.line + "-" + item.raw}>
                        <Table.Td><Text size="sm" maw={240} truncate="end">{item.raw}</Text></Table.Td>
                        <Table.Td>
                          <Text size="sm" fw={700} maw={230} truncate="end">{item.title || item.normalized_target || "-"}</Text>
                          <Text size="xs" c="dimmed" maw={230} truncate="end">{item.normalized_target || item.target || "-"}</Text>
                        </Table.Td>
                        <Table.Td><Badge variant="light">{previewTargetTypeLabel(item)}</Badge></Table.Td>
                        <Table.Td>{bulkOptions.target_group ? <Badge variant="light" color="cyan">{bulkOptions.target_group}</Badge> : <Text size="xs" c="dimmed">未分组</Text>}</Table.Td>
                        <Table.Td>{formatCount(item.participants_count)}</Table.Td>
                        <Table.Td><Badge color={parseStatusColor(item.status)} variant="light">{parseStatusLabel(item.status)}</Badge></Table.Td>
                        <Table.Td><Text size="sm" c={["invalid", "failed"].includes(item.status) ? "red" : "dimmed"} maw={260} truncate="end">{item.reason || "可导入"}</Text></Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            </Card>
          ) : null}
        </Stack>
      </Drawer>

      <Drawer opened={Boolean(selectedTarget)} onClose={() => setSelectedTarget(null)} title="监控目标详情" position="right" size="lg">
        {selectedTarget ? (
          <Stack gap="lg" className="target-detail">
            <Paper withBorder radius="md" p="md" className="target-detail-hero">
              <Group justify="space-between" align="flex-start" wrap="nowrap">
                <Group gap="sm" align="flex-start" wrap="nowrap">
                  <ThemeIcon size={42} radius="md" variant="light" color={targetDisplayColor(selectedTarget)}>
                    <IconBrandTelegram size={22} />
                  </ThemeIcon>
                  <Box className="grow">
                    <Group gap="xs" align="center">
                      <Title order={3} className="target-detail-title">{targetDisplayName(selectedTarget)}</Title>
                    </Group>
                    <Text size="sm" c="dimmed" mt={2}>{targetDisplayHandle(selectedTarget)}</Text>
                  </Box>
                </Group>
                <StatusBadge value={selectedTarget.enabled ? selectedTarget.status : "disabled"} label={targetRuntimeLabel(selectedTarget)} />
              </Group>
              <SimpleGrid cols={{ base: 2, sm: 4 }} mt="md" spacing="xs">
                <TargetMetric label="成员数" value={formatCount(selectedTarget.participants_count)} />
                <TargetMetric label="最近消息" value={selectedTarget.last_message_at ? relativeTimeLabel(selectedTarget.last_message_at) : "暂无消息"} />
                <TargetMetric label="优先账号" value={selectedTarget.account_id ? accountName(selectedTarget.account_id) : "未分配"} />
                <TargetMetric label="所在分组" value={selectedTarget.target_group || "未分组"} />
              </SimpleGrid>
            </Paper>

            <Paper withBorder p="md" radius="md" className="target-config-panel">
              <Stack gap="md">
                <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
                  <Select
                    label="优先采集账号"
                    description="失效时自动切换到其他可用账号"
                    placeholder="自动分配可用账号"
                    data={accountOptions}
                    value={targetEdit.account_id}
                    onChange={(value) => setTargetEdit({ ...targetEdit, account_id: value || "" })}
                    clearable
                    searchable
                    checkIconPosition="right"
                    comboboxProps={{ withinPortal: false, zIndex: 1000 }}
                  />
                  <TextInput
                    label="所在分组"
                    description="用于列表筛选和后续批量管理"
                    placeholder="未分组"
                    value={targetEdit.target_group}
                    onChange={(event) => setTargetEdit({ ...targetEdit, target_group: event.currentTarget.value })}
                  />
                </SimpleGrid>
                <Group justify="space-between" align="center" className="target-config-actions">
                  <Checkbox
                    label="启用目标"
                    checked={targetEdit.enabled}
                    onChange={(event) => setTargetEdit({ ...targetEdit, enabled: event.currentTarget.checked })}
                  />
                  <Button size="sm" onClick={saveTargetEdit}>保存设置</Button>
                </Group>
              </Stack>
            </Paper>

            <Paper withBorder p="md" radius="md" className="target-info-panel">
              <Group justify="space-between" align="center" mb="sm">
                <Text fw={900}>群组信息</Text>
                <Badge size="sm" variant="light" color={selectedTarget.about ? "teal" : "gray"}>
                  简介{selectedTarget.about ? "已同步" : "未获取"}
                </Badge>
              </Group>
              <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="lg">
                <Stack gap={7}>
                  <InfoLine label="群组名" value={targetDisplayName(selectedTarget)} />
                  <InfoLine label="类型" value={targetDisplayTypeLabel(selectedTarget)} />
                  <InfoLine label="目标地址" value={<TargetLink target={selectedTarget} />} />
                </Stack>
                <Stack gap={7}>
                  <InfoLine label="历史消息" value={formatCount(selectedTarget.message_count)} />
                  <InfoLine
                    label="最近消息"
                    value={selectedTarget.last_message_at ? `${formatTime(selectedTarget.last_message_at)}（${relativeTimeLabel(selectedTarget.last_message_at)}）` : "暂无消息"}
                  />
                  <InfoLine label="采集状态" value={targetRuntimeLabel(selectedTarget)} />
                  <InfoLine label="最近错误" value={selectedTarget.last_error || "暂无异常"} danger={Boolean(selectedTarget.last_error)} />
                </Stack>
              </SimpleGrid>
              <Box mt="md">
                <Text size="sm" c="dimmed" mb={4}>简介</Text>
                <Text size="sm" c={selectedTarget.about ? "dark" : "dimmed"} className={aboutExpanded ? "target-about-text" : "target-about-text target-about-collapsed"}>
                  {selectedTarget.about || "暂无简介。公开群组通常可在导入或可访问性检测时同步；私密群、受限群可能无法获取。"}
                </Text>
                {selectedTarget.about ? (
                  <Button size="compact-xs" variant="subtle" mt={6} onClick={() => setAboutExpanded((value) => !value)}>
                    {aboutExpanded ? "收起" : "展开全文"}
                  </Button>
                ) : null}
              </Box>
            </Paper>
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <Button loading={targetActionKey === `${selectedTarget.id}-start`} disabled={!selectedTarget.enabled || isTargetListening(selectedTarget) || Boolean(targetActionKey)} leftSection={<IconPlayerPlay size={14} />} onClick={() => targetAction(selectedTarget.id, "start", {}, "实时监听已启动，已采集近4小时")}>{isTargetListening(selectedTarget) ? "已在监听" : "启动实时监听"}</Button>
              <Button loading={targetActionKey === `${selectedTarget.id}-stop`} disabled={Boolean(targetActionKey)} color="gray" variant="light" leftSection={<IconSquare size={14} />} onClick={() => targetAction(selectedTarget.id, "stop", {}, "监听已停止")}>停止监听</Button>
              <Menu shadow="md" width={180}>
                <Menu.Target>
                  <Button loading={targetActionKey === `${selectedTarget.id}-backfill`} disabled={!selectedTarget.enabled || Boolean(targetActionKey)} variant="light" leftSection={<IconHistory size={14} />}>选择采集范围</Button>
                </Menu.Target>
                <Menu.Dropdown>
                  <Menu.Label>快捷回爬</Menu.Label>
                  {backfillQuickRanges.map((range) => (
                    <Menu.Item key={range.label} leftSection={<IconHistory size={14} />} onClick={() => targetBackfill(selectedTarget.id, range)}>{range.label}</Menu.Item>
                  ))}
                  <Menu.Divider />
                  <Menu.Item
                    closeMenuOnClick={false}
                    leftSection={extendedBackfillOpen ? <IconChevronLeft size={14} /> : <IconChevronRight size={14} />}
                    onClick={() => setExtendedBackfillOpen((value) => !value)}
                  >
                    更长范围
                  </Menu.Item>
                  <Collapse in={extendedBackfillOpen}>
                    {backfillExtendedRanges.map((range) => (
                      <Menu.Item key={range.label} leftSection={<IconHistory size={14} />} onClick={() => targetBackfill(selectedTarget.id, range)}>{range.label}</Menu.Item>
                    ))}
                  </Collapse>
                  <Menu.Item leftSection={<IconEdit size={14} />} onClick={() => openCustomBackfill(selectedTarget.id)}>自定义时间...</Menu.Item>
                </Menu.Dropdown>
              </Menu>
              <Button variant="subtle" leftSection={<IconMessageSearch size={14} />} onClick={() => openMessages(selectedTarget.id)}>查看消息</Button>
              <Button color="red" variant="light" leftSection={<IconTrash size={14} />} onClick={() => openDeleteTargets([selectedTarget.id])}>删除目标</Button>
            </SimpleGrid>
          </Stack>
        ) : null}
      </Drawer>

      <Modal opened={customBackfillOpen} onClose={() => setCustomBackfillOpen(false)} title="自定义回爬时间" centered>
        <Stack gap="md">
          <Alert color="cyan" icon={<IconHistory size={16} />}>
            适合临时补采更长历史。范围越大耗时越久，建议先保持消息上限在 10000 以内。
          </Alert>
          <SegmentedControl
            value={customBackfill.unit}
            onChange={(value) => updateCustomBackfill("unit", value)}
            data={[
              { value: "hours", label: "小时" },
              { value: "days", label: "天" },
              { value: "months", label: "月" }
            ]}
          />
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <NumberInput
              label="回爬范围"
              min={1}
              max={customBackfill.unit === "hours" ? 168 : customBackfill.unit === "months" ? 12 : 365}
              value={customBackfill.amount}
              onChange={(value) => updateCustomBackfill("amount", value || 1)}
            />
            <NumberInput
              label="消息上限"
              min={1}
              max={20000}
              value={customBackfill.limit}
              onChange={(value) => updateCustomBackfill("limit", value || 10000)}
            />
          </SimpleGrid>
          <Text size="sm" c="dimmed">
            将执行：{customBackfillLabel(customBackfill)}；按月份选择时会按 30 天折算，最长不超过 365 天。
          </Text>
          <Group justify="flex-end">
            <Button variant="subtle" color="gray" onClick={() => setCustomBackfillOpen(false)}>取消</Button>
            <Button loading={Boolean(targetActionKey)} leftSection={<IconHistory size={14} />} onClick={submitCustomBackfill}>
              开始回爬
            </Button>
          </Group>
        </Stack>
      </Modal>

      <Modal opened={targetDeleteOpen} onClose={() => setTargetDeleteOpen(false)} title="删除监控目标" centered>
        <Stack>
          <Alert color="red" icon={<IconAlertTriangle size={16} />}>
            将删除 {selectedTargetIds.length} 个监控目标。删除目标后将停止对应监听，并从目标列表移除。
          </Alert>
          <Checkbox
            label="同时删除这些群组以往爬取的全部消息、命中记录和媒体索引"
            checked={deleteTargetMessages}
            onChange={(event) => setDeleteTargetMessages(event.currentTarget.checked)}
          />
          <Text size="sm" c="dimmed">
            不勾选时会保留历史消息，只解除消息和目标的绑定；勾选后对应消息记录不可恢复。
          </Text>
          <Group justify="flex-end">
            <Button variant="subtle" onClick={() => setTargetDeleteOpen(false)}>取消</Button>
            <Button color="red" loading={deletingTargets} onClick={deleteTargets}>确认删除</Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}

function LastRunSummary({ target }) {
  if (!target?.last_run_id) {
    const status = String(target?.status || "").toLowerCase();
    if (["initializing", "backfilling"].includes(status)) {
      return (
        <Stack gap={2}>
          <Text size="sm" fw={700}>首次回爬进行中</Text>
          <Text size="xs" c="dimmed">完成后自动显示任务结果</Text>
        </Stack>
      );
    }
    return (
      <Stack gap={2}>
        <Text size="sm" c="dimmed">暂无回爬任务</Text>
        <Text size="xs" c="dimmed">等待初始化或定时回爬</Text>
      </Stack>
    );
  }
  return (
    <Stack gap={2}>
      <Text size="sm" fw={700}>#{target.last_run_id} · {formatCount(target.last_run_records)} 条</Text>
      <Text size="xs" c="dimmed">{formatCompactTime(target.last_run_at)} · {relativeTimeLabel(target.last_run_at)}</Text>
    </Stack>
  );
}

function compareTargets(a, b, sort, accountName) {
  const direction = sort.direction === "asc" ? 1 : -1;
  const value = (target) => {
    if (sort.key === "name") return targetDisplayName(target).toLowerCase();
    if (sort.key === "group") return String(target.target_group || "").toLowerCase();
    if (sort.key === "participants") return Number(target.participants_count ?? -1);
    if (sort.key === "account") return String(target.account_id ? accountName(target.account_id) : "").toLowerCase();
    if (sort.key === "last_message_at") return parseTelegramTime(target.last_message_at)?.getTime() || 0;
    if (sort.key === "status") return targetRuntimeLabel(target);
    if (sort.key === "last_run_at") return parseTelegramTime(target.last_run_at)?.getTime() || 0;
    return target.id || 0;
  };
  const left = value(a);
  const right = value(b);
  if (typeof left === "number" && typeof right === "number") {
    return (left - right) * direction || ((a.id || 0) - (b.id || 0));
  }
  return String(left).localeCompare(String(right), "zh-CN") * direction || ((a.id || 0) - (b.id || 0));
}

function buildCheckedParseResult(sourceItems, checkedItems, fallbackGroup = "", rawTotal = sourceItems.length) {
  const byKey = new Map(checkedItems.map((item) => [item.line + "-" + item.raw, item]));
  const mergedItems = sourceItems.map((item) => {
    const checked = byKey.get(item.line + "-" + item.raw);
    if (!checked) return item;
    return {
      ...item,
      status: checked.status === "accessible" ? "accessible" : "invalid",
      category: checked.category,
      reason: checked.reason,
      title: checked.title || item.title,
      target_type: checked.target_type || item.target_type,
      target_group: checked.target_group ?? item.target_group ?? fallbackGroup ?? "",
      participants_count: checked.participants_count ?? item.participants_count,
      about: checked.about ?? item.about
    };
  });
  const items = [];
  const seen = new Set();
  let mergedDuplicates = Math.max(0, rawTotal - sourceItems.length);
  for (const item of mergedItems) {
    const dedupeKey = targetPreviewDedupeKey(item);
    if (dedupeKey && seen.has(dedupeKey)) {
      mergedDuplicates += 1;
      continue;
    }
    if (dedupeKey) seen.add(dedupeKey);
    items.push(item);
  }
  return {
    items,
    total: items.length,
    raw_total: rawTotal,
    importable: items.filter((item) => ["ready", "accessible"].includes(item.status)).length,
    duplicated: mergedDuplicates + items.filter((item) => item.status === "duplicate").length,
    invalid: items.filter((item) => item.status === "invalid").length
  };
}

function targetPreviewDedupeKey(item) {
  const normalized = String(item?.normalized_target || item?.target || "").trim().toLowerCase();
  const title = String(item?.title || "").trim().toLowerCase();
  const type = String(item?.target_type || "").trim().toLowerCase();
  const participants = item?.participants_count ?? "";
  if (title && participants !== "") return `meta:${type}:${title}:${participants}`;
  if (normalized) return `target:${normalized.replace(/^@/, "")}`;
  return "";
}

function targetTypeLabel(value = "") {
  return ({ group: "群组", supergroup: "超级群", channel: "频道", private: "私聊", invite: "邀请链接", public: "公开目标" }[String(value).toLowerCase()] || value || "-");
}

function isInviteTarget(value = "") {
  const text = String(value || "").trim();
  return text.startsWith("+") || text.startsWith("joinchat/") || /t\.me\/(\+|joinchat\/)/i.test(text);
}

function previewTargetTypeLabel(item) {
  if (item?.detected_type === "invite" || isInviteTarget(item?.normalized_target || item?.target)) return "邀请链接";
  return targetTypeLabel(item?.target_type);
}

function targetDisplayTypeLabel(target) {
  if (isInviteTarget(target?.normalized_target || target?.target)) return "邀请链接";
  return targetTypeLabel(target?.target_type);
}

function targetDisplayName(target) {
  const title = String(target?.title || "").trim();
  if (title && !/^Telegram\s*\/\s*/i.test(title) && !/^https?:\/\/t\.me\//i.test(title)) return title;
  return targetDisplayHandle(target);
}

function targetDisplayHandle(target) {
  const normalized = String(target?.normalized_target || "").trim();
  if (!normalized) return target?.target || "-";
  if (isInviteTarget(normalized)) return normalized.startsWith("+") ? normalized : `t.me/${normalized}`;
  if (/^-?\d+$/.test(normalized)) return normalized;
  return normalized.startsWith("@") ? normalized : `@${normalized}`;
}

function targetUrl(target) {
  const raw = String(target?.target || "").trim();
  if (/^https?:\/\//i.test(raw)) return raw;
  const normalized = String(target?.normalized_target || raw || "").trim().replace(/^@/, "");
  if (!normalized || /^-?\d+$/.test(normalized)) return "";
  if (normalized.startsWith("+")) return `https://t.me/${normalized}`;
  if (normalized.startsWith("joinchat/")) return `https://t.me/${normalized}`;
  return `https://t.me/${normalized}`;
}

function targetDisplayColor(target) {
  if (!target?.enabled) return "gray";
  if (target?.last_error) return "red";
  if (isTargetListening(target)) return "teal";
  if (String(target?.status).toLowerCase() === "initializing") return "blue";
  if (String(target?.status).toLowerCase() === "backfilling") return "yellow";
  return "blue";
}

function targetRuntimeLabel(target) {
  if (!target?.enabled) return "已暂停";
  if (target?.last_error) return "异常";
  if (isTargetListening(target)) return "监听中";
  if (String(target?.status).toLowerCase() === "initializing") return "初始化中";
  if (String(target?.status).toLowerCase() === "backfilling") return "采集中";
  if (target?.last_run_id || target?.last_message_at) return "待监听";
  return "等待调度";
}

function isTargetListening(target) {
  return ["listening", "running"].includes(String(target?.status).toLowerCase());
}

function targetStatusHint(target) {
  if (!target?.enabled) return "已禁用，不会监听或回填";
  if (target?.last_error) return target.last_error;
  const status = String(target?.status || "").toLowerCase();
  if (isTargetListening(target)) return "";
  if (status === "initializing") return "正在排队或执行首次回爬";
  if (status === "backfilling") return "正在执行历史回填";
  if (target?.last_run_id || target?.last_message_at) return "已有采集记录，等待监听恢复或下次定时采集";
  if (target?.account_id) return "有优先账号，待调度";
  return "自动分配账号，待调度";
}

function formatCount(value) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return number.toLocaleString("zh-CN");
}

function relativeTimeLabel(value) {
  const date = parseTelegramTime(value);
  if (!date) return "-";
  const diffMs = Date.now() - date.getTime();
  if (diffMs < 0) return "刚刚";
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes}分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}小时前`;
  const days = Math.floor(hours / 24);
  return `${days}天前`;
}

function parseStatusLabel(value = "") {
  return ({ ready: "可导入", accessible: "可访问", duplicate: "重复", invalid: "错误", failed: "失败" }[String(value).toLowerCase()] || value || "-");
}

function cleanTargetTitle(value = "") {
  return String(value || "-")
    .replace(/^Telegram\s*\/\s*/i, "")
    .replace(/^https?:\/\/t\.me\//i, "")
    .replace(/^@/, "");
}

function InfoLine({ label, value, danger = false }) {
  return (
    <Group justify="space-between" align="flex-start" gap="md" wrap="nowrap" className="info-line">
      <Text size="sm" c="dimmed">{label}</Text>
      <Text component="div" size="sm" fw={600} c={danger ? "red" : undefined} ta="right" className="info-line-value">{value}</Text>
    </Group>
  );
}

function TargetLink({ target }) {
  const href = targetUrl(target);
  const label = target?.target || href || "未检测";
  async function copyTargetLink(event) {
    event.preventDefault();
    event.stopPropagation();
    try {
      await navigator.clipboard.writeText(href || label);
      notifyOk("目标链接已复制");
    } catch (error) {
      notifyError(new Error("复制失败，请手动选择链接"));
    }
  }
  if (!href) return <Text component="span" c="dimmed">{label || "未检测"}</Text>;
  return (
    <Group gap={6} justify="flex-end" wrap="nowrap" className="target-link-group">
      <Anchor href={href} target="_blank" rel="noreferrer" size="sm" fw={700} className="target-link-text">
        {label}
      </Anchor>
      <Tooltip label="复制目标链接">
        <ActionIcon aria-label="复制目标链接" size="xs" variant="subtle" onClick={copyTargetLink}>
          <IconCopy size={13} />
        </ActionIcon>
      </Tooltip>
    </Group>
  );
}

function TargetMetric({ label, value }) {
  return (
    <Paper withBorder radius="md" p="sm" className="target-detail-metric">
      <Text size="xs" c="dimmed">{label}</Text>
      <Text fw={900} size="sm" mt={2} truncate="end">{value}</Text>
    </Paper>
  );
}

function Rules({ rules, channels = [], reload, openMatchesForRule }) {
  const emptyForm = {
    name: "",
    match_type: "contains",
    topic_terms: "",
    signal_terms: "",
    exclude_patterns: "",
    target_filter: "",
    risk_level: 1,
	    priority: 100,
	    notify: true,
	    notification_channel_ids: [],
	    enabled: true
	  };
  const [form, setForm] = useState({
    ...emptyForm
  });
  const [editingRuleId, setEditingRuleId] = useState(null);
  const [selectedRule, setSelectedRule] = useState(null);
  const [ruleActionId, setRuleActionId] = useState(null);
  const [drawerOpened, setDrawerOpened] = useState(false);
  const [reprocessRule, setReprocessRule] = useState(null);
  const [reprocessForm, setReprocessForm] = useState({ limit: "5000", notify_matches: false, reset_existing: true });

  function splitTerms(value, newlineOnly = false) {
    return String(value || "")
      .split(newlineOnly ? /\n/ : /[,，\n]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function ruleTopics(rule) {
    return (rule.tags || []).filter((tag) => tag.startsWith("topic:")).map((tag) => tag.replace(/^topic:/, ""));
  }

  function ruleSignals(rule) {
    const topics = ruleTopics(rule);
    return (rule.patterns || []).filter((pattern) => !topics.includes(pattern));
  }

  function buildRulePayload(source) {
    const regexMode = source.match_type === "regex";
    const topicTerms = splitTerms(source.topic_terms, regexMode);
    const signalTerms = splitTerms(source.signal_terms, regexMode);
    return {
      name: source.name,
      match_type: source.match_type,
      patterns: [...topicTerms, ...signalTerms],
      exclude_patterns: splitTerms(source.exclude_patterns, regexMode),
      target_filter: splitTerms(source.target_filter),
      sender_filter: [],
      risk_level: Number(source.risk_level),
      priority: Number(source.priority),
      enabled: Boolean(source.enabled),
	      notify: Boolean(source.notify),
	      notification_channel_ids: (source.notification_channel_ids || []).map((item) => Number(item)).filter(Boolean),
	      tags: topicTerms.map((term) => `topic:${term}`)
	    };
	  }

  function resetRuleForm() {
    setForm({ ...emptyForm });
    setEditingRuleId(null);
  }

  function openRuleDrawer(rule = null) {
    if (rule) {
      editRule(rule, { open: false });
    } else {
      resetRuleForm();
    }
    setDrawerOpened(true);
  }

  function editRule(rule, options = { open: true }) {
    setEditingRuleId(rule.id);
    setForm({
      name: rule.name || "",
      match_type: rule.match_type || "contains",
      topic_terms: ruleTopics(rule).join("\n"),
      signal_terms: ruleSignals(rule).join("\n"),
      exclude_patterns: (rule.exclude_patterns || []).join("\n"),
      target_filter: (rule.target_filter || []).join("\n"),
      risk_level: rule.risk_level ?? 1,
	      priority: rule.priority ?? 100,
	      notify: Boolean(rule.notify),
	      notification_channel_ids: (rule.notification_channel_ids || []).map((item) => String(item)),
	      enabled: Boolean(rule.enabled)
	    });
    if (options.open) setDrawerOpened(true);
  }

  function validateRegexPayload(payload) {
    if (payload.match_type !== "regex") return;
    [...payload.patterns, ...payload.exclude_patterns].forEach((pattern) => {
      try {
        new RegExp(pattern);
      } catch (error) {
        throw new Error(`正则表达式无效：${pattern}`);
      }
    });
  }

  async function create(event) {
    event.preventDefault();
    try {
      const payload = buildRulePayload(form);
      validateRegexPayload(payload);
      await api(editingRuleId ? `/rules/${editingRuleId}` : "/rules", {
        method: editingRuleId ? "PATCH" : "POST",
        body: payload
      });
      resetRuleForm();
      setDrawerOpened(false);
      notifyOk(editingRuleId ? "监控规则已保存" : "监控规则已新增");
      await reload();
    } catch (error) {
      notifyError(error);
    }
  }

  async function toggleRule(rule, enabled) {
    setRuleActionId(rule.id);
    try {
      await api(`/rules/${rule.id}`, {
        method: "PATCH",
        body: {
          ...rule,
	          enabled,
	          notification_channel_ids: rule.notification_channel_ids || [],
	          sender_filter: rule.sender_filter || [],
          target_filter: rule.target_filter || [],
          exclude_patterns: rule.exclude_patterns || [],
          patterns: rule.patterns || [],
          tags: rule.tags || []
        }
      });
      notifyOk(enabled ? "规则已启用" : "规则已停用");
      await reload();
    } catch (error) {
      notifyError(error);
    } finally {
      setRuleActionId(null);
    }
  }

  async function deleteRule(rule) {
    if (!window.confirm(`确定删除规则「${rule.name}」吗？已有命中记录会保留，但不再关联新规则。`)) return;
    setRuleActionId(rule.id);
    try {
      await api(`/rules/${rule.id}`, { method: "DELETE" });
      if (editingRuleId === rule.id) resetRuleForm();
      notifyOk("监控规则已删除");
      await reload();
    } catch (error) {
      notifyError(error);
    } finally {
      setRuleActionId(null);
    }
  }

  async function reprocessSingleRule() {
    if (!reprocessRule) return;
    setRuleActionId(reprocessRule.id);
    try {
      const result = await api("/rules/reprocess", {
        method: "POST",
        body: {
          rule_id: reprocessRule.id,
          limit: Number(reprocessForm.limit) || 5000,
          notify_matches: Boolean(reprocessForm.notify_matches),
          reset_existing: Boolean(reprocessForm.reset_existing)
        }
      });
      notifyOk(`历史重扫完成：扫描 ${result.scanned} 条，生成 ${result.created} 条线索${result.notified ? `，推送 ${result.notified} 条` : ""}`);
      setReprocessRule(null);
      await reload();
      openMatchesForRule(reprocessRule);
    } catch (error) {
      notifyError(error);
    } finally {
      setRuleActionId(null);
    }
  }

  return (
    <Stack>
      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        <MetricCard icon={IconListCheck} label="规则总数" value={rules.length} sub="规则是可选加工层" />
        <MetricCard icon={IconCircleCheck} label="启用中" value={rules.filter((rule) => rule.enabled).length} sub="参与新消息匹配" color="teal" />
        <MetricCard icon={IconBell} label="命中通知" value={rules.filter((rule) => rule.notify).length} sub="命中后触发推送" color="blue" />
      </SimpleGrid>
      <Card withBorder radius="lg" p="lg">
        <Group justify="space-between" align="flex-start" mb="md">
          <Stack gap={2}>
            <Title order={3}>监控规则</Title>
            <Text c="dimmed" size="sm">规则是采集后的可选加工层，可以按主题词、信号词或正则表达式生成命中线索。</Text>
          </Stack>
          <Button leftSection={<IconListCheck size={16} />} onClick={() => openRuleDrawer()}>新增规则</Button>
        </Group>
        <Table.ScrollContainer minWidth={1180}>
          <Table verticalSpacing="sm" className="rules-table">
            <Table.Thead>
              <Table.Tr>
                <Table.Th w={190}>规则</Table.Th>
                <Table.Th w={140}>主题</Table.Th>
                <Table.Th>信号 / 表达式</Table.Th>
                <Table.Th w={100}>范围</Table.Th>
                <Table.Th w={130}>推送渠道</Table.Th>
                <Table.Th w={72}>命中</Table.Th>
                <Table.Th w={92}>最近命中</Table.Th>
                <Table.Th w={78}>状态</Table.Th>
                <Table.Th w={78}>通知</Table.Th>
                <Table.Th w={70}>等级</Table.Th>
                <Table.Th w={70}>优先级</Table.Th>
                <Table.Th w={104}>操作</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rules.map((rule) => {
                const topics = ruleTopics(rule);
                const signals = ruleSignals(rule);
                return (
                  <Table.Tr key={rule.id} className="clickable-row" onClick={() => setSelectedRule(rule)}>
                    <Table.Td><Text fw={700}>{rule.name}</Text><Badge size="xs" variant="light" color={rule.match_type === "regex" ? "violet" : "gray"}>{rule.match_type === "regex" ? "正则" : rule.match_type}</Badge></Table.Td>
                    <Table.Td><Text size="sm" lineClamp={2}>{topics.join(", ") || "-"}</Text></Table.Td>
		                    <Table.Td><Text size="sm" lineClamp={2}>{signals.join(", ") || rule.patterns.join(", ")}</Text></Table.Td>
	                    <Table.Td><Text size="sm" lineClamp={1}>{rule.target_filter?.join(", ") || "全部目标"}</Text></Table.Td>
	                    <Table.Td><RuleChannelSummary rule={rule} channels={channels} /></Table.Td>
	                    <Table.Td><Text fw={800}>{formatCount(rule.hit_count || 0)}</Text></Table.Td>
                    <Table.Td><Text size="sm">{rule.recent_hit_at ? relativeTimeLabel(rule.recent_hit_at) : "-"}</Text></Table.Td>
                    <Table.Td><Switch size="sm" checked={Boolean(rule.enabled)} disabled={ruleActionId === rule.id} onChange={(event) => toggleRule(rule, event.currentTarget.checked)} /></Table.Td>
                    <Table.Td><StatusBadge value={rule.notify ? "enabled" : "disabled"} label={rule.notify ? "通知" : "只标记"} /></Table.Td>
                    <Table.Td><MatchLevel value={rule.risk_level} /></Table.Td>
                    <Table.Td>{rule.priority}</Table.Td>
                    <Table.Td>
                      <Group gap={4} wrap="nowrap">
                        <Tooltip label="查看线索"><ActionIcon variant="subtle" color="cyan" onClick={(event) => { event.stopPropagation(); openMatchesForRule(rule); }}><IconEye size={16} /></ActionIcon></Tooltip>
                        <Tooltip label="重扫历史"><ActionIcon variant="subtle" color="blue" loading={ruleActionId === rule.id} onClick={(event) => { event.stopPropagation(); setReprocessRule(rule); setReprocessForm({ limit: "5000", notify_matches: false, reset_existing: true }); }}><IconRefresh size={16} /></ActionIcon></Tooltip>
                        <Tooltip label="删除"><ActionIcon variant="subtle" color="red" loading={ruleActionId === rule.id} onClick={(event) => { event.stopPropagation(); deleteRule(rule); }}><IconTrash size={16} /></ActionIcon></Tooltip>
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        {!rules.length ? <EmptyState text="还没有监控规则。可以先从一个产品词和一个信号词开始，后续再逐步细分。" /> : null}
      </Card>

	      <Drawer opened={drawerOpened} onClose={() => { setDrawerOpened(false); resetRuleForm(); }} title={editingRuleId ? "编辑监控规则" : "新增监控规则"} position="right" size="lg">
	        <Stack gap="md">
          <Alert color={form.match_type === "regex" ? "violet" : "cyan"} icon={form.match_type === "regex" ? <IconCode size={16} /> : <IconListCheck size={16} />}>
            {form.match_type === "regex" ? "正则模式下主题词、信号词和排除词均为一行一个正则表达式，保存前会校验表达式是否合法。" : "主题词用于一级分类，信号词用于细分事件或风险；逗号或换行都可以分隔。"}
          </Alert>
          <form onSubmit={create}>
            <Stack gap="md">
              <TextInput label="规则名称" placeholder="例如：品牌负面舆情" value={form.name} onChange={(e) => setForm({ ...form, name: e.currentTarget.value })} required />
              <SimpleGrid cols={{ base: 1, sm: 2 }}>
                <Select label="匹配方式" data={[{ value: "contains", label: "包含" }, { value: "keyword", label: "独立关键词" }, { value: "regex", label: "正则表达式" }, { value: "exact", label: "精确匹配" }]} value={form.match_type} onChange={(value) => setForm({ ...form, match_type: value || "contains" })} />
                <NumberInput label="线索等级" min={0} max={5} value={form.risk_level} onChange={(value) => setForm({ ...form, risk_level: value || 0 })} />
                <NumberInput label="优先级" min={1} value={form.priority} onChange={(value) => setForm({ ...form, priority: value || 100 })} />
	                <Stack gap={6} justify="flex-end">
	                  <Checkbox label="启用规则" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.currentTarget.checked })} />
	                  <Checkbox label="命中后通知" checked={form.notify} onChange={(e) => setForm({ ...form, notify: e.currentTarget.checked })} />
	                </Stack>
	              </SimpleGrid>
	              <MultiSelect
	                label="推送渠道"
	                placeholder="不指定时使用全局启用渠道"
	                data={channels.map((channel) => ({ value: String(channel.id), label: `${channel.name} · ${channelTypeShortLabel(channel.type)} · L${channel.min_risk_level}+` }))}
	                value={(form.notification_channel_ids || []).map(String)}
	                onChange={(value) => setForm({ ...form, notification_channel_ids: value })}
	                clearable
	                searchable
	              />
              <Textarea minRows={3} label={form.match_type === "regex" ? "主题正则" : "主题词"} placeholder={form.match_type === "regex" ? "例如：watchout|telegram\\s*monitor" : "产品名、品牌名、项目名；逗号或换行分隔"} value={form.topic_terms} onChange={(e) => setForm({ ...form, topic_terms: e.currentTarget.value })} />
              <Textarea minRows={4} label={form.match_type === "regex" ? "信号正则" : "信号词"} placeholder={form.match_type === "regex" ? "例如：(泄露|出售|dump|leak)\\s*.{0,20}(账号|数据)" : "泄露、诈骗、投诉、出售、漏洞；逗号或换行分隔"} value={form.signal_terms} onChange={(e) => setForm({ ...form, signal_terms: e.currentTarget.value })} />
              <Textarea minRows={2} label={form.match_type === "regex" ? "排除正则" : "排除词"} placeholder={form.match_type === "regex" ? "一行一个排除正则" : "误报词，逗号或换行分隔"} value={form.exclude_patterns} onChange={(e) => setForm({ ...form, exclude_patterns: e.currentTarget.value })} />
              <TextInput label="目标范围" placeholder="群组名 / 链接片段，留空为全部" value={form.target_filter} onChange={(e) => setForm({ ...form, target_filter: e.currentTarget.value })} />
              <Group justify="flex-end">
                <Button variant="subtle" color="gray" onClick={() => { setDrawerOpened(false); resetRuleForm(); }}>取消</Button>
                <Button type="submit">{editingRuleId ? "保存规则" : "新增规则"}</Button>
              </Group>
            </Stack>
          </form>
	        </Stack>
	      </Drawer>
      <Drawer opened={Boolean(selectedRule)} onClose={() => setSelectedRule(null)} title="规则详情" position="right" size="lg">
        {selectedRule ? (
          <Stack gap="md">
            <Group justify="space-between" align="flex-start">
              <Box>
                <Text fw={900}>{selectedRule.name}</Text>
                <Group gap={6} mt={6}>
                  <Badge size="xs" variant="light" color={selectedRule.match_type === "regex" ? "violet" : "gray"}>{selectedRule.match_type === "regex" ? "正则" : selectedRule.match_type}</Badge>
                  <MatchLevel value={selectedRule.risk_level} />
                  <StatusBadge value={selectedRule.notify ? "enabled" : "disabled"} label={selectedRule.notify ? "通知" : "只标记"} />
                </Group>
              </Box>
              <Switch size="sm" checked={Boolean(selectedRule.enabled)} disabled={ruleActionId === selectedRule.id} onChange={(event) => toggleRule(selectedRule, event.currentTarget.checked)} />
            </Group>
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
              <InfoLine label="命中数" value={formatCount(selectedRule.hit_count || 0)} />
              <InfoLine label="最近命中" value={selectedRule.recent_hit_at ? relativeTimeLabel(selectedRule.recent_hit_at) : "-"} />
              <InfoLine label="优先级" value={String(selectedRule.priority ?? "-")} />
              <InfoLine label="目标范围" value={selectedRule.target_filter?.join(", ") || "全部目标"} />
            </SimpleGrid>
            <Paper withBorder radius="md" p="md" className="rule-detail-block">
              <Text fw={800} mb={6}>主题</Text>
              <Text size="sm" c={ruleTopics(selectedRule).length ? undefined : "dimmed"}>{ruleTopics(selectedRule).join(", ") || "-"}</Text>
            </Paper>
            <Paper withBorder radius="md" p="md" className="rule-detail-block">
              <Text fw={800} mb={6}>信号 / 表达式</Text>
              <Text size="sm" className="rule-detail-code">{(ruleSignals(selectedRule).length ? ruleSignals(selectedRule) : selectedRule.patterns || []).join("\n") || "-"}</Text>
            </Paper>
            <Paper withBorder radius="md" p="md" className="rule-detail-block">
              <Text fw={800} mb={6}>排除词</Text>
              <Text size="sm" c={selectedRule.exclude_patterns?.length ? undefined : "dimmed"}>{selectedRule.exclude_patterns?.join(", ") || "-"}</Text>
            </Paper>
            <Paper withBorder radius="md" p="md" className="rule-detail-block">
              <Text fw={800} mb={8}>推送渠道</Text>
              <RuleChannelSummary rule={selectedRule} channels={channels} />
            </Paper>
            <Group justify="flex-end">
              <Button variant="light" leftSection={<IconEye size={15} />} onClick={() => openMatchesForRule(selectedRule)}>查看线索</Button>
              <Button variant="light" leftSection={<IconRefresh size={15} />} onClick={() => { setReprocessRule(selectedRule); setReprocessForm({ limit: "5000", notify_matches: false, reset_existing: true }); }}>重扫历史</Button>
              <Button leftSection={<IconEdit size={15} />} onClick={() => { editRule(selectedRule); setSelectedRule(null); }}>编辑规则</Button>
            </Group>
          </Stack>
        ) : null}
      </Drawer>
	      <Modal opened={Boolean(reprocessRule)} onClose={() => setReprocessRule(null)} title="重扫历史消息" size="md">
        {reprocessRule ? (
          <Stack gap="md">
            <Alert color="blue" icon={<IconRefresh size={16} />}>
              将用规则「{reprocessRule.name}」重新匹配已入库消息。默认只生成线索，不推送历史命中，避免刷屏。
            </Alert>
            <Select
              label="扫描范围"
              value={reprocessForm.limit}
              onChange={(value) => setReprocessForm((current) => ({ ...current, limit: value || "5000" }))}
              data={[
                { value: "1000", label: "最近 1,000 条消息" },
                { value: "5000", label: "最近 5,000 条消息" },
                { value: "20000", label: "最近 20,000 条消息" },
                { value: "50000", label: "最近 50,000 条消息" }
              ]}
            />
            <Checkbox
              label="重扫前清空该规则旧命中"
              checked={reprocessForm.reset_existing}
              onChange={(event) => setReprocessForm((current) => ({ ...current, reset_existing: event.currentTarget.checked }))}
            />
            <Checkbox
              label="历史命中也触发推送"
              description="默认关闭。开启后会按渠道等级推送历史命中的消息。"
              checked={reprocessForm.notify_matches}
              onChange={(event) => setReprocessForm((current) => ({ ...current, notify_matches: event.currentTarget.checked }))}
            />
            <Group justify="flex-end">
              <Button variant="subtle" color="gray" onClick={() => setReprocessRule(null)}>取消</Button>
              <Button loading={ruleActionId === reprocessRule.id} onClick={reprocessSingleRule}>开始重扫</Button>
            </Group>
          </Stack>
        ) : null}
      </Modal>
    </Stack>
  );
}

function channelTypeShortLabel(type) {
  if (type === "telegram_bot") return "TG";
  if (type === "feishu") return "飞书";
  if (type === "wecom") return "企微";
  if (type === "dingtalk") return "钉钉";
  if (type === "webhook") return "Webhook";
  return type || "渠道";
}

function RuleChannelSummary({ rule, channels = [] }) {
  const ids = new Set((rule.notification_channel_ids || []).map((item) => Number(item)));
  if (!ids.size) return <Text size="sm" c="dimmed">全局渠道</Text>;
  const selected = channels.filter((channel) => ids.has(Number(channel.id)));
  if (!selected.length) return <Text size="sm" c="red">渠道已删除</Text>;
  return (
    <Group gap={4}>
      {selected.slice(0, 2).map((channel) => (
        <Badge key={channel.id} size="xs" variant="light">{channel.name}</Badge>
      ))}
      {selected.length > 2 ? <Badge size="xs" variant="light" color="gray">+{selected.length - 2}</Badge> : null}
    </Group>
  );
}

function Messages({ messages, targets, reload, filters, setFilters, total, page, setPage, defaultPageSize = "50" }) {
  const [selected, setSelected] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);
  const [translatingId, setTranslatingId] = useState(null);
  const [deletingMessages, setDeletingMessages] = useState(false);
  const targetById = useMemo(() => new Map(targets.map((target) => [String(target.id), target])), [targets]);
  const targetOptions = targets.map((target) => ({
    value: String(target.id),
    label: targetDisplayName(target)
  }));

  async function search(event) {
    event.preventDefault();
    setSelectedIds([]);
    setPage(1);
    await reload(filters, 1);
  }

  async function changePageSize(value) {
    const nextLimit = Number(value) || 50;
    const nextFilters = { ...filters, limit: nextLimit };
    setSelectedIds([]);
    setFilters(nextFilters);
    setPage(1);
    await reload(nextFilters, 1);
  }

  useEffect(() => {
    const nextLimit = Number(defaultPageSize) || 50;
    if (Number(filters.limit) === nextLimit) return;
    const nextFilters = { ...filters, limit: nextLimit };
    setSelectedIds([]);
    setFilters(nextFilters);
    setPage(1);
    reload(nextFilters, 1).catch(notifyError);
  }, [defaultPageSize]);

  function queryString(format, selectedOnly = false) {
    const params = new URLSearchParams();
    appendMessageFilters(params, filters, { includeLimit: false });
    params.set("format", format);
    params.set("limit", "5000");
    if (selectedOnly) params.set("ids", selectedIds.join(","));
    return params.toString();
  }

  async function exportMessages(format, selectedOnly = false) {
    try {
      const response = await fetch(`${API_BASE}/messages/export?${queryString(format, selectedOnly)}`, {
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

  const selectedSet = new Set(selectedIds);
  const pageIds = messages.map((message) => message.id);
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selectedSet.has(id));
  const somePageSelected = pageIds.some((id) => selectedSet.has(id));

  function togglePage(checked) {
    setSelectedIds((current) => {
      const next = new Set(current);
      pageIds.forEach((id) => {
        if (checked) next.add(id);
        else next.delete(id);
      });
      return [...next];
    });
  }

  function toggleOne(id, checked) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (checked) next.add(id);
      else next.delete(id);
      return [...next];
    });
  }

  async function changePage(nextPage) {
    setSelectedIds([]);
    setPage(nextPage);
    await reload(filters, nextPage);
  }

  async function refreshPage() {
    setSelectedIds([]);
    await reload(filters, page);
  }

  async function deleteMessages({ ids = [], targetId = null, closeDetail = false } = {}) {
    const idList = ids.length ? ids : selectedIds;
    if (!idList.length && !targetId) return;
    const scopeText = targetId
      ? `当前群组「${targetOptions.find((item) => item.value === String(targetId))?.label || targetId}」的全部消息`
      : `${idList.length} 条消息`;
    if (!window.confirm(`确认删除 ${scopeText}？相关命中记录和媒体索引也会删除。`)) return;
    setDeletingMessages(true);
    try {
      const result = idList.length === 1 && !targetId
        ? await api(`/messages/${idList[0]}`, { method: "DELETE" })
        : await api("/messages/bulk", { method: "DELETE", body: targetId ? { target_id: Number(targetId) } : { message_ids: idList } });
      notifyOk(`已删除 ${result.deleted || 0} 条消息`);
      setSelectedIds([]);
      if (closeDetail) setSelected(null);
      await reload(filters, page);
    } catch (error) {
      notifyError(error);
    } finally {
      setDeletingMessages(false);
    }
  }

  async function translateSelected() {
    if (!selected) return;
    setTranslatingId(selected.id);
    try {
      const updated = await api(`/messages/${selected.id}/translate`, { method: "POST", body: {} });
      setSelected(updated);
      if (updated.translation_status === "translated") notifyOk("翻译完成");
      else if (updated.translation_status === "failed") notifyError(new Error(updated.desc || "翻译失败，请检查翻译服务配置"));
      else notifyOk("翻译已跳过或未产生译文");
      await reload(filters, page);
    } catch (error) {
      notifyError(error);
    } finally {
      setTranslatingId(null);
    }
  }

  const pageSize = Number(filters.limit) || 50;
  const totalPages = Math.max(1, Math.ceil((total || 0) / pageSize));

  return (
    <Stack gap="sm" className="messages-view">
      <Card withBorder radius="lg" p="md" className="message-filter-card">
        <form onSubmit={search}>
          <Grid align="end" gutter="sm">
            <Grid.Col span={{ base: 12, md: 3 }}><TextInput size="sm" label="关键词" placeholder="内容 / 来源 / 发送人 / 链接 / OCR" value={filters.keyword} onChange={(e) => setFilters({ ...filters, keyword: e.currentTarget.value })} /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 2 }}><Select size="sm" label="群组" placeholder="全部群组" data={targetOptions} value={filters.target_id} onChange={(value) => setFilters({ ...filters, target_id: value || "" })} clearable searchable /></Grid.Col>
            <Grid.Col span={{ base: 6, md: 1.4 }}><Select size="sm" label="链接" placeholder="不限" data={[{ value: "true", label: "有链接" }, { value: "false", label: "无链接" }]} value={filters.has_links} onChange={(value) => setFilters({ ...filters, has_links: value || "" })} clearable /></Grid.Col>
            <Grid.Col span={{ base: 6, md: 1.4 }}><Select size="sm" label="媒体" placeholder="不限" data={[{ value: "true", label: "有媒体" }, { value: "false", label: "无媒体" }]} value={filters.has_media} onChange={(value) => setFilters({ ...filters, has_media: value || "" })} clearable /></Grid.Col>
            <Grid.Col span={{ base: 6, md: 1.4 }}><TextInput size="sm" label="开始时间" type="datetime-local" value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.currentTarget.value })} /></Grid.Col>
            <Grid.Col span={{ base: 6, md: 1.4 }}><TextInput size="sm" label="结束时间" type="datetime-local" value={filters.date_to} onChange={(e) => setFilters({ ...filters, date_to: e.currentTarget.value })} /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 1.4 }}>
              <Group justify="flex-end" gap="xs" wrap="nowrap">
                <Button size="sm" type="submit" leftSection={<IconSearch size={15} />}>搜索</Button>
                <Tooltip label="导出 CSV"><ActionIcon size="lg" variant="light" onClick={() => exportMessages("csv")}><IconDownload size={17} /></ActionIcon></Tooltip>
              </Group>
            </Grid.Col>
          </Grid>
        </form>
      </Card>

      <Card withBorder radius="lg" p={0} className="message-table-card">
        <Group justify="space-between" px="sm" py={8} className="message-table-toolbar">
          <Group gap="sm">
            <Text size="sm" c="dimmed">当前页 {messages.length} 条，已选 {selectedIds.length} 条</Text>
            <SegmentedControl
              size="xs"
              className="page-size-control"
              value={String(pageSize)}
              data={["25", "50", "100", "200"]}
              onChange={changePageSize}
            />
          </Group>
          <Group gap="xs">
            <Tooltip label="刷新当前页"><ActionIcon size="md" variant="subtle" onClick={refreshPage}><IconRefresh size={16} /></ActionIcon></Tooltip>
            <Button size="compact-xs" variant="light" disabled={!selectedIds.length} leftSection={<IconDownload size={13} />} onClick={() => exportMessages("csv", true)}>导出选中 CSV</Button>
            <Button size="compact-xs" color="red" variant="light" disabled={!selectedIds.length || deletingMessages} leftSection={<IconTrash size={13} />} onClick={() => deleteMessages({ ids: selectedIds })}>删除选中</Button>
            <Button size="compact-xs" color="red" variant="subtle" disabled={!filters.target_id || deletingMessages} leftSection={<IconTrash size={13} />} onClick={() => deleteMessages({ targetId: filters.target_id })}>删除当前群组消息</Button>
          </Group>
        </Group>
        <Table.ScrollContainer minWidth={860}>
          <Table verticalSpacing={6} horizontalSpacing="sm" striped highlightOnHover className="message-table">
            <Table.Thead>
              <Table.Tr>
                <Table.Th w={38}><Checkbox size="xs" checked={allPageSelected} indeterminate={!allPageSelected && somePageSelected} onChange={(event) => togglePage(event.currentTarget.checked)} /></Table.Th>
                <Table.Th w={118}>本地时间</Table.Th>
                <Table.Th w={180}>群组</Table.Th>
                <Table.Th w={170}>发送人</Table.Th>
                <Table.Th>内容</Table.Th>
                <Table.Th w={150}>类型</Table.Th>
                <Table.Th w={72}>操作</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {messages.map((message) => {
                return (
                  <Table.Tr key={message.id} className="message-table-row" onClick={() => setSelected(message)}>
                    <Table.Td onClick={(event) => event.stopPropagation()}>
                      <Checkbox size="xs" checked={selectedSet.has(message.id)} onChange={(event) => toggleOne(message.id, event.currentTarget.checked)} />
                    </Table.Td>
                    <Table.Td>
                      <Text size="xs" fw={700}>{formatCompactTime(message.event_time)}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" fw={800} truncate="end">{messageTargetName(message, targetById)}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" truncate="end">{firstNonEmpty(message.sender_username, message.sender_name, message.sender_id)}</Text>
                    </Table.Td>
                    <Table.Td><Text size="sm" className="message-snippet" lineClamp={2}>{messageDisplayText(message)}</Text></Table.Td>
                    <Table.Td>
                      <MessageTypeBadges message={message} />
                    </Table.Td>
                    <Table.Td onClick={(event) => event.stopPropagation()}>
                      <Tooltip label="删除这条消息">
                        <ActionIcon color="red" variant="subtle" loading={deletingMessages} onClick={() => deleteMessages({ ids: [message.id] })}>
                          <IconTrash size={15} />
                        </ActionIcon>
                      </Tooltip>
                    </Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        {!messages.length ? <EmptyState text="暂无消息。可以先配置监控目标并执行回填。" /> : null}
        <Group justify="space-between" px="sm" py="sm">
          <Text size="sm" c="dimmed">共 {total || 0} 条，每页 {pageSize} 条</Text>
          <Pagination size="sm" total={totalPages} value={page} onChange={changePage} siblings={1} boundaries={1} />
        </Group>
      </Card>

      <Modal opened={Boolean(selected)} onClose={() => setSelected(null)} title="消息详情" size="lg" classNames={{ content: "message-detail-modal" }}>
        {selected ? (
          <Stack gap="sm" className="message-detail">
            <Group justify="space-between" align="flex-start" gap="md">
              <Stack gap={2}>
                <Text fw={800}>{messageTargetName(selected, targetById)}</Text>
                <Text size="sm" c="dimmed">{firstNonEmpty(selected.sender_username, selected.sender_name, "未知发送人")} · {formatTime(selected.event_time)}</Text>
              </Stack>
              <MessageTypeBadges message={selected} size="sm" />
            </Group>
            <Paper withBorder p="md" radius="md" className="message-body-panel">
              <Group justify="space-between" mb="xs">
                <Text size="sm" fw={700}>原文 {selected.language ? `(${selected.language})` : ""}</Text>
                <Button size="compact-xs" variant="light" loading={translatingId === selected.id} onClick={translateSelected}>翻译</Button>
              </Group>
              <Text className="message-content">{messageDisplayText(selected)}</Text>
            </Paper>
            {selected.translated_content ? (
              <Paper withBorder p="md" radius="md" className="message-body-panel">
                <Text size="sm" fw={700} mb="xs">译文 ({selected.language || "auto"} {"->"} {selected.translation_target || "目标语言"})</Text>
                <Text className="message-content">{selected.translated_content}</Text>
                <Text size="xs" c="dimmed" mt="xs">{selected.translation_engine || "translation"} · {selected.translation_status}</Text>
              </Paper>
            ) : selected.translation_status && selected.translation_status !== "pending" ? (
              <Alert color={selected.translation_status === "failed" ? "red" : "gray"} icon={<IconMessageSearch size={16} />}>
                翻译状态：{selected.translation_status}{selected.desc ? ` · ${selected.desc}` : ""}
              </Alert>
            ) : null}
            {selected.ocr_text ? (
              <Paper withBorder p="md" radius="md" className="message-body-panel">
                <Text size="sm" fw={700} mb="xs">图片 OCR</Text>
                <Text className="message-content">{selected.ocr_text}</Text>
              </Paper>
            ) : null}
            {(selected.media_items?.length || selected.media_count > 0) ? (
              <Paper withBorder p="md" radius="md" className="message-body-panel">
                <Group justify="space-between" mb="xs">
                  <Text size="sm" fw={700}>媒体归档</Text>
                  <Badge variant="light">{selected.media_count || selected.media_items?.length || 0} 个媒体</Badge>
                </Group>
                <Stack gap="xs">
                  {(selected.media_items?.length ? selected.media_items : [{
                    id: "fallback",
                    media_kind: selected.message_kind,
                    file_name: selected.media_name || selected.raw_name || "",
                    mime_type: selected.media_type || "",
                    size: 0,
                    download_status: "metadata_only",
                    ocr_status: selected.ocr_status,
                    ocr_engine: selected.ocr_engine,
                    ocr_text: selected.ocr_text,
                    error: ""
                  }]).map((item) => (
                    <Paper key={item.id} withBorder radius="md" p="sm" className="dashboard-metric">
                      <Group justify="space-between" align="flex-start" gap="md">
                        <Stack gap={2} className="grow">
                          <Text size="sm" fw={700} lineClamp={1}>{item.file_name || item.media_kind || item.mime_type || "媒体文件"}</Text>
                          <Text size="xs" c="dimmed">{item.media_kind || "-"} · {item.mime_type || "-"} · {formatBytes(item.size)}</Text>
                          {item.ocr_text ? <Text size="xs" c="dimmed" lineClamp={2}>OCR：{item.ocr_text}</Text> : null}
                          {item.error ? <Text size="xs" c="red" lineClamp={2}>{item.error}</Text> : null}
                        </Stack>
                        <Stack gap={3} align="flex-end">
                          <StatusBadge value={item.download_status || "metadata_only"} />
                          <StatusBadge value={item.ocr_status || "pending"} label={`OCR ${statusLabel(item.ocr_status || "pending")}`} />
                        </Stack>
                      </Group>
                    </Paper>
                  ))}
                </Stack>
              </Paper>
            ) : null}
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs" className="message-detail-meta">
              <InfoLine label="浏览 / 回复 / 转发" value={`${selected.views_count || 0} / ${selected.replies_count || 0} / ${selected.forwards_count || 0}`} />
              <InfoLine label="消息 ID" value={selected.message_id || "-"} />
            </SimpleGrid>
            <Group justify="flex-end" className="message-detail-actions" gap="xs">
              <Button color="red" size="xs" variant="light" loading={deletingMessages} leftSection={<IconTrash size={14} />} onClick={() => deleteMessages({ ids: [selected.id], closeDetail: true })}>删除消息</Button>
              {messageUrl(selected) ? <Button component="a" href={messageUrl(selected)} target="_blank" rel="noreferrer" size="xs" variant="light" leftSection={<IconExternalLink size={14} />}>打开原消息</Button> : null}
            </Group>
            {extractedLinks(selected).length ? (
              <Stack gap={6} className="message-links-panel">
                <Text size="sm" fw={700}>正文链接</Text>
                {extractedLinks(selected).map((link) => <Anchor key={link} href={link} target="_blank">{link}</Anchor>)}
              </Stack>
            ) : null}
          </Stack>
        ) : null}
      </Modal>
    </Stack>
  );
}

function Matches({ hits, initialRuleId = "", rules = [], reload, defaultPageSize = "50" }) {
  const [rows, setRows] = useState(hits);
  const [total, setTotal] = useState(hits.length);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(defaultPageSize);
  const [filters, setFilters] = useState({
    keyword: "",
    status: "all",
    rule_id: initialRuleId,
    min_risk_level: ""
  });
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(false);
  const [hitAction, setHitAction] = useState("");
  const [deliveries, setDeliveries] = useState([]);
  const [deliveryLoading, setDeliveryLoading] = useState(false);
  const ruleOptions = useMemo(() => {
    const seen = new Map();
    rules.forEach((rule) => {
      if (rule.id) seen.set(String(rule.id), rule.name || `规则 #${rule.id}`);
    });
    rows.concat(hits).forEach((hit) => {
      if (hit.rule_id && !seen.has(String(hit.rule_id))) seen.set(String(hit.rule_id), hit.rule_name || `规则 #${hit.rule_id}`);
    });
    return [...seen.entries()].map(([value, label]) => ({ value, label }));
  }, [rows, hits, rules]);

  useEffect(() => {
    if (initialRuleId && filters.rule_id !== initialRuleId) {
      setFilters((current) => ({ ...current, rule_id: initialRuleId }));
    }
  }, [initialRuleId]);

  function hitQuery(nextPage = page, nextPageSize = pageSize) {
    const params = new URLSearchParams();
    const limit = Number(nextPageSize) || 25;
    params.set("limit", String(limit));
    params.set("offset", String(Math.max(0, nextPage - 1) * limit));
    if (filters.keyword) params.set("keyword", filters.keyword);
    if (filters.status !== "all") params.set("status", filters.status);
    if (filters.rule_id) params.set("rule_id", filters.rule_id);
    if (filters.min_risk_level) params.set("min_risk_level", filters.min_risk_level);
    return params.toString();
  }

  function hitCountQuery() {
    const params = new URLSearchParams();
    if (filters.keyword) params.set("keyword", filters.keyword);
    if (filters.status !== "all") params.set("status", filters.status);
    if (filters.rule_id) params.set("rule_id", filters.rule_id);
    if (filters.min_risk_level) params.set("min_risk_level", filters.min_risk_level);
    return params.toString();
  }

  async function loadHits(nextPage = page, nextPageSize = pageSize) {
    setLoading(true);
    try {
      const [nextRows, count] = await Promise.all([
        api(`/hits?${hitQuery(nextPage, nextPageSize)}`),
        api(`/hits/count?${hitCountQuery()}`)
      ]);
      setRows(nextRows);
      setTotal(count.total || 0);
    } catch (error) {
      notifyError(error);
    } finally {
      setLoading(false);
    }
  }

  async function loadDeliveries(messageId) {
    if (!messageId) {
      setDeliveries([]);
      return;
    }
    setDeliveryLoading(true);
    try {
      const result = await api(`/notifications/deliveries?message_id=${messageId}&page_size=20`);
      setDeliveries(Array.isArray(result) ? result : (result.items || []));
    } catch (error) {
      notifyError(error);
    } finally {
      setDeliveryLoading(false);
    }
  }

  useEffect(() => {
    loadHits(1, pageSize);
    setPage(1);
  }, [filters.status, filters.rule_id, filters.min_risk_level]);

  useEffect(() => {
    setPageSize(defaultPageSize);
    setPage(1);
    loadHits(1, defaultPageSize);
  }, [defaultPageSize]);

  useEffect(() => {
    if (page !== 1 || filters.keyword || filters.status !== "all" || filters.rule_id || filters.min_risk_level) return;
    setRows(hits);
    setTotal((current) => Math.max(current, hits.length));
  }, [hits, page, filters]);

  async function search(event) {
    event.preventDefault();
    setPage(1);
    await loadHits(1);
  }

  async function changePage(nextPage) {
    setPage(nextPage);
    await loadHits(nextPage);
  }

  async function changePageSize(value) {
    const nextPageSize = value || "25";
    setPageSize(nextPageSize);
    setPage(1);
    await loadHits(1, nextPageSize);
  }

  function replaceHit(updated) {
    setRows((current) => current.map((hit) => (hit.id === updated.id ? updated : hit)));
    setSelected((current) => (current?.id === updated.id ? updated : current));
  }

  function openHitDetail(hit) {
    setSelected(hit);
    loadDeliveries(hit.message_id);
  }

  async function updateHitStatus(status, message) {
    if (!selected) return;
    setHitAction(status);
    try {
      const updated = await api(`/hits/${selected.id}`, { method: "PATCH", body: { status } });
      replaceHit(updated);
      notifyOk(message);
    } catch (error) {
      notifyError(error);
    } finally {
      setHitAction("");
    }
  }

  async function notifySelectedHit() {
    if (!selected) return;
    setHitAction("notify");
    try {
      const updated = await api(`/hits/${selected.id}/notify`, { method: "POST" });
      replaceHit(updated);
      await loadDeliveries(updated.message_id);
      notifyOk("线索已重新推送");
    } catch (error) {
      notifyError(error);
    } finally {
      setHitAction("");
    }
  }

  async function addSelectedPatternToExclude() {
    if (!selected?.rule_id) return;
    const pattern = selected.matched_patterns?.[0] || "";
    if (!pattern) {
      notifyError(new Error("当前线索没有可加入排除词的命中词"));
      return;
    }
    if (!window.confirm(`将「${pattern}」加入规则「${selected.rule_name}」的排除词吗？`)) return;
    setHitAction("exclude");
    try {
      await api(`/rules/${selected.rule_id}/exclude`, { method: "POST", body: { pattern } });
      const updated = await api(`/hits/${selected.id}`, { method: "PATCH", body: { status: "ignored" } });
      replaceHit(updated);
      notifyOk("已加入排除词，并将该线索标记为已忽略");
      if (reload) await reload();
    } catch (error) {
      notifyError(error);
    } finally {
      setHitAction("");
    }
  }

  const pageLimit = Number(pageSize) || 25;
  const totalPages = Math.max(1, Math.ceil((total || 0) / pageLimit));

  return (
    <Stack>
      <SimpleGrid cols={{ base: 1, md: 3 }}>
        <KpiCard icon={IconCircleCheck} label="命中线索" value={total || rows.length} sub="规则命中的消息记录" />
        <KpiCard icon={IconAlertTriangle} label="当前页待处理" value={rows.filter((hit) => hit.status === "open").length} sub="需要人工确认" color="orange" />
        <KpiCard icon={IconBell} label="当前页高等级" value={rows.filter((hit) => Number(hit.risk_level) >= 2).length} sub="建议进入通知策略" color="red" />
      </SimpleGrid>
      <Card withBorder radius="lg" p="md">
        <form onSubmit={search}>
          <Grid align="end" gutter="sm">
            <Grid.Col span={{ base: 12, md: 4 }}><TextInput size="sm" label="关键词" placeholder="规则 / 命中词 / 消息 / 来源" value={filters.keyword} onChange={(event) => setFilters({ ...filters, keyword: event.currentTarget.value })} /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 2.5 }}><Select size="sm" label="规则" placeholder="全部规则" data={ruleOptions} value={filters.rule_id} onChange={(value) => setFilters({ ...filters, rule_id: value || "" })} clearable searchable /></Grid.Col>
            <Grid.Col span={{ base: 6, md: 1.8 }}><Select size="sm" label="状态" data={[{ value: "all", label: "全部" }, { value: "open", label: "待处理" }, { value: "confirmed", label: "已确认" }, { value: "ignored", label: "已忽略" }, { value: "archived", label: "已归档" }, { value: "notified", label: "已通知" }, { value: "muted", label: "只标记" }]} value={filters.status} onChange={(value) => setFilters({ ...filters, status: value || "all" })} /></Grid.Col>
            <Grid.Col span={{ base: 6, md: 1.7 }}><Select size="sm" label="最低等级" placeholder="不限" data={["1", "2", "3", "4", "5"].map((value) => ({ value, label: `L${value}+` }))} value={filters.min_risk_level} onChange={(value) => setFilters({ ...filters, min_risk_level: value || "" })} clearable /></Grid.Col>
            <Grid.Col span={{ base: 12, md: 2 }}><Button size="sm" type="submit" loading={loading} fullWidth leftSection={<IconSearch size={15} />}>搜索</Button></Grid.Col>
          </Grid>
        </form>
      </Card>
      <Card withBorder radius="lg" p={0}>
        <Group justify="space-between" px="sm" py={8}>
          <Text size="sm" c="dimmed">当前页 {rows.length} 条</Text>
          <Group gap="xs">
            <SegmentedControl size="xs" value={String(pageSize)} data={["25", "50", "100", "200"]} onChange={changePageSize} />
            <Tooltip label="刷新当前页"><ActionIcon size="md" variant="subtle" loading={loading} onClick={() => loadHits()}><IconRefresh size={16} /></ActionIcon></Tooltip>
          </Group>
        </Group>
        <Table.ScrollContainer minWidth={1180}>
          <Table verticalSpacing="sm" horizontalSpacing="sm" striped highlightOnHover className="matches-table">
            <colgroup>
              <col style={{ width: "170px" }} />
              <col />
              <col style={{ width: "150px" }} />
              <col style={{ width: "190px" }} />
              <col style={{ width: "72px" }} />
              <col style={{ width: "90px" }} />
              <col style={{ width: "130px" }} />
            </colgroup>
            <Table.Thead>
              <Table.Tr><Table.Th>线索规则</Table.Th><Table.Th>消息摘要</Table.Th><Table.Th>命中信号</Table.Th><Table.Th>来源</Table.Th><Table.Th>等级</Table.Th><Table.Th>状态</Table.Th><Table.Th>命中时间</Table.Th></Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((hit) => (
                <Table.Tr key={hit.id} className="message-table-row" onClick={() => openHitDetail(hit)}>
                  <Table.Td className="matches-rule-cell"><Text fw={700} size="sm" lineClamp={2}>{hit.rule_name}</Text><Text size="xs" c="dimmed">规则 #{hit.rule_id || "-"}</Text></Table.Td>
                  <Table.Td><Text size="sm" lineClamp={2} className="matches-summary">{messageDisplayText(hit.message) || `消息 #${hit.message_id}`}</Text></Table.Td>
                  <Table.Td><Group gap={4} className="matches-badge-group">{hit.matched_patterns.slice(0, 4).map((item) => <Badge key={item} variant="light">{item}</Badge>)}</Group></Table.Td>
                  <Table.Td className="matches-source-cell"><Text size="sm" lineClamp={1}>{hit.message ? messageTargetName(hit.message, new Map()) : "-"}</Text></Table.Td>
                  <Table.Td className="matches-compact-cell"><MatchLevel value={hit.risk_level} /></Table.Td>
                  <Table.Td className="matches-compact-cell"><StatusBadge value={hit.status} /></Table.Td>
                  <Table.Td className="matches-time-cell"><Text size="sm">{formatTime(hit.created_at)}</Text></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        {!rows.length ? <EmptyState text="暂无命中线索。可以先启用监控规则，然后执行采集或回填。" /> : null}
        <Group justify="space-between" px="sm" py="sm">
          <Text size="sm" c="dimmed">共 {total || 0} 条，每页 {pageLimit} 条</Text>
          <Pagination size="sm" total={totalPages} value={page} onChange={changePage} siblings={1} boundaries={1} />
        </Group>
      </Card>

      <Drawer opened={Boolean(selected)} onClose={() => setSelected(null)} title="线索详情" position="right" size="lg">
        {selected ? (
          <Stack gap="md">
            <Paper withBorder p="md" radius="md">
              <Group justify="space-between" align="flex-start">
                <Stack gap={4}>
                  <Title order={4}>{selected.rule_name}</Title>
                  <Group gap={6}>{selected.matched_patterns.map((item) => <Badge key={item} variant="light">{item}</Badge>)}</Group>
                </Stack>
                <MatchLevel value={selected.risk_level} />
              </Group>
              <SimpleGrid cols={{ base: 1, sm: 2 }} mt="md" spacing="xs">
                <InfoLine label="处理状态" value={statusLabel(selected.status)} />
                <InfoLine label="命中时间" value={formatTime(selected.created_at)} />
              </SimpleGrid>
              <Group mt="md" gap="xs">
                <Button size="xs" color="teal" variant="light" loading={hitAction === "confirmed"} onClick={() => updateHitStatus("confirmed", "线索已确认")}>确认线索</Button>
                <Button size="xs" color="gray" variant="light" loading={hitAction === "ignored"} onClick={() => updateHitStatus("ignored", "线索已忽略")}>忽略</Button>
                <Button size="xs" color="gray" variant="subtle" loading={hitAction === "archived"} onClick={() => updateHitStatus("archived", "线索已归档")}>归档</Button>
                <Button size="xs" color="blue" variant="light" loading={hitAction === "notify"} onClick={notifySelectedHit}>重新推送</Button>
              </Group>
            </Paper>
            {selected.message ? (
              <>
                <Paper withBorder p="md" radius="md" className="message-body-panel">
                  <Group justify="space-between" mb="xs">
                    <Text size="sm" fw={700}>原始消息</Text>
                    <MessageTypeBadges message={selected.message} size="sm" />
                  </Group>
                  <Text className="message-content">{messageDisplayText(selected.message)}</Text>
                </Paper>
                {selected.message.translated_content ? (
                  <Paper withBorder p="md" radius="md" className="message-body-panel">
                    <Text size="sm" fw={700} mb="xs">译文 ({selected.message.language || "auto"} {"->"} {selected.message.translation_target || "目标语言"})</Text>
                    <Text className="message-content">{selected.message.translated_content}</Text>
                  </Paper>
                ) : null}
                {selected.message.ocr_text ? (
                  <Paper withBorder p="md" radius="md" className="message-body-panel">
                    <Text size="sm" fw={700} mb="xs">图片 OCR</Text>
                    <Text className="message-content">{selected.message.ocr_text}</Text>
                  </Paper>
                ) : null}
                <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs">
                  <InfoLine label="来源" value={messageTargetName(selected.message, new Map())} />
                  <InfoLine label="发送人" value={firstNonEmpty(selected.message.sender_username, selected.message.sender_name, selected.message.sender_id)} />
                  <InfoLine label="消息时间" value={formatTime(selected.message.event_time)} />
                  <InfoLine label="浏览 / 回复 / 转发" value={`${selected.message.views_count || 0} / ${selected.message.replies_count || 0} / ${selected.message.forwards_count || 0}`} />
                </SimpleGrid>
                <Group justify="flex-end">
                  <Button size="xs" variant="subtle" color="red" loading={hitAction === "exclude"} onClick={addSelectedPatternToExclude}>加入排除词</Button>
                  {messageUrl(selected.message) ? <Button component="a" href={messageUrl(selected.message)} target="_blank" rel="noreferrer" size="xs" variant="light" leftSection={<IconExternalLink size={14} />}>打开原消息</Button> : null}
                </Group>
                <Paper withBorder p="md" radius="md">
                  <Group justify="space-between" mb="sm">
                    <Text size="sm" fw={800}>通知投递历史</Text>
                    <Button size="compact-xs" variant="subtle" loading={deliveryLoading} onClick={() => loadDeliveries(selected.message_id)}>刷新</Button>
                  </Group>
                  <Stack gap="xs">
                    {deliveries.map((delivery) => (
                      <Paper key={delivery.id} withBorder radius="md" p="sm" className="dashboard-metric">
                        <Group justify="space-between" align="flex-start" gap="md">
                          <Stack gap={2}>
                            <Text size="sm" fw={700}>{delivery.channel_name || `渠道 #${delivery.channel_id || "-"}`}</Text>
                            <Text size="xs" c="dimmed">{delivery.channel_type || "unknown"} · {formatTime(delivery.created_at)}</Text>
                            {delivery.error ? <Text size="xs" c="red" lineClamp={2}>{delivery.error}</Text> : null}
                          </Stack>
                          <Stack gap={2} align="flex-end">
                            <StatusBadge value={delivery.status} />
                            <Text size="xs" c="dimmed">尝试 {delivery.attempts || 0}</Text>
                          </Stack>
                        </Group>
                      </Paper>
                    ))}
                    {!deliveries.length ? <Text size="sm" c="dimmed">{deliveryLoading ? "正在加载投递记录..." : "暂无通知投递记录。"}</Text> : null}
                  </Stack>
                </Paper>
              </>
            ) : (
              <Alert color="gray">关联消息不存在或已被清理。</Alert>
            )}
          </Stack>
        ) : null}
      </Drawer>
    </Stack>
  );
}

function NotificationsPanel({ channels, reload }) {
  const defaultTelegramProxy = "";
  const emptyForm = { name: "", type: "telegram_bot", bot_token: "", chat_ids: "", proxy_url: defaultTelegramProxy, url: "", min_risk_level: 1, enabled: true };
  const [form, setForm] = useState(emptyForm);
  const [drawerOpened, setDrawerOpened] = useState(false);
  const [editingChannelId, setEditingChannelId] = useState(null);
  const [channelActionId, setChannelActionId] = useState(null);
  const [deliveryRows, setDeliveryRows] = useState([]);
  const [deliveryTotal, setDeliveryTotal] = useState(0);
  const [deliveryPage, setDeliveryPage] = useState(1);
  const [deliveryPageSize, setDeliveryPageSize] = useState("25");
  const [deliverySort, setDeliverySort] = useState({ key: "created_at", direction: "desc" });
  const [selectedDelivery, setSelectedDelivery] = useState(null);
  const [deliveryLoading, setDeliveryLoading] = useState(false);
  const [deliveryFilters, setDeliveryFilters] = useState({ channel_id: "", status: "all" });
  const [rulesExpanded, setRulesExpanded] = useState(false);
  const [deliveriesExpanded, setDeliveriesExpanded] = useState(true);
  const [expandedChannels, setExpandedChannels] = useState({});
  const notificationTypes = [
    { value: "telegram_bot", label: "Telegram Bot" },
    { value: "feishu", label: "飞书机器人" },
    { value: "wecom", label: "企业微信" },
    { value: "dingtalk", label: "钉钉" },
    { value: "webhook", label: "Webhook" },
    { value: "email", label: "Email" },
    { value: "slack", label: "Slack" },
    { value: "discord", label: "Discord" },
    { value: "ntfy", label: "ntfy" }
  ];
  const channelOptions = channels.map((channel) => ({ value: String(channel.id), label: channel.name }));
  const enabledChannels = channels.filter((channel) => channel.enabled);
  const totalDeliveries = channels.reduce((total, channel) => total + (Number(channel.delivery_count) || 0), 0);
  const totalDelivered = channels.reduce((total, channel) => total + (Number(channel.delivered_count) || 0), 0);
  const totalFailed = channels.reduce((total, channel) => total + (Number(channel.failed_count) || 0), 0);
  const successRate = totalDeliveries ? Math.round((totalDelivered / totalDeliveries) * 100) : 0;

  function channelTypeLabel(type) {
    return notificationTypes.find((item) => item.value === type)?.label || type;
  }

  function maskedUrl(value = "") {
    const text = String(value || "");
    if (!text) return "未配置";
    if (text.length <= 34) return text;
    return `${text.slice(0, 22)}...${text.slice(-10)}`;
  }

  function channelEndpoint(channel) {
    const config = channel.config || {};
    if (channel.type === "telegram_bot") {
      const chats = Array.isArray(config.chat_ids) ? config.chat_ids : [];
      return chats.length ? chats.join(", ") : "未配置 Chat ID";
    }
    if (channel.type === "dingtalk") {
      return config.access_token ? "已配置 access_token" : (config.webhook_url || config.url || "");
    }
    return config.webhook_url || config.url || "";
  }

  function toggleChannelExpand(id) {
    setExpandedChannels((current) => ({ ...current, [id]: !current[id] }));
  }

  function buildChannelPayload(source) {
    const config = source.type === "telegram_bot"
      ? { bot_token: source.bot_token, chat_ids: source.chat_ids.split(",").map((item) => item.trim()).filter(Boolean), proxy_url: source.proxy_url || "" }
      : source.type === "feishu" || source.type === "wecom"
        ? { webhook_url: source.url }
        : source.type === "dingtalk"
          ? { webhook_url: source.url, access_token: source.access_token || "", secret: source.secret || "" }
          : { url: source.url };
    return {
      name: source.name,
      type: source.type,
      enabled: Boolean(source.enabled),
      min_risk_level: Number(source.min_risk_level),
      config
    };
  }

  function resetChannelForm() {
    setForm(emptyForm);
    setEditingChannelId(null);
  }

  function openChannelDrawer(channel = null) {
    if (channel) {
      const config = channel.config || {};
      setEditingChannelId(channel.id);
      setForm({
        name: channel.name || "",
	        type: channel.type || "telegram_bot",
	        bot_token: config.bot_token || "",
	        chat_ids: Array.isArray(config.chat_ids) ? config.chat_ids.join(",") : "",
	        proxy_url: config.proxy_url || (channel.type === "telegram_bot" ? defaultTelegramProxy : ""),
	        url: config.webhook_url || config.url || "",
	        access_token: config.access_token || "",
	        secret: config.secret || config.sign || config.secret_key || "",
        min_risk_level: channel.min_risk_level ?? 1,
        enabled: Boolean(channel.enabled)
      });
    } else {
      resetChannelForm();
    }
    setDrawerOpened(true);
  }

  async function saveChannel(event) {
    event.preventDefault();
    try {
      await api(editingChannelId ? `/notifications/${editingChannelId}` : "/notifications", {
        method: editingChannelId ? "PATCH" : "POST",
        body: buildChannelPayload(form)
      });
      resetChannelForm();
      setDrawerOpened(false);
      notifyOk(editingChannelId ? "通知渠道已保存" : "通知渠道已新增");
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

  function deliveryQuery(filters = deliveryFilters, nextPage = deliveryPage, nextPageSize = deliveryPageSize, nextSort = deliverySort) {
    const params = new URLSearchParams();
    params.set("page", String(nextPage));
    params.set("page_size", String(nextPageSize));
    params.set("sort", nextSort.key);
    params.set("direction", nextSort.direction);
    if (filters.channel_id) params.set("channel_id", filters.channel_id);
    if (filters.status !== "all") params.set("status", filters.status);
    return params.toString();
  }

  async function loadDeliveryRows(filters = deliveryFilters, nextPage = deliveryPage, nextPageSize = deliveryPageSize, nextSort = deliverySort) {
    setDeliveryLoading(true);
    try {
      const result = await api(`/notifications/deliveries?${deliveryQuery(filters, nextPage, nextPageSize, nextSort)}`);
      const items = Array.isArray(result) ? result : (result.items || []);
      setDeliveryRows(items);
      setDeliveryTotal(Array.isArray(result) ? items.length : (result.total || 0));
      setDeliveryPage(Array.isArray(result) ? 1 : (result.page || nextPage));
      setDeliveryPageSize(String(Array.isArray(result) ? nextPageSize : (result.page_size || nextPageSize)));
    } catch (error) {
      notifyError(error);
    } finally {
      setDeliveryLoading(false);
    }
  }

  useEffect(() => {
    loadDeliveryRows();
  }, []);

  async function changeDeliveryFilter(nextFilters) {
    setDeliveryFilters(nextFilters);
    await loadDeliveryRows(nextFilters, 1);
  }

  function changeDeliveryPage(nextPage) {
    loadDeliveryRows(deliveryFilters, nextPage);
  }

  function changeDeliveryPageSize(nextPageSize) {
    setDeliveryPageSize(String(nextPageSize));
    loadDeliveryRows(deliveryFilters, 1, String(nextPageSize));
  }

  function setDeliverySortKey(key) {
    const nextSort = deliverySort.key === key
      ? { key, direction: deliverySort.direction === "asc" ? "desc" : "asc" }
      : { key, direction: "desc" };
    setDeliverySort(nextSort);
    loadDeliveryRows(deliveryFilters, 1, deliveryPageSize, nextSort);
  }

  function DeliverySortHeader({ label, sortKey, width }) {
    const active = deliverySort.key === sortKey;
    return (
      <Table.Th w={width}>
        <UnstyledButton className={`target-sort-header ${active ? "active" : ""}`} onClick={() => setDeliverySortKey(sortKey)}>
          <span>{label}</span>
          <span className="target-sort-indicator">{active ? (deliverySort.direction === "asc" ? "↑" : "↓") : "↕"}</span>
        </UnstyledButton>
      </Table.Th>
    );
  }

  async function retryFailedDeliveries() {
    setDeliveryLoading(true);
    try {
      const result = await api("/notifications/retry-failed", { method: "POST" });
      notifyOk(`失败投递已重试：${result.delivered || 0}/${result.retried || 0} 成功`);
      await Promise.all([loadDeliveryRows(deliveryFilters, deliveryPage), reload()]);
    } catch (error) {
      notifyError(error);
    } finally {
      setDeliveryLoading(false);
    }
  }

  async function toggleChannel(channel, enabled) {
    setChannelActionId(channel.id);
    try {
      await api(`/notifications/${channel.id}`, {
        method: "PATCH",
        body: { ...channel, enabled, config: channel.config || {} }
      });
      notifyOk(enabled ? "通知渠道已启用" : "通知渠道已停用");
      await reload();
    } catch (error) {
      notifyError(error);
    } finally {
      setChannelActionId(null);
    }
  }

  async function deleteChannel(channel) {
    if (!window.confirm(`确定删除通知渠道「${channel.name}」吗？历史投递记录会保留。`)) return;
    setChannelActionId(channel.id);
    try {
      await api(`/notifications/${channel.id}`, { method: "DELETE" });
      notifyOk("通知渠道已删除");
      await reload();
    } catch (error) {
      notifyError(error);
    } finally {
      setChannelActionId(null);
    }
  }

  return (
    <Stack className="notifications-view" gap="md">
      <SimpleGrid cols={{ base: 1, sm: 2, xl: 4 }}>
        <KpiCard icon={IconBell} label="启用渠道" value={`${enabledChannels.length}/${channels.length}`} sub="当前参与推送" color="blue" />
        <KpiCard icon={IconSend} label="总投递" value={formatCount(totalDeliveries)} sub="历史投递记录" color="cyan" />
        <KpiCard icon={IconCircleCheck} label="成功率" value={`${successRate}%`} sub={`成功 ${formatCount(totalDelivered)}`} color="teal" />
        <KpiCard icon={IconAlertTriangle} label="失败待查" value={formatCount(totalFailed)} sub="可在投递表重试" color="red" />
      </SimpleGrid>

      <Card withBorder radius="lg" p="lg" className="push-management-card">
        <Group justify="space-between" align="flex-start" mb="md">
          <Stack gap={2}>
            <Title order={3}>推送渠道</Title>
            <Text c="dimmed" size="sm">管理飞书、Telegram Bot、Webhook 等推送渠道，配置触发等级、投递策略和失败重试。</Text>
          </Stack>
          <Button leftSection={<IconBell size={16} />} onClick={() => openChannelDrawer()}>新增渠道</Button>
        </Group>

        <Paper withBorder radius="md" p="md" className="push-rule-panel">
          <Group justify="space-between" align="center">
            <Group gap="sm">
              <ThemeIcon variant="light" color="blue" radius="md"><IconBell size={17} /></ThemeIcon>
              <Box>
                <Text fw={800}>推送等级说明</Text>
                <Text size="sm" c="dimmed">选择 L2 时，会接收 L2、L3、L4、L5 线索。</Text>
              </Box>
            </Group>
            <Button size="xs" variant="subtle" onClick={() => setRulesExpanded((value) => !value)}>{rulesExpanded ? "收起" : "展开"}</Button>
          </Group>
          {rulesExpanded ? (
            <SimpleGrid cols={{ base: 1, md: 3 }} mt="md">
              <Paper withBorder radius="md" p="sm" className="push-rule-item"><MatchLevel value={1} /><Text size="sm" mt={6}>低风险或普通命中，适合入库、低频摘要或测试渠道。</Text></Paper>
              <Paper withBorder radius="md" p="sm" className="push-rule-item"><MatchLevel value={2} /><Text size="sm" mt={6}>中等线索，适合飞书业务群、运营群和值班群。</Text></Paper>
              <Paper withBorder radius="md" p="sm" className="push-rule-item"><MatchLevel value={3} /><Text size="sm" mt={6}>高优先级线索，适合即时推送给负责人或多人渠道。</Text></Paper>
            </SimpleGrid>
          ) : null}
        </Paper>

	        <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="sm" mt="md">
	          {channels.map((channel) => {
            const expanded = Boolean(expandedChannels[channel.id]);
            const endpoint = channelEndpoint(channel);
            return (
	              <Paper key={channel.id} withBorder radius="md" p="sm" className="push-channel-card compact">
	                <Group justify="space-between" align="flex-start" gap="sm" wrap="nowrap">
	                  <Group gap="sm" align="flex-start" wrap="nowrap">
	                    <ActionIcon size="sm" variant="light" color="cyan" onClick={() => toggleChannelExpand(channel.id)} aria-label={expanded ? "收起渠道" : "展开渠道"}>
	                      {expanded ? <IconChevronLeft size={16} /> : <IconChevronRight size={16} />}
	                    </ActionIcon>
	                    <Box miw={0}>
	                      <Group gap="xs" mb={4}>
	                        <Text fw={900} truncate="end">{channel.name}</Text>
	                        <Badge size="xs" variant="light">{channelTypeLabel(channel.type)}</Badge>
	                        <MatchLevel value={channel.min_risk_level} />
	                      </Group>
	                      <Text size="xs" c="dimmed">#{channel.id} · L{channel.min_risk_level}+</Text>
	                    </Box>
	                  </Group>
	                  <Group gap="xs" wrap="nowrap">
	                    {channel.last_delivery_status ? <StatusBadge value={channel.last_delivery_status} /> : <Badge variant="light" color="gray">暂无投递</Badge>}
	                    <Switch size="sm" checked={Boolean(channel.enabled)} disabled={channelActionId === channel.id} onChange={(event) => toggleChannel(channel, event.currentTarget.checked)} />
	                    <Tooltip label="测试"><ActionIcon size="sm" variant="subtle" color="cyan" onClick={() => testChannel(channel.id)}><IconSend size={16} /></ActionIcon></Tooltip>
	                    <Tooltip label="编辑"><ActionIcon size="sm" variant="subtle" onClick={() => openChannelDrawer(channel)}><IconEdit size={16} /></ActionIcon></Tooltip>
	                    <Tooltip label="删除"><ActionIcon size="sm" variant="subtle" color="red" loading={channelActionId === channel.id} onClick={() => deleteChannel(channel)}><IconTrash size={16} /></ActionIcon></Tooltip>
	                  </Group>
	                </Group>
	                <SimpleGrid cols={4} spacing={6} mt="sm">
	                  <Paper radius="md" px="xs" py={6} className="push-channel-metric"><Text size="xs" c="dimmed">投递</Text><Text fw={900} size="sm">{formatCount(channel.delivery_count || 0)}</Text></Paper>
	                  <Paper radius="md" px="xs" py={6} className="push-channel-metric"><Text size="xs" c="dimmed">成功</Text><Text fw={900} size="sm">{formatCount(channel.delivered_count || 0)}</Text></Paper>
	                  <Paper radius="md" px="xs" py={6} className="push-channel-metric"><Text size="xs" c="dimmed">失败</Text><Text fw={900} size="sm" c={(channel.failed_count || 0) ? "red" : undefined}>{formatCount(channel.failed_count || 0)}</Text></Paper>
	                  <Paper radius="md" px="xs" py={6} className="push-channel-metric"><Text size="xs" c="dimmed">最近</Text><Text fw={800} size="xs">{channel.last_delivery_at ? relativeTimeLabel(channel.last_delivery_at) : "暂无"}</Text></Paper>
	                </SimpleGrid>
                {expanded ? (
                  <Box mt="md" className="push-channel-detail">
	                    <SimpleGrid cols={{ base: 1, md: 2 }} spacing="sm">
	                      <InfoLine label={channel.type === "telegram_bot" ? "Chat IDs" : "Webhook"} value={maskedUrl(endpoint)} />
	                      {channel.type === "telegram_bot" ? <InfoLine label="代理" value={channel.config?.proxy_url || "直连"} /> : null}
	                      <InfoLine label="触发等级" value={`L${channel.min_risk_level}+`} />
	                    </SimpleGrid>
                    <Group mt="sm" gap="xs">
                      <Button size="xs" variant="light" leftSection={<IconSend size={13} />} onClick={() => testChannel(channel.id)}>发送测试</Button>
                      <Button size="xs" variant="subtle" leftSection={<IconEdit size={13} />} onClick={() => openChannelDrawer(channel)}>编辑配置</Button>
                      <Button size="xs" variant="subtle" onClick={() => changeDeliveryFilter({ ...deliveryFilters, channel_id: String(channel.id) })}>查看投递</Button>
                    </Group>
                  </Box>
                ) : null}
              </Paper>
            );
          })}
	        </SimpleGrid>
        {!channels.length ? <EmptyState text="还没有通知渠道。可以先新增飞书、Telegram Bot 或 Webhook，用于线索命中后的推送。" /> : null}
      </Card>

      <Drawer opened={drawerOpened} onClose={() => { setDrawerOpened(false); resetChannelForm(); }} title={editingChannelId ? "编辑通知渠道" : "新增通知渠道"} position="right" size="lg">
        <form onSubmit={saveChannel}>
          <Stack gap="md">
            <TextInput label="名称" value={form.name} onChange={(e) => setForm({ ...form, name: e.currentTarget.value })} required />
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <Select label="类型" data={notificationTypes} value={form.type} onChange={(value) => setForm({ ...form, type: value || "telegram_bot" })} />
              <Select label="最低推送等级" data={[1, 2, 3, 4, 5].map((value) => ({ value: String(value), label: `L${value}+` }))} value={String(form.min_risk_level)} onChange={(value) => setForm({ ...form, min_risk_level: Number(value || 1) })} />
            </SimpleGrid>
            {form.type === "telegram_bot" ? (
	              <>
	                <TextInput label="Bot Token" value={form.bot_token} onChange={(e) => setForm({ ...form, bot_token: e.currentTarget.value })} required />
	                <TextInput label="Chat IDs" placeholder="逗号分隔" value={form.chat_ids} onChange={(e) => setForm({ ...form, chat_ids: e.currentTarget.value })} required />
	                <TextInput label="代理 URL" description="Telegram Bot API 访问超时时使用；Docker 中连接宿主机代理请使用 host.docker.internal。" placeholder="socks5://host.docker.internal:7891" value={form.proxy_url} onChange={(e) => setForm({ ...form, proxy_url: e.currentTarget.value })} />
	              </>
            ) : (
              form.type === "dingtalk" ? (
                <>
                  <TextInput label="Webhook URL 或 Access Token" description="支持直接填完整机器人地址，也可只填 access_token；钉钉签名可选。" value={form.url} onChange={(e) => setForm({ ...form, url: e.currentTarget.value })} />
                  <TextInput label="Access Token" value={form.access_token || ""} onChange={(e) => setForm({ ...form, access_token: e.currentTarget.value })} />
                  <PasswordInput label="签名 Secret" value={form.secret || ""} onChange={(e) => setForm({ ...form, secret: e.currentTarget.value })} />
                </>
              ) : (
                <TextInput label={form.type === "feishu" ? "飞书 Webhook" : "企业微信 Webhook"} value={form.url} onChange={(e) => setForm({ ...form, url: e.currentTarget.value })} required />
              )
            )}
            <Checkbox label="启用通知渠道" checked={form.enabled} onChange={(event) => setForm({ ...form, enabled: event.currentTarget.checked })} />
            <Group justify="flex-end">
              <Button variant="subtle" color="gray" onClick={() => { setDrawerOpened(false); resetChannelForm(); }}>取消</Button>
              <Button type="submit">{editingChannelId ? "保存渠道" : "新增渠道"}</Button>
            </Group>
          </Stack>
        </form>
      </Drawer>

      <Card withBorder radius="lg" p="lg" className="push-delivery-card">
        <Group justify="space-between" align="flex-start" mb="md">
          <Stack gap={2}>
            <Title order={3}>最近投递</Title>
            <Text c="dimmed" size="sm">用于排查命中线索是否成功推送，以及查看失败原因。</Text>
          </Stack>
          <Group gap="xs">
            <Button variant="subtle" onClick={() => setDeliveriesExpanded((value) => !value)}>{deliveriesExpanded ? "收起表格" : "展开表格"}</Button>
            <Button variant="light" leftSection={<IconRefresh size={15} />} loading={deliveryLoading} onClick={retryFailedDeliveries}>重试失败</Button>
          </Group>
        </Group>
        {deliveriesExpanded ? (
          <>
            <Grid align="end" gutter="sm" mb="md">
              <Grid.Col span={{ base: 12, md: 4 }}>
                <Select
                  size="sm"
                  label="渠道"
                  placeholder="全部渠道"
                  data={channelOptions}
                  value={deliveryFilters.channel_id}
                  onChange={(value) => changeDeliveryFilter({ ...deliveryFilters, channel_id: value || "" })}
                  clearable
                  searchable
                />
              </Grid.Col>
              <Grid.Col span={{ base: 12, md: 3 }}>
                <Select
                  size="sm"
                  label="状态"
                  data={[{ value: "all", label: "全部" }, { value: "delivered", label: "成功" }, { value: "failed", label: "失败" }, { value: "pending", label: "等待中" }]}
                  value={deliveryFilters.status}
                  onChange={(value) => changeDeliveryFilter({ ...deliveryFilters, status: value || "all" })}
                />
              </Grid.Col>
              <Grid.Col span={{ base: 12, md: 2 }}>
                <Button size="sm" variant="light" fullWidth loading={deliveryLoading} onClick={() => loadDeliveryRows(deliveryFilters, deliveryPage)}>刷新</Button>
              </Grid.Col>
            </Grid>
            <Table.ScrollContainer minWidth={940}>
              <Table verticalSpacing="sm" striped highlightOnHover className="push-delivery-table">
                <Table.Thead>
                  <Table.Tr>
                    <DeliverySortHeader label="渠道" sortKey="channel" width={230} />
                    <DeliverySortHeader label="状态" sortKey="status" width={130} />
                    <DeliverySortHeader label="消息" sortKey="message" width={110} />
                    <Table.Th>来源 / 规则</Table.Th>
                    <DeliverySortHeader label="尝试" sortKey="attempts" width={90} />
                    <DeliverySortHeader label="时间" sortKey="created_at" width={170} />
                    <Table.Th w={220}>错误摘要</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {deliveryRows.map((row) => {
                    return (
                      <Table.Tr key={row.id} className="clickable-row" onClick={() => setSelectedDelivery(row)}>
                        <Table.Td><Text fw={700} size="sm">{row.channel_name || `渠道 #${row.channel_id || "-"}`}</Text><Text size="xs" c="dimmed">{channelTypeLabel(row.channel_type) || "-"}</Text></Table.Td>
                        <Table.Td><StatusBadge value={row.status} /></Table.Td>
                        <Table.Td><Text size="sm">#{row.message_id || "-"}</Text><Text size="xs" c="dimmed">{row.message_tg_id ? `TG ${row.message_tg_id}` : "测试/系统"}</Text></Table.Td>
                        <Table.Td><Text size="sm" fw={700} lineClamp={1}>{row.message_source || "-"}</Text><Text size="xs" c="dimmed" lineClamp={1}>{row.message_rule || "-"}</Text></Table.Td>
                        <Table.Td><Text size="sm">{row.attempts || 0}</Text></Table.Td>
                        <Table.Td><Text size="sm">{formatTime(row.created_at)}</Text></Table.Td>
                        <Table.Td><Text size="sm" c={row.error ? "red" : "dimmed"} lineClamp={1}>{row.error || "-"}</Text></Table.Td>
                      </Table.Tr>
                    );
                  })}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
            <Group justify="space-between" mt="md" align="center">
              <Group gap="xs">
                <Text size="sm" c="dimmed">共 {deliveryTotal} 条</Text>
                <SegmentedControl size="xs" value={String(deliveryPageSize)} data={["25", "50", "100", "200"]} onChange={changeDeliveryPageSize} />
              </Group>
              <Pagination size="sm" total={Math.max(1, Math.ceil((deliveryTotal || 0) / (Number(deliveryPageSize) || 25)))} value={deliveryPage} onChange={changeDeliveryPage} siblings={1} boundaries={1} />
            </Group>
            {!deliveryRows.length ? <EmptyState text={deliveryLoading ? "正在加载投递记录..." : "暂无投递记录。"} /> : null}
          </>
        ) : (
          <Text size="sm" c="dimmed">投递表格已收起，当前缓存 {deliveryRows.length} 条记录。</Text>
        )}
      </Card>
      <Drawer opened={Boolean(selectedDelivery)} onClose={() => setSelectedDelivery(null)} title="投递详情" position="right" size="lg">
        {selectedDelivery ? (
          <Stack gap="md">
            <Group justify="space-between">
              <Box>
                <Text fw={900}>{selectedDelivery.channel_name || `渠道 #${selectedDelivery.channel_id || "-"}`}</Text>
                <Text size="sm" c="dimmed">投递 #{selectedDelivery.id} · {channelTypeLabel(selectedDelivery.channel_type)}</Text>
              </Box>
              <StatusBadge value={selectedDelivery.status} />
            </Group>
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
              <InfoLine label="创建时间" value={formatTime(selectedDelivery.created_at)} />
              <InfoLine label="送达时间" value={selectedDelivery.delivered_at ? formatTime(selectedDelivery.delivered_at) : "-"} />
              <InfoLine label="尝试次数" value={String(selectedDelivery.attempts || 0)} />
              <InfoLine label="消息记录" value={selectedDelivery.message_id ? `#${selectedDelivery.message_id}` : "测试/系统"} />
              <InfoLine label="Telegram 消息" value={selectedDelivery.message_tg_id || "-"} />
              <InfoLine label="风险等级" value={selectedDelivery.message_risk_level ? `L${selectedDelivery.message_risk_level}` : "-"} />
              <InfoLine label="来源" value={selectedDelivery.message_source || "-"} />
              <InfoLine label="源 ID" value={selectedDelivery.message_source_id || "-"} />
              <InfoLine label="消息时间" value={selectedDelivery.message_event_time ? formatTime(selectedDelivery.message_event_time) : "-"} />
              <InfoLine label="命中规则" value={selectedDelivery.message_rule || "-"} />
            </SimpleGrid>
            <Paper withBorder radius="md" p="md" className="push-delivery-detail">
              <Text fw={800} mb={6}>消息摘要</Text>
              <Text size="sm" c={selectedDelivery.message_summary ? undefined : "dimmed"}>{selectedDelivery.message_summary || "暂无消息内容，可能是测试投递或原消息已删除。"}</Text>
            </Paper>
            {selectedDelivery.error ? <Alert color="red" title="错误详情">{selectedDelivery.error}</Alert> : <Alert color="teal" title="投递正常">当前投递没有记录错误。</Alert>}
          </Stack>
        ) : null}
      </Drawer>
    </Stack>
  );
}

function Runs({ initialRuns = [], targets = [], accounts = [], defaultPageSize = "50" }) {
  const [selected, setSelected] = useState(null);
  const [runs, setRuns] = useState(initialRuns);
  const [total, setTotal] = useState(initialRuns.length);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(defaultPageSize);
  const [statusFilter, setStatusFilter] = useState("all");
  const [modeFilter, setModeFilter] = useState("all");
  const [targetFilter, setTargetFilter] = useState("");
  const [runSort, setRunSort] = useState({ key: "started_at", direction: "desc" });
  const [loading, setLoading] = useState(false);
  const targetById = useMemo(() => new Map(targets.map((target) => [String(target.id), target])), [targets]);
  const accountById = useMemo(() => new Map(accounts.map((account) => [String(account.id), account])), [accounts]);
  const targetOptions = targets.map((target) => ({
    value: String(target.id),
    label: targetDisplayName(target)
  }));

  function runQuery(nextPage = page, nextPageSize = pageSize, nextSort = runSort) {
    const limit = Number(nextPageSize) || 50;
    const params = new URLSearchParams();
    params.set("limit", String(limit));
    params.set("offset", String(Math.max(0, nextPage - 1) * limit));
    params.set("sort", nextSort.key);
    params.set("direction", nextSort.direction);
    if (targetFilter) params.set("target_id", targetFilter);
    if (statusFilter !== "all") params.set("status", statusFilter);
    if (modeFilter !== "all") params.set("mode", modeFilter);
    return params.toString();
  }

  function runCountQuery() {
    const params = new URLSearchParams();
    if (targetFilter) params.set("target_id", targetFilter);
    if (statusFilter !== "all") params.set("status", statusFilter);
    if (modeFilter !== "all") params.set("mode", modeFilter);
    return params.toString();
  }

  async function loadRuns(nextPage = page, nextPageSize = pageSize, nextSort = runSort) {
    setLoading(true);
    try {
      const [rows, count] = await Promise.all([
        api(`/runs?${runQuery(nextPage, nextPageSize, nextSort)}`),
        api(`/runs/count?${runCountQuery()}`)
      ]);
      setRuns(rows);
      setTotal(count.total || 0);
    } catch (error) {
      notifyError(error);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadRuns(1, pageSize);
    setPage(1);
  }, [targetFilter, statusFilter, modeFilter, runSort]);

  useEffect(() => {
    setPageSize(defaultPageSize);
    setPage(1);
    loadRuns(1, defaultPageSize);
  }, [defaultPageSize]);

  useEffect(() => {
    if (page !== 1 || targetFilter || statusFilter !== "all" || modeFilter !== "all" || runSort.key !== "started_at" || runSort.direction !== "desc") return;
    setRuns(initialRuns);
    setTotal((current) => Math.max(current, initialRuns.length));
  }, [initialRuns, page, targetFilter, statusFilter, modeFilter, runSort]);

  async function openRun(id) {
    try {
      setSelected(await api(`/runs/${id}`));
    } catch (error) {
      notifyError(error);
    }
  }

  async function changePage(nextPage) {
    setPage(nextPage);
    await loadRuns(nextPage);
  }

  async function changePageSize(value) {
    const nextPageSize = value || "50";
    setPageSize(nextPageSize);
    setPage(1);
    await loadRuns(1, nextPageSize);
  }

  function setRunSortKey(key) {
    const nextSort = {
      key,
      direction: runSort.key === key && runSort.direction === "asc" ? "desc" : "asc"
    };
    setRunSort(nextSort);
    setPage(1);
    loadRuns(1, pageSize, nextSort);
  }

  function RunSortHeader({ label, sortKey, width }) {
    const active = runSort.key === sortKey;
    return (
      <Table.Th w={width}>
        <UnstyledButton className={`target-sort-header ${active ? "active" : ""}`} onClick={() => setRunSortKey(sortKey)}>
          <span>{label}</span>
          <span className="target-sort-indicator">{active ? (runSort.direction === "asc" ? "↑" : "↓") : "↕"}</span>
        </UnstyledButton>
      </Table.Th>
    );
  }

  function runAccountLabel(run) {
    const account = run.account_id ? accountById.get(String(run.account_id)) : null;
    return run.account_label || account?.label || account?.phone || (run.account_id ? `账号 ${run.account_id}` : "未分配账号");
  }

  function runTargetLabel(run) {
    const target = run.target_id ? targetById.get(String(run.target_id)) : null;
    if (run.target_title) return run.target_title;
    if (target) return targetDisplayName(target);
    if (run.mode === "live" && run.account_id) return `${runAccountLabel(run)} · 实时监听`;
    if (!run.target_id) return "账号级任务";
    return `目标 #${run.target_id}`;
  }

  function runTargetSubLabel(run) {
    const target = run.target_id ? targetById.get(String(run.target_id)) : null;
    if (run.target_ref) return run.target_ref;
    if (target) return targetDisplayHandle(target);
    return run.mode === "live" ? "监听该账号绑定的全部目标" : "未绑定单个目标";
  }

  function runModeLabel(value = "") {
    return ({
      live: "实时监听",
      backfill: "历史回填",
      manual: "手动",
      scheduler: "自动调度"
    })[String(value).toLowerCase()] || value || "-";
  }

  function formatDuration(seconds) {
    if (seconds === null || seconds === undefined) return "-";
    const value = Math.max(0, Number(seconds) || 0);
    if (value < 60) return `${value}秒`;
    if (value < 3600) return `${Math.floor(value / 60)}分${value % 60}秒`;
    return `${Math.floor(value / 3600)}小时${Math.floor((value % 3600) / 60)}分`;
  }

  const numericPageSize = Number(pageSize) || 50;
  const totalPages = Math.max(1, Math.ceil((total || 0) / numericPageSize));
  const rangeStart = total ? (page - 1) * numericPageSize + 1 : 0;
  const rangeEnd = Math.min(page * numericPageSize, total || 0);

  return (
    <Stack gap="sm" className="runs-view">
      <Card withBorder radius="lg" p={0} className="run-table-card">
        <Group justify="space-between" px="md" py="sm" className="run-table-toolbar" align="flex-end">
          <Box>
            <Title order={3}>采集任务列表</Title>
            <Text size="sm" c="dimmed">当前页 {runs.length} 条，匹配任务 {total || 0} 条。</Text>
          </Box>
          <Group gap="xs" className="run-list-controls">
            <Select
              w={190}
              placeholder="全部目标"
              data={targetOptions}
              value={targetFilter}
              onChange={(value) => setTargetFilter(value || "")}
              clearable
              searchable
              leftSection={<IconSearch size={15} />}
            />
            <Select
              w={130}
              value={modeFilter}
              onChange={(value) => setModeFilter(value || "all")}
              data={[
                { value: "all", label: "全部模式" },
                { value: "live", label: "实时监听" },
                { value: "backfill", label: "历史回填" },
                { value: "manual", label: "手动" }
              ]}
            />
            <Select
              w={130}
              value={statusFilter}
              onChange={(value) => setStatusFilter(value || "all")}
              data={[
                { value: "all", label: "全部状态" },
                { value: "running", label: "运行中" },
                { value: "backfilling", label: "回填中" },
                { value: "success", label: "成功" },
                { value: "failed", label: "失败" },
                { value: "error", label: "异常" }
              ]}
            />
            <SegmentedControl
              size="xs"
              className="page-size-control"
              value={pageSize}
              onChange={changePageSize}
              data={["25", "50", "100", "200"]}
            />
            <Tooltip label="刷新当前页">
              <ActionIcon size="lg" variant="light" onClick={() => loadRuns(page)} loading={loading}>
                <IconRefresh size={16} />
              </ActionIcon>
            </Tooltip>
          </Group>
        </Group>
        <Table.ScrollContainer minWidth={860}>
          <Table verticalSpacing="sm" horizontalSpacing="md" striped highlightOnHover className="run-table">
            <Table.Thead>
              <Table.Tr>
                <RunSortHeader label="任务" sortKey="target" width={280} />
                <RunSortHeader label="模式" sortKey="mode" width={110} />
                <RunSortHeader label="读取" sortKey="records_seen" width={80} />
                <RunSortHeader label="写入" sortKey="records_written" width={80} />
                <RunSortHeader label="开始" sortKey="started_at" width={150} />
                <RunSortHeader label="耗时" sortKey="duration" width={90} />
                <RunSortHeader label="状态" sortKey="status" width={100} />
                <Table.Th w={90} />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {runs.map((run) => (
                <Table.Tr key={run.id} className="run-table-row">
	                  <Table.Td>
	                    <Stack gap={2}>
	                      <Text fw={800} size="sm" maw={260} truncate="end">{runTargetLabel(run)}</Text>
	                      <Text size="xs" c="dimmed">#{run.id} · {runAccountLabel(run)} · {runTargetSubLabel(run)}</Text>
	                    </Stack>
	                  </Table.Td>
                  <Table.Td><Badge variant="light">{runModeLabel(run.mode)}</Badge></Table.Td>
                  <Table.Td>{run.records_seen}</Table.Td>
	                  <Table.Td>{run.records_written}</Table.Td>
	                  <Table.Td>{formatTime(run.started_at)}</Table.Td>
	                  <Table.Td>{formatDuration(run.duration_seconds)}</Table.Td>
                  <Table.Td><StatusBadge value={run.status} /></Table.Td>
                  <Table.Td><Button size="xs" variant="light" onClick={() => openRun(run.id)}>日志详情</Button></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        {!runs.length ? <EmptyState text="暂无采集任务。可以先启动监听或执行一次历史回填。" /> : null}
        <Group justify="space-between" px="md" py="sm" className="run-table-footer">
          <Text size="sm" c="dimmed">第 {page} / {totalPages} 页，{rangeStart}-{rangeEnd} / {total || 0}</Text>
          <Pagination size="sm" total={totalPages} value={page} onChange={changePage} siblings={1} boundaries={1} />
        </Group>
      </Card>
      <Modal opened={Boolean(selected)} onClose={() => setSelected(null)} title="采集任务详情" size="lg">
        {selected ? (
          <Stack>
            <SimpleGrid cols={2}>
              <Text>任务 ID：#{selected.id}</Text>
              <Text>状态：{selected.status}</Text>
              <Text>账号：{runAccountLabel(selected)}</Text>
              <Text>目标：{runTargetLabel(selected)}</Text>
              <Text>读取：{selected.records_seen}</Text>
              <Text>写入：{selected.records_written}</Text>
              <Text>开始：{formatTime(selected.started_at)}</Text>
              <Text>结束：{formatTime(selected.finished_at)}</Text>
              <Text>耗时：{formatDuration(selected.duration_seconds)}</Text>
              <Text>目标 ID：{selected.target_id || "-"}</Text>
            </SimpleGrid>
            <Paper withBorder p="md" radius="md">
              <Text fw={700} mb="xs">错误 / 日志</Text>
              <Text className="message-content" c={selected.error ? "red" : "dimmed"}>{selected.error || "暂无错误。当前版本记录任务摘要，后续可扩展逐条日志。"}</Text>
            </Paper>
          </Stack>
        ) : null}
      </Modal>
    </Stack>
  );
}

const COLLECTION_CONFIG_DEFAULTS = {
  auto_backfill_on_import: true,
  auto_start_listening_on_import: true,
  initial_backfill_limit: 5000,
  initial_backfill_window_hours: 24,
  backfill_enabled: true,
  backfill_interval_seconds: 900,
  backfill_limit_per_target: 10000,
  backfill_window_hours: 4,
  max_concurrent_initial_jobs: 3,
  max_initial_jobs_per_account: 1,
  max_targets_per_account: 80
};

function compactNumber(value, fallback, min, max) {
  const parsed = Number(value);
  const next = Number.isFinite(parsed) ? parsed : fallback;
  return Math.max(min, Math.min(max, Math.round(next)));
}

function normalizeCollectionPayload(form) {
  return {
    auto_backfill_on_import: Boolean(form.auto_backfill_on_import),
    auto_start_listening_on_import: Boolean(form.auto_start_listening_on_import),
    initial_backfill_limit: compactNumber(form.initial_backfill_limit, COLLECTION_CONFIG_DEFAULTS.initial_backfill_limit, 0, 20000),
    initial_backfill_window_hours: compactNumber(form.initial_backfill_window_hours, COLLECTION_CONFIG_DEFAULTS.initial_backfill_window_hours, 1, 168),
    backfill_enabled: Boolean(form.backfill_enabled),
    backfill_interval_seconds: compactNumber(form.backfill_interval_seconds, COLLECTION_CONFIG_DEFAULTS.backfill_interval_seconds, 60, 86400),
    backfill_limit_per_target: compactNumber(form.backfill_limit_per_target, COLLECTION_CONFIG_DEFAULTS.backfill_limit_per_target, 1, 20000),
    backfill_window_hours: compactNumber(form.backfill_window_hours, COLLECTION_CONFIG_DEFAULTS.backfill_window_hours, 1, 168),
    max_concurrent_initial_jobs: compactNumber(form.max_concurrent_initial_jobs, COLLECTION_CONFIG_DEFAULTS.max_concurrent_initial_jobs, 1, 20),
    max_initial_jobs_per_account: compactNumber(form.max_initial_jobs_per_account, COLLECTION_CONFIG_DEFAULTS.max_initial_jobs_per_account, 1, 5),
    max_targets_per_account: compactNumber(form.max_targets_per_account, COLLECTION_CONFIG_DEFAULTS.max_targets_per_account, 0, 10000)
  };
}

function SettingsPanel({ sinks, storageOverview, systemDatabase, intelligenceConfig, collectionConfig, uiPrefs, onUiPrefsChange, reload }) {
  const normalizedCollectionConfig = useMemo(() => {
    const { scheduler: _scheduler, ...config } = collectionConfig || {};
    return config;
  }, [collectionConfig]);
  const database = storageOverview?.database || {};
  const tableCounts = database.table_counts || {};
  const sinkRows = storageOverview?.sinks || sinks || [];
  const initialEngine = systemDatabase?.engine || database.engine || "postgresql";
  const [dbForm, setDbForm] = useState({
    engine: initialEngine === "sqlite" ? "sqlite" : "postgresql",
    host: systemDatabase?.host || database.host || "localhost",
    port: systemDatabase?.port || 5432,
    database: systemDatabase?.database || database.database || "watchout_telegram",
    username: systemDatabase?.username || "watchout",
    password: "",
    sqlite_path: systemDatabase?.sqlite_path || "./data/app.db",
    url: ""
  });
  const [dbTest, setDbTest] = useState(null);
  const [smartConfig, setSmartConfig] = useState(() => ({
    platform_language: "zh-CN",
    translation: {
      enabled: false,
      engine: "tencent",
      baidu_app_id: "",
      baidu_secret_key: "",
      tencent_secret_id: "",
      tencent_secret_key: "",
      tencent_region: "ap-guangzhou",
      target_language: "auto"
    },
    ocr: { enabled: false, engine: "paddleocr", max_image_mb: 5, delete_after_ocr: true, include_in_search: true, include_in_rules: true },
    summary: { enabled: false, mode: "structured", min_chars: 600 },
    ...(intelligenceConfig || {})
  }));
  const [collectionForm, setCollectionForm] = useState(() => ({ ...COLLECTION_CONFIG_DEFAULTS, ...normalizedCollectionConfig }));
  const [collectionScheduler, setCollectionScheduler] = useState(collectionConfig?.scheduler || {});
  const [collectionDirty, setCollectionDirty] = useState(false);
  const [collectionSaving, setCollectionSaving] = useState(false);
  const [translationTestText, setTranslationTestText] = useState("Hello WatchOut, this is a translation test.");
  const [translationTestResult, setTranslationTestResult] = useState(null);
  const [translationTesting, setTranslationTesting] = useState(false);
  const [passwordForm, setPasswordForm] = useState({ current_password: "", new_password: "", confirm_password: "" });
  const [passwordSaving, setPasswordSaving] = useState(false);
  const translationEngine = smartConfig.translation?.engine || "baidu";

  function updateDbForm(field, value) {
    setDbForm((current) => ({ ...current, [field]: value }));
    setDbTest(null);
  }

  function updateUiPrefs(field, value) {
    const next = saveUiPrefs({ ...uiPrefs, [field]: value });
    onUiPrefsChange?.(next);
    notifyOk("界面偏好已保存到本地");
  }

  function updateSmartConfig(path, value) {
    setSmartConfig((current) => {
      const next = { ...current, translation: { ...(current.translation || {}) }, ocr: { ...(current.ocr || {}) }, summary: { ...(current.summary || {}) } };
      if (path.includes(".")) {
        const [group, key] = path.split(".");
        next[group] = { ...(next[group] || {}), [key]: value };
      } else {
        next[path] = value;
      }
      return next;
    });
  }

  function updateCollectionForm(field, value) {
    setCollectionDirty(true);
    setCollectionForm((current) => ({ ...current, [field]: value }));
  }

  function updatePasswordForm(field, value) {
    setPasswordForm((current) => ({ ...current, [field]: value }));
  }

  function updateBackfillIntervalMinutes(value) {
    const minutes = Math.max(1, Number(value) || 15);
    updateCollectionForm("backfill_interval_seconds", minutes * 60);
  }

  async function saveSmartConfig() {
    try {
      const updated = await api("/system/intelligence/config", { method: "PUT", body: smartConfig });
      setSmartConfig(updated);
      notifyOk("智能增强设置已保存");
      if (reload) await reload();
    } catch (error) {
      notifyError(error);
    }
  }

  async function testTranslation() {
    setTranslationTesting(true);
    setTranslationTestResult(null);
    try {
      const result = await api("/system/intelligence/translate-test", {
        method: "POST",
        body: {
          text: translationTestText,
          target_language: smartConfig.translation?.target_language || "auto",
          config: smartConfig
        }
      });
      setTranslationTestResult(result);
      if (result.translation_status === "translated") notifyOk("翻译测试成功");
      else if (result.translation_status === "skipped") notifyOk("翻译测试跳过");
      else notifyError(new Error(result.desc || "翻译测试失败"));
    } catch (error) {
      notifyError(error);
    } finally {
      setTranslationTesting(false);
    }
  }

  async function saveCollectionConfig() {
    const payload = normalizeCollectionPayload(collectionForm);
    setCollectionSaving(true);
    try {
      const updated = await api("/system/collection/config", { method: "PUT", body: payload });
      const { scheduler, ...config } = updated || {};
      setCollectionForm({ ...COLLECTION_CONFIG_DEFAULTS, ...config });
      setCollectionScheduler(scheduler || {});
      setCollectionDirty(false);
      notifyOk("采集运行设置已保存");
    } catch (error) {
      notifyError(error);
      return;
    } finally {
      setCollectionSaving(false);
    }
    if (reload) {
      try {
        await reload();
      } catch (error) {
        notifyError(new Error(`配置已保存，但刷新最新状态失败：${error.message}`));
      }
    }
  }

  async function changeLoginPassword() {
    const nextPassword = String(passwordForm.new_password || "");
    if (nextPassword.length < 8) {
      notifyError(new Error("新密码至少需要 8 位"));
      return;
    }
    if (nextPassword !== passwordForm.confirm_password) {
      notifyError(new Error("两次输入的新密码不一致"));
      return;
    }
    setPasswordSaving(true);
    try {
      await api("/auth/me/password", {
        method: "POST",
        body: {
          current_password: passwordForm.current_password,
          new_password: nextPassword
        }
      });
      setPasswordForm({ current_password: "", new_password: "", confirm_password: "" });
      notifyOk("登录密码已修改");
    } catch (error) {
      notifyError(error);
    } finally {
      setPasswordSaving(false);
    }
  }

  useEffect(() => {
    if (!collectionConfig || collectionDirty) return;
    const { scheduler, ...config } = collectionConfig;
    setCollectionForm({ ...COLLECTION_CONFIG_DEFAULTS, ...config });
    setCollectionScheduler(scheduler || {});
  }, [collectionConfig, collectionDirty]);

  async function testDatabase() {
    setDbTest(null);
    try {
      const result = await api("/system/database/test", { method: "POST", body: dbForm });
      setDbTest(result);
      if (result.ok) notifyOk("数据库连接测试通过");
      else notifyError(new Error(result.message || "数据库连接失败"));
    } catch (error) {
      notifyError(error);
    }
  }

  return (
    <Tabs defaultValue="database" className="settings-tabs">
      <Tabs.List mb="md">
        <Tabs.Tab value="database" leftSection={<IconDatabase size={16} />}>数据库</Tabs.Tab>
        <Tabs.Tab value="sinks" leftSection={<IconServer size={16} />}>外部存储</Tabs.Tab>
        <Tabs.Tab value="system" leftSection={<IconTerminal size={16} />}>系统</Tabs.Tab>
        <Tabs.Tab value="collection" leftSection={<IconHistory size={16} />}>采集</Tabs.Tab>
        <Tabs.Tab value="intelligence" leftSection={<IconMessageSearch size={16} />}>智能增强</Tabs.Tab>
        <Tabs.Tab value="about" leftSection={<IconBrandTelegram size={16} />}>关于</Tabs.Tab>
      </Tabs.List>

      <Tabs.Panel value="database">
        <Stack>
          <Card withBorder radius="md" p="lg" className="settings-database-card">
            <Group justify="space-between" align="flex-start" mb="md">
              <Group gap="sm">
                <ThemeIcon color="cyan" variant="light" size={42} radius="md">
                  <IconDatabase size={22} />
                </ThemeIcon>
                <Stack gap={2}>
                  <Title order={3}>主数据库</Title>
                  <Text c="dimmed" size="sm">默认使用 PostgreSQL；SQLite 适合本地演示或轻量试用。修改主数据库配置后需要重启后端生效。</Text>
                </Stack>
              </Group>
              <StatusBadge value={database.status || "active"} label={database.status_note || statusLabel(database.status)} />
            </Group>
            <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="sm">
              <Paper withBorder radius="md" p="md" className="settings-metric">
                <Text size="xs" c="dimmed">当前引擎</Text>
                <Group gap={6} mt={4}><IconServer size={16} /><Text fw={800}>{database.engine || "unknown"}</Text></Group>
              </Paper>
              <Paper withBorder radius="md" p="md" className="settings-metric">
                <Text size="xs" c="dimmed">数据库</Text>
                <Text fw={800} mt={4}>{database.database || "-"}</Text>
              </Paper>
              <Paper withBorder radius="md" p="md" className="settings-metric">
                <Text size="xs" c="dimmed">地址</Text>
                <Text fw={800} mt={4}>{database.host || "-"}{database.port ? `:${database.port}` : ""}</Text>
              </Paper>
              <Paper withBorder radius="md" p="md" className="settings-metric">
                <Text size="xs" c="dimmed">数据表</Text>
                <Text fw={800} mt={4}>{database.table_count ?? "-"}</Text>
              </Paper>
            </SimpleGrid>
            <Paper withBorder radius="md" p="sm" mt="md" className="settings-url">
              <Text size="xs" c="dimmed" mb={4}>当前连接串（已脱敏）</Text>
              <Text size="sm" ff="monospace">{database.url || systemDatabase?.url || "-"}</Text>
            </Paper>
          </Card>

          <Card withBorder radius="md" p="lg">
            <Group justify="space-between" align="flex-start" mb="md">
              <Stack gap={2}>
                <Title order={4}>连接配置</Title>
                <Text c="dimmed" size="sm">第一阶段先提供配置填写和连接测试，保存到运行配置将在下一步接入。</Text>
              </Stack>
              <SegmentedControl
                value={dbForm.engine}
                onChange={(value) => updateDbForm("engine", value)}
                data={[{ label: "PostgreSQL", value: "postgresql" }, { label: "SQLite", value: "sqlite" }]}
              />
            </Group>
            {dbForm.engine === "postgresql" ? (
              <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
                <TextInput label="Host" value={dbForm.host} onChange={(event) => updateDbForm("host", event.currentTarget.value)} />
                <NumberInput label="Port" min={1} max={65535} value={dbForm.port} onChange={(value) => updateDbForm("port", value || 5432)} />
                <TextInput label="Database" value={dbForm.database} onChange={(event) => updateDbForm("database", event.currentTarget.value)} />
                <TextInput label="Username" value={dbForm.username} onChange={(event) => updateDbForm("username", event.currentTarget.value)} />
                <PasswordInput label="Password" value={dbForm.password} onChange={(event) => updateDbForm("password", event.currentTarget.value)} />
                <TextInput label="完整连接串（可选）" placeholder="postgresql+psycopg://user:pass@host:5432/db" value={dbForm.url} onChange={(event) => updateDbForm("url", event.currentTarget.value)} />
              </SimpleGrid>
            ) : (
              <TextInput label="SQLite 文件路径" value={dbForm.sqlite_path} onChange={(event) => updateDbForm("sqlite_path", event.currentTarget.value)} />
            )}
            <Group mt="md">
              <Button leftSection={<IconRefresh size={16} />} onClick={testDatabase}>测试连接</Button>
              <Button variant="light" disabled>保存配置</Button>
              {reload ? <Button variant="subtle" onClick={reload}>刷新状态</Button> : null}
            </Group>
            {dbTest ? (
              <Alert mt="md" color={dbTest.ok ? "teal" : "red"} icon={dbTest.ok ? <IconCircleCheck size={16} /> : <IconAlertTriangle size={16} />}>
                {dbTest.message}<Text size="xs" mt={4} ff="monospace">{dbTest.url}</Text>
              </Alert>
            ) : null}
          </Card>

          <Card withBorder radius="md" p="lg">
            <Group justify="space-between" mb="sm">
              <Title order={4}>核心表数据量</Title>
              <Badge variant="light">当前连接</Badge>
            </Group>
            <Table.ScrollContainer minWidth={620}>
              <Table striped highlightOnHover className="settings-table">
                <Table.Thead>
                  <Table.Tr><Table.Th>表名</Table.Th><Table.Th>用途</Table.Th><Table.Th ta="right">行数</Table.Th></Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {[
                    ["telegram_accounts", "账号"],
                    ["telegram_targets", "监控目标"],
                    ["telegram_messages", "消息线索"],
                    ["monitor_rules", "监控规则"],
                    ["rule_hits", "命中记录"],
                    ["monitor_runs", "采集任务"],
                    ["crawl_errors", "采集异常"],
                    ["app_settings", "应用设置"]
                  ].map(([table, label]) => (
                    <Table.Tr key={table}>
                      <Table.Td ff="monospace">{table}</Table.Td>
                      <Table.Td>{label}</Table.Td>
                      <Table.Td ta="right">{tableCounts[table] ?? "-"}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </Card>
        </Stack>
      </Tabs.Panel>

      <Tabs.Panel value="sinks">
        <Card withBorder radius="md" p="lg">
          <Title order={4} mb="sm">外部存储</Title>
          <Text c="dimmed" size="sm" mb="md">这些是消息导出和分析 Sink，不影响主业务数据库。</Text>
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
            {sinkRows.map((sink) => (
              <Paper withBorder radius="md" key={sink.name} p="md" className="settings-sink-card">
                <Group justify="space-between" wrap="nowrap">
                  <Text fw={800}>{sink.name}</Text>
                  <StatusBadge value={sink.status} />
                </Group>
                <Text c="dimmed" size="sm" mt={8}>{sink.note}</Text>
                <Switch mt="md" label="启用" checked={Boolean(sink.enabled)} disabled />
              </Paper>
            ))}
          </SimpleGrid>
        </Card>
      </Tabs.Panel>

      <Tabs.Panel value="system">
        <Stack>
          <SimpleGrid cols={{ base: 1, md: 2 }}>
            <Card withBorder radius="md" p="lg">
              <Title order={4} mb="md">运行参数</Title>
              <Stack gap="sm">
                <Group justify="space-between"><Text c="dimmed">API 地址</Text><Text ff="monospace">{API_BASE}</Text></Group>
                <Group justify="space-between"><Text c="dimmed">自动回填</Text><Badge variant="light">已由后端配置控制</Badge></Group>
                <Group justify="space-between"><Text c="dimmed">会话目录</Text><Text ff="monospace">data/sessions</Text></Group>
              </Stack>
            </Card>
            <Card withBorder radius="md" p="lg">
              <Title order={4} mb="md">健康状态</Title>
              <Stack gap="sm">
                <Group justify="space-between"><Text c="dimmed">主数据库</Text><StatusBadge value={database.status || "active"} label={database.status_note || "连接正常"} /></Group>
                <Group justify="space-between"><Text c="dimmed">数据表</Text><Text fw={800}>{database.table_count ?? "-"}</Text></Group>
                <Group justify="space-between"><Text c="dimmed">存储 Sink</Text><Text fw={800}>{sinkRows.length}</Text></Group>
              </Stack>
            </Card>
          </SimpleGrid>
          <Card withBorder radius="md" p="lg">
            <Group justify="space-between" mb="md" align="flex-start">
              <Stack gap={2}>
                <Title order={4}>界面偏好</Title>
                <Text size="sm" c="dimmed">主题和默认分页会立即应用到当前浏览器。</Text>
              </Stack>
              <Badge variant="light">{uiPrefs.pageSize} 条/页</Badge>
            </Group>
            <SimpleGrid cols={{ base: 1, md: 2 }}>
              <Select
                label="主题模式"
                value={uiPrefs.colorScheme}
                onChange={(value) => updateUiPrefs("colorScheme", value || "light")}
                data={[
                  { value: "light", label: "浅色" },
                  { value: "soft", label: "柔和浅色" },
                  { value: "dark", label: "深色" },
                  { value: "midnight", label: "深蓝夜间" },
                  { value: "auto", label: "跟随系统" }
                ]}
              />
              <Select label="默认分页" value={uiPrefs.pageSize} onChange={(value) => updateUiPrefs("pageSize", value || "50")} data={["25", "50", "100", "200"].map((value) => ({ value, label: `${value} 条` }))} />
            </SimpleGrid>
          </Card>
          <Card withBorder radius="md" p="lg" className="settings-password-card">
            <Group justify="space-between" mb="md" align="flex-start">
              <Stack gap={2}>
                <Title order={4}>登录密码</Title>
                <Text size="sm" c="dimmed">修改当前后台账号的登录密码。修改成功后，新登录会使用新密码。</Text>
              </Stack>
              <Badge variant="light">当前账号</Badge>
            </Group>
            <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg" className="settings-password-layout">
              <Stack gap="sm" className="settings-password-form">
                <PasswordInput
                  label="当前密码"
                  value={passwordForm.current_password}
                  onChange={(event) => updatePasswordForm("current_password", event.currentTarget.value)}
                />
                <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
                  <PasswordInput
                    label="新密码"
                    description="至少 8 位"
                    value={passwordForm.new_password}
                    onChange={(event) => updatePasswordForm("new_password", event.currentTarget.value)}
                  />
                  <PasswordInput
                    label="确认新密码"
                    description="需与新密码一致"
                    value={passwordForm.confirm_password}
                    onChange={(event) => updatePasswordForm("confirm_password", event.currentTarget.value)}
                  />
                </SimpleGrid>
              </Stack>
              <Paper withBorder radius="md" p="md" className="settings-password-aside">
                <Stack gap="sm">
                  <Group gap="xs" wrap="nowrap">
                    <ThemeIcon variant="light" color="cyan" size="sm" radius="md">
                      <IconKey size={14} />
                    </ThemeIcon>
                    <Text fw={800} size="sm">安全提示</Text>
                  </Group>
                  <Text size="sm" c="dimmed">建议使用 8 位以上、包含数字和字母的密码。修改后当前会话仍可继续使用，下次登录需输入新密码。</Text>
                  <Group justify="flex-end" mt="xs">
                    <Button
                      variant="light"
                      color="gray"
                      onClick={() => setPasswordForm({ current_password: "", new_password: "", confirm_password: "" })}
                      disabled={passwordSaving}
                    >
                      清空
                    </Button>
                    <Button
                      leftSection={<IconKey size={16} />}
                      loading={passwordSaving}
                      onClick={changeLoginPassword}
                      disabled={!passwordForm.current_password || !passwordForm.new_password || !passwordForm.confirm_password}
                    >
                      修改密码
                    </Button>
                  </Group>
                </Stack>
              </Paper>
            </SimpleGrid>
          </Card>
        </Stack>
      </Tabs.Panel>

      <Tabs.Panel value="collection">
        <Stack gap="md">
          <Card withBorder radius="md" p="md">
            <Group justify="space-between" align="flex-start" mb="sm">
              <Stack gap={2}>
                <Group gap="xs">
                  <Title order={5}>新增目标初始化</Title>
                  {collectionDirty ? <Badge color="orange" variant="light">未保存</Badge> : <Badge color="teal" variant="light">已同步</Badge>}
                </Group>
                <Text c="dimmed" size="xs">导入后进入后台初始化队列；批量导入会按全局和账号并发上限排队。</Text>
              </Stack>
              <Badge variant="light">{collectionForm.initial_backfill_window_hours || 24} 小时窗口</Badge>
            </Group>
            <SimpleGrid cols={{ base: 1, sm: 2 }} mb="sm">
              <Switch size="sm" label="导入后自动回爬" checked={Boolean(collectionForm.auto_backfill_on_import)} onChange={(event) => updateCollectionForm("auto_backfill_on_import", event.currentTarget.checked)} />
              <Switch size="sm" label="导入后自动启动监听" checked={Boolean(collectionForm.auto_start_listening_on_import)} onChange={(event) => updateCollectionForm("auto_start_listening_on_import", event.currentTarget.checked)} />
            </SimpleGrid>
            <SimpleGrid cols={{ base: 1, md: 3 }} spacing="sm">
              <NumberInput size="sm" label="回爬窗口（小时）" min={1} max={168} value={collectionForm.initial_backfill_window_hours} onChange={(value) => updateCollectionForm("initial_backfill_window_hours", value || 24)} />
              <NumberInput size="sm" label="每目标消息上限" min={0} max={20000} value={collectionForm.initial_backfill_limit} onChange={(value) => updateCollectionForm("initial_backfill_limit", value ?? 5000)} />
              <NumberInput size="sm" label="每账号目标上限" min={0} max={10000} value={collectionForm.max_targets_per_account} onChange={(value) => updateCollectionForm("max_targets_per_account", value ?? 80)} />
              <NumberInput size="sm" label="全局初始化并发" min={1} max={20} value={collectionForm.max_concurrent_initial_jobs} onChange={(value) => updateCollectionForm("max_concurrent_initial_jobs", value || 3)} />
              <NumberInput size="sm" label="每账号初始化并发" min={1} max={5} value={collectionForm.max_initial_jobs_per_account} onChange={(value) => updateCollectionForm("max_initial_jobs_per_account", value || 1)} />
            </SimpleGrid>
            <Text mt="xs" size="xs" c="dimmed">建议每账号初始化并发保持 1；全局并发用于控制批量导入时的总体吞吐。</Text>
          </Card>

          <Card withBorder radius="md" p="md">
            <Group justify="space-between" align="flex-start" mb="sm">
              <Stack gap={2}>
                <Title order={5}>定时补偿回爬</Title>
                <Text c="dimmed" size="xs">用于补偿实时监听断线、重启或 Telegram 事件延迟造成的空窗。</Text>
              </Stack>
              <Badge variant="light">{Math.round((collectionForm.backfill_interval_seconds || 900) / 60)} 分钟一次</Badge>
            </Group>
            <SimpleGrid cols={{ base: 1, md: 4 }} spacing="sm">
              <Switch size="sm" label="启用定时回爬" checked={Boolean(collectionForm.backfill_enabled)} onChange={(event) => updateCollectionForm("backfill_enabled", event.currentTarget.checked)} />
              <NumberInput size="sm" label="间隔（分钟）" min={1} max={1440} value={Math.round((collectionForm.backfill_interval_seconds || 900) / 60)} onChange={updateBackfillIntervalMinutes} />
              <NumberInput size="sm" label="窗口（小时）" min={1} max={168} value={collectionForm.backfill_window_hours} onChange={(value) => updateCollectionForm("backfill_window_hours", value || 4)} />
              <NumberInput size="sm" label="每目标消息上限" min={1} max={20000} value={collectionForm.backfill_limit_per_target} onChange={(value) => updateCollectionForm("backfill_limit_per_target", value || 10000)} />
            </SimpleGrid>
            {collectionScheduler?.running ? (
              <Text mt="sm" size="xs" c="dimmed">调度器运行中，下一次回爬：{formatTime(collectionScheduler.next_run_at)}</Text>
            ) : (
              <Text mt="sm" size="xs" c="red">调度器未运行，请确认已启用定时回爬并重启后端。</Text>
            )}
          </Card>

          <Group justify="flex-end">
            <Button onClick={saveCollectionConfig} loading={collectionSaving}>保存采集设置</Button>
          </Group>
        </Stack>
      </Tabs.Panel>

      <Tabs.Panel value="intelligence">
        <Stack>
          <Card withBorder radius="md" p="lg">
            <Group justify="space-between" align="flex-start" mb="md">
              <Stack gap={2}>
                <Title order={4}>按需翻译</Title>
                <Text c="dimmed" size="sm">消息详情页点击翻译时才调用服务。默认目标语言跟随平台语言，也可以在这里固定。</Text>
              </Stack>
              <Badge variant="light">目标：{smartConfig.effective_translation_target || smartConfig.translation?.target_language || "auto"}</Badge>
            </Group>
            <SimpleGrid cols={{ base: 1, md: 2 }}>
              <Select label="平台语言" value={smartConfig.platform_language} onChange={(value) => updateSmartConfig("platform_language", value || "zh-CN")} data={[{ value: "zh-CN", label: "中文" }, { value: "en-US", label: "English" }, { value: "ja-JP", label: "日本語" }, { value: "ko-KR", label: "한국어" }]} />
              <Select label="默认翻译目标" value={smartConfig.translation?.target_language || "auto"} onChange={(value) => updateSmartConfig("translation.target_language", value || "auto")} data={[{ value: "auto", label: "跟随平台语言" }, { value: "zh", label: "中文" }, { value: "en", label: "English" }, { value: "ja", label: "日本語" }, { value: "ko", label: "한국어" }]} />
              <Select
                label="翻译引擎"
                value={translationEngine}
                onChange={(value) => updateSmartConfig("translation.engine", value || "tencent")}
                data={[
                  { value: "tencent", label: "腾讯云机器翻译" },
                  { value: "baidu", label: "百度云翻译" }
                ]}
              />
              {translationEngine === "baidu" ? (
                <>
                  <TextInput label="百度 APP ID" value={smartConfig.translation?.baidu_app_id || ""} onChange={(event) => updateSmartConfig("translation.baidu_app_id", event.currentTarget.value.trim())} />
                  <PasswordInput label="百度密钥" value={smartConfig.translation?.baidu_secret_key || ""} onChange={(event) => updateSmartConfig("translation.baidu_secret_key", event.currentTarget.value)} />
                </>
              ) : null}
              {translationEngine === "tencent" ? (
                <>
                  <TextInput label="腾讯云 SecretId" value={smartConfig.translation?.tencent_secret_id || ""} onChange={(event) => updateSmartConfig("translation.tencent_secret_id", event.currentTarget.value.trim())} />
                  <PasswordInput label="腾讯云 SecretKey" value={smartConfig.translation?.tencent_secret_key || ""} onChange={(event) => updateSmartConfig("translation.tencent_secret_key", event.currentTarget.value)} />
                  <TextInput label="腾讯云地域" value={smartConfig.translation?.tencent_region || "ap-guangzhou"} onChange={(event) => updateSmartConfig("translation.tencent_region", event.currentTarget.value.trim())} />
                </>
              ) : null}
            </SimpleGrid>
            <Divider my="md" />
            <Stack gap="sm">
              <Group justify="space-between" align="flex-start">
                <Stack gap={2}>
                  <Title order={5}>翻译测试</Title>
                  <Text c="dimmed" size="xs">这里直接调用当前智能增强配置，不依赖消息记录。可以验证接口、鉴权和实际译文。</Text>
                </Stack>
                <Button size="compact-sm" onClick={testTranslation} loading={translationTesting}>测试翻译</Button>
              </Group>
              <Textarea
                label="测试文本"
                minRows={4}
                autosize
                value={translationTestText}
                onChange={(event) => setTranslationTestText(event.currentTarget.value)}
                placeholder="输入一段需要验证的原文"
              />
              {translationTestResult ? (
                <Paper withBorder radius="md" p="sm">
                  <SimpleGrid cols={{ base: 1, md: 2 }} spacing="sm">
                    <Text size="sm">状态：{translationTestResult.translation_status}</Text>
                    <Text size="sm">引擎：{translationTestResult.translation_engine || "-"}</Text>
                    <Text size="sm">源语言：{translationTestResult.source_language || "auto"}</Text>
                    <Text size="sm">目标语言：{translationTestResult.target_language || "auto"}</Text>
                  </SimpleGrid>
                  {translationTestResult.translated_content ? (
                    <>
                      <Divider my="sm" />
                      <Text size="sm" fw={700} mb={4}>译文</Text>
                      <Text className="message-content">{translationTestResult.translated_content}</Text>
                    </>
                  ) : null}
                  {translationTestResult.desc ? <Text size="xs" c="dimmed" mt="sm">{translationTestResult.desc}</Text> : null}
                </Paper>
              ) : null}
              <Alert color="blue" icon={<IconMessageSearch size={16} />}>保存设置只负责持久化；测试按钮会使用当前表单配置直接请求翻译服务。</Alert>
            </Stack>
          </Card>

          <Card withBorder radius="md" p="lg">
            <Title order={4} mb="md">图片 OCR 与媒体索引</Title>
            <SimpleGrid cols={{ base: 1, md: 2 }}>
              <Switch label="启用图片 OCR" checked={Boolean(smartConfig.ocr?.enabled)} onChange={(event) => updateSmartConfig("ocr.enabled", event.currentTarget.checked)} />
              <Select label="OCR 引擎" value={smartConfig.ocr?.engine || "paddleocr"} onChange={(value) => updateSmartConfig("ocr.engine", value || "paddleocr")} data={[{ value: "paddleocr", label: "PaddleOCR" }, { value: "easyocr", label: "EasyOCR" }]} />
              <NumberInput label="最大图片大小 MB" min={1} max={50} value={smartConfig.ocr?.max_image_mb || 5} onChange={(value) => updateSmartConfig("ocr.max_image_mb", value || 5)} />
              <Switch label="OCR 后删除临时图片" checked={Boolean(smartConfig.ocr?.delete_after_ocr)} onChange={(event) => updateSmartConfig("ocr.delete_after_ocr", event.currentTarget.checked)} />
              <Switch label="OCR 文本参与检索" checked={Boolean(smartConfig.ocr?.include_in_search)} onChange={(event) => updateSmartConfig("ocr.include_in_search", event.currentTarget.checked)} />
              <Switch label="OCR 文本参与规则匹配" checked={Boolean(smartConfig.ocr?.include_in_rules)} onChange={(event) => updateSmartConfig("ocr.include_in_rules", event.currentTarget.checked)} />
            </SimpleGrid>
          </Card>

          <Group justify="flex-end">
            <Button onClick={saveSmartConfig}>保存智能增强设置</Button>
          </Group>
        </Stack>
      </Tabs.Panel>

      <Tabs.Panel value="about">
        <Card withBorder radius="md" p="lg">
          <Group gap="sm" mb="md">
            <ThemeIcon color="cyan" variant="light" size={42} radius="md"><IconBrandTelegram size={22} /></ThemeIcon>
            <Stack gap={2}>
              <Title order={3}>WatchOut Telegram</Title>
              <Text c="dimmed" size="sm">Telegram 消息采集、检索、规则命中和通知转发平台。</Text>
            </Stack>
          </Group>
          <SimpleGrid cols={{ base: 1, md: 3 }}>
            <Paper withBorder radius="md" p="md"><Text size="xs" c="dimmed">后端</Text><Text fw={800}>FastAPI / Telethon</Text></Paper>
            <Paper withBorder radius="md" p="md"><Text size="xs" c="dimmed">前端</Text><Text fw={800}>React / Mantine</Text></Paper>
            <Paper withBorder radius="md" p="md"><Text size="xs" c="dimmed">主数据库</Text><Text fw={800}>{database.engine || "postgresql"}</Text></Paper>
          </SimpleGrid>
        </Card>
      </Tabs.Panel>
    </Tabs>
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

function serializeMessageFilterValue(key, value) {
  if ((key === "date_from" || key === "date_to") && value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toISOString();
  }
  return value;
}

function appendMessageFilters(params, filters, { includeLimit = true } = {}) {
  Object.entries(filters).forEach(([key, value]) => {
    if (!includeLimit && key === "limit") return;
    if (value === "" || value === null || value === undefined) return;
    params.set(key, serializeMessageFilterValue(key, value));
  });
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
  limit: 50
};

function MainApp() {
  const [authed, setAuthed] = useState(Boolean(getToken()));
  const [activeTab, setActiveTab] = useState(tabFromHash);
  const [collapsed, setCollapsed] = useState(false);
  const [uiPrefs, setUiPrefs] = useState(loadUiPrefs);
  const [data, setData] = useState({ accounts: [], targets: [], rules: [], messages: [], hits: [], notifications: [], runs: [], sinks: [], storageOverview: {}, systemDatabase: {}, intelligenceConfig: {}, collectionConfig: {}, intelligence: {}, dashboard: {}, dashboardTrends: {}, dashboardOverview: {} });
  const [messageFilters, setMessageFilters] = useState(() => ({ ...defaultMessageFilters, limit: Number(loadUiPrefs().pageSize) || 50 }));
  const [messageTotal, setMessageTotal] = useState(0);
  const [messagePage, setMessagePage] = useState(1);
  const [matchRuleFilter, setMatchRuleFilter] = useState("");
  const [error, setError] = useState("");

  const current = useMemo(() => navItems.find((item) => item.id === activeTab) || navItems[0], [activeTab]);

  function changeTab(tab) {
    if (!navIds.has(tab)) return;
    setActiveTab(tab);
    setTabHash(tab);
  }

  function messageQuery(filters = messageFilters, page = messagePage) {
    const params = new URLSearchParams();
    appendMessageFilters(params, filters);
    const limit = Number(filters.limit) || 100;
    params.set("limit", String(limit));
    params.set("offset", String(Math.max(0, page - 1) * limit));
    return params.toString();
  }

  function updateGlobalUiPrefs(nextPrefs) {
    const normalized = saveUiPrefs(nextPrefs);
    setUiPrefs(normalized);
  }

  function messageCountQuery(filters = messageFilters) {
    const params = new URLSearchParams();
    appendMessageFilters(params, filters, { includeLimit: false });
    return params.toString();
  }

  async function load(filters = messageFilters, page = messagePage) {
    if (!getToken()) return;
    setError("");
    const optionalErrors = [];
    const optional = (request, fallback) => request.catch((error) => {
      optionalErrors.push(error.message || String(error));
      return fallback;
    });
    try {
      const [dashboard, dashboardOverview, dashboardTrends, accounts, targets, rules, messages, messageCount, hits, notificationChannels, runs, sinks, storageOverview, systemDatabase, intelligenceConfig, collectionConfig, tgLinks] = await Promise.all([
        api("/dashboard"),
        optional(api("/dashboard/overview"), {}),
        optional(api("/dashboard/trends"), {}),
        api("/telegram/accounts"),
        api("/targets"),
        api("/rules"),
        api(`/messages?${messageQuery(filters, page)}`),
        api(`/messages/count?${messageCountQuery(filters)}`),
        api("/hits"),
        api("/notifications"),
        api("/runs"),
        api("/storage/sinks"),
        api("/storage/overview"),
        optional(api("/system/database/config"), {}),
        optional(api("/system/intelligence/config"), {}),
        optional(api("/system/collection/config"), {}),
        optional(api("/intelligence/tg-links"), [])
      ]);
      setData({
        dashboard,
        dashboardOverview,
        dashboardTrends,
        accounts,
        targets,
        rules,
        messages,
        hits,
        notifications: notificationChannels,
        runs,
        sinks,
        storageOverview,
        systemDatabase,
        intelligenceConfig,
        collectionConfig,
        intelligence: { links: tgLinks }
      });
      setMessageTotal(messageCount.total || 0);
      if (optionalErrors.length) {
        setError(`部分接口异常：${optionalErrors.slice(0, 3).join("；")}`);
      }
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
    changeTab("messages");
    load(nextFilters);
  }

  function openMatchesForRule(rule) {
    setMatchRuleFilter(rule?.id ? String(rule.id) : "");
    changeTab("matches");
  }

  useEffect(() => { if (authed) load(); }, [authed]);

  useEffect(() => {
    document.documentElement.dataset.themePref = uiPrefs.colorScheme || "light";
  }, [uiPrefs.colorScheme]);

  useEffect(() => {
    function syncTabFromHash() {
      setActiveTab(tabFromHash());
    }
    window.addEventListener("hashchange", syncTabFromHash);
    return () => window.removeEventListener("hashchange", syncTabFromHash);
  }, []);

  if (!authed) return <Login onDone={() => setAuthed(true)} />;

  return (
    <AppShell navbar={{ width: collapsed ? 72 : 236, breakpoint: "sm" }} padding="md">
      <AppShell.Navbar className="nav" p="sm">
        <Group mb="md" gap="xs" justify={collapsed ? "center" : "space-between"}>
          <UnstyledButton className="nav-brand" onClick={() => changeTab("dashboard")} aria-label="返回首页">
            <Box className="nav-brand-icon">
              <img src="/tg.png" alt="WatchOut" />
            </Box>
            {!collapsed ? (
              <Stack gap={0}>
                <Text fw={900} c="white" className="nav-brand-title">WatchOut</Text>
                <Text size="xs" c="cyan.1" className="nav-brand-subtitle">TG 监控</Text>
              </Stack>
            ) : null}
          </UnstyledButton>
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
          <Stack gap={3}>
            {navItems.map((item) => {
              const Icon = item.icon;
              const link = (
                <NavLink
                  key={item.id}
                  active={activeTab === item.id}
                  label={collapsed ? null : item.label}
                  leftSection={<Icon size={18} />}
                  onClick={() => changeTab(item.id)}
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
          px={collapsed ? 0 : "sm"}
        >
          {collapsed ? null : "退出"}
        </Button>
      </AppShell.Navbar>

      <AppShell.Main className="main">
        <Container size="xl" py="lg">
          <Group justify="space-between" mb="xl" align="flex-start" className="page-header">
            <Stack gap={4}>
              <Title order={1}>{current.label}</Title>
              <Text c="dimmed" size="sm">更新于刚刚</Text>
            </Stack>
            <Group>
              <Burger opened={!collapsed} onClick={() => setCollapsed((value) => !value)} hiddenFrom="sm" />
              <ActionIcon size="lg" variant="light" color="cyan" onClick={() => load()}>
                <IconRefresh size={18} />
              </ActionIcon>
            </Group>
          </Group>
          {error ? <Alert color="red" icon={<IconAlertTriangle size={16} />} mb="md" withCloseButton onClose={() => setError("")}>{error}</Alert> : null}
          {activeTab === "dashboard" && <Dashboard data={data} setActiveTab={changeTab} accounts={data.accounts} targets={data.targets} openMessagesForTarget={openMessagesForTarget} setMessageFilters={setMessageFilters} />}
          {activeTab === "messages" && <Messages messages={data.messages} targets={data.targets} reload={load} filters={messageFilters} setFilters={setMessageFilters} total={messageTotal} page={messagePage} setPage={setMessagePage} defaultPageSize={uiPrefs.pageSize} />}
          {activeTab === "accounts" && <Accounts accounts={data.accounts} reload={load} collectionConfig={data.collectionConfig} />}
          {activeTab === "targets" && <Targets targets={data.targets} accounts={data.accounts} reload={load} openMessages={openMessagesForTarget} defaultPageSize={uiPrefs.pageSize} />}
          {activeTab === "runs" && <Runs initialRuns={data.runs} targets={data.targets} accounts={data.accounts} defaultPageSize={uiPrefs.pageSize} />}
          {activeTab === "rules" && <Rules rules={data.rules} channels={data.notifications} reload={load} openMatchesForRule={openMatchesForRule} />}
          {activeTab === "matches" && <Matches hits={data.hits} initialRuleId={matchRuleFilter} rules={data.rules} reload={load} defaultPageSize={uiPrefs.pageSize} />}
          {activeTab === "notifications" && <NotificationsPanel channels={data.notifications} reload={load} />}
          {activeTab === "settings" && <SettingsPanel sinks={data.sinks} storageOverview={data.storageOverview} systemDatabase={data.systemDatabase} intelligenceConfig={data.intelligenceConfig} collectionConfig={data.collectionConfig} uiPrefs={uiPrefs} onUiPrefsChange={updateGlobalUiPrefs} reload={load} />}
        </Container>
      </AppShell.Main>
    </AppShell>
  );
}

function AppRoot() {
  const [uiPrefs, setUiPrefs] = useState(loadUiPrefs);
  const effectiveMantineScheme = uiPrefs.colorScheme === "auto"
    ? undefined
    : ["dark", "midnight"].includes(uiPrefs.colorScheme)
      ? "dark"
      : "light";
  const theme = useMemo(() => ({
    primaryColor: "cyan",
    defaultRadius: "md",
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
  }), []);

  useEffect(() => {
    function handleUiPrefsChanged(event) {
      if (event.detail) setUiPrefs(event.detail);
    }
    window.addEventListener("watchout-ui-prefs", handleUiPrefsChanged);
    return () => window.removeEventListener("watchout-ui-prefs", handleUiPrefsChanged);
  }, []);

  return (
    <MantineProvider defaultColorScheme={["dark", "midnight"].includes(uiPrefs.colorScheme) ? "dark" : "light"} forceColorScheme={effectiveMantineScheme} theme={theme}>
      <Notifications position="top-right" />
      <MainApp />
    </MantineProvider>
  );
}

createRoot(document.getElementById("root")).render(<AppRoot />);
