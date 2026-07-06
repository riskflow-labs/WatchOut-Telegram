export const API_BASE = import.meta.env.VITE_API_BASE || `${window.location.protocol}//${window.location.hostname}:8000/api`;

export function getToken() {
  return localStorage.getItem("watchout_telegram_token") || "";
}

export function setToken(token) {
  localStorage.setItem("watchout_telegram_token", token);
}

export function clearToken() {
  localStorage.removeItem("watchout_telegram_token");
}

export async function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {})
  };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const method = options.method || "GET";
  const url = `${API_BASE}${path}`;
  let response;
  try {
    response = await fetch(url, {
      ...options,
      headers,
      body: options.body ? JSON.stringify(options.body) : undefined
    });
  } catch (err) {
    const error = new Error(`${method.toUpperCase()} ${path} -> 网络连接失败：后端未响应、请求超时或连接被中断（${err.message || "Failed to fetch"}）`);
    error.path = path;
    error.method = method.toUpperCase();
    error.detail = err.message || "Failed to fetch";
    throw error;
  }
  const text = await response.text();
  let payload = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = text ? { detail: text } : null;
  }
  if (!response.ok) {
    const detail = formatApiDetail(payload?.detail || payload?.error || response.statusText || "request failed");
    const error = new Error(`${method.toUpperCase()} ${path} -> ${response.status} ${detail}`);
    error.status = response.status;
    error.path = path;
    error.method = method.toUpperCase();
    error.detail = detail;
    throw error;
  }
  return payload;
}

function formatApiDetail(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const location = Array.isArray(item?.loc) ? item.loc.join(".") : "";
        const message = item?.msg || JSON.stringify(item);
        return location ? `${location}: ${message}` : message;
      })
      .join("; ");
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return String(detail || "request failed");
}

export async function login(username, password) {
  const payload = await api("/auth/login", { method: "POST", body: { username, password } });
  setToken(payload.access_token);
  return payload;
}
