const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000/api";

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
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(payload?.detail || payload?.error || "request failed");
  }
  return payload;
}

export async function login(username, password) {
  const payload = await api("/auth/login", { method: "POST", body: { username, password } });
  setToken(payload.access_token);
  return payload;
}
