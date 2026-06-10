const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

let accessToken: string | null = null;
let refreshToken: string | null = null;
let onAuthFailure: (() => void) | null = null;

export function setTokens(access: string, refresh: string) {
  accessToken = access;
  refreshToken = refresh;
  if (typeof window !== "undefined") {
    sessionStorage.setItem("access_token", access);
    sessionStorage.setItem("refresh_token", refresh);
    // session cookie — 关闭所有页面后自动清除，匹配 sessionStorage 生命周期
    document.cookie = "eva_auth=1; path=/; SameSite=Lax";
  }
}

export function clearTokens() {
  accessToken = null;
  refreshToken = null;
  if (typeof window !== "undefined") {
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem("refresh_token");
    document.cookie = "eva_auth=; path=/; max-age=0";
  }
}

export function loadTokens() {
  if (typeof window !== "undefined") {
    accessToken = sessionStorage.getItem("access_token");
    refreshToken = sessionStorage.getItem("refresh_token");
  }
}

export function getAccessToken() {
  return accessToken;
}

export function onAuthFailureHandler(handler: () => void) {
  onAuthFailure = handler;
}

loadTokens();

async function refreshAccessToken(): Promise<boolean> {
  if (!refreshToken) return false;
  try {
    const res = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    setTokens(data.access_token, data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

export async function api<T = unknown>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (accessToken) {
    headers["Authorization"] = `Bearer ${accessToken}`;
  }

  let res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401 && refreshToken) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      headers["Authorization"] = `Bearer ${accessToken}`;
      res = await fetch(`${API_BASE}${path}`, { ...options, headers });
    } else {
      clearTokens();
      onAuthFailure?.();
      throw new Error("认证已过期，请重新登录");
    }
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

export async function apiSSE(
  path: string,
  body: unknown,
  onEvent: (event: Record<string, unknown>) => void,
  onDone: () => void,
  onError: (err: Error) => void
): Promise<AbortController> {
  const controller = new AbortController();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => null);
      onError(new Error(errData?.detail || `HTTP ${res.status}`));
      return controller;
    }

    const reader = res.body?.getReader();
    if (!reader) {
      onError(new Error("响应体不可读"));
      return controller;
    }

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const data = JSON.parse(line.slice(6));
            if (data.type === "done") {
              onDone();
              return controller;
            }
            onEvent(data);
          } catch {
            // skip unparseable lines
          }
        }
      }
    }
    onDone();
  } catch (err) {
    if ((err as Error).name !== "AbortError") {
      onError(err as Error);
    }
  }

  return controller;
}
