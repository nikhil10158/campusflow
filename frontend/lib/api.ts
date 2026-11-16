import { useAuth } from "./store";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  data: Record<string, unknown>;

  constructor(status: number, message: string, data: Record<string, unknown>) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

type Params = Record<string, string | number | boolean | null | undefined>;

interface Options {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  params?: Params;
  form?: FormData;
}

export function buildUrl(path: string, params?: Params): string {
  const url = new URL(path, API_URL);
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
  });
  return url.toString();
}

export async function api<T>(path: string, options: Options = {}): Promise<T> {
  const token = useAuth.getState().token;
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(buildUrl(path, options.params), {
    method: options.method ?? (options.body !== undefined || options.form ? "POST" : "GET"),
    headers,
    body: options.form ?? (options.body !== undefined ? JSON.stringify(options.body) : undefined),
  }).catch(() => {
    throw new ApiError(0, `Cannot reach the planner service at ${API_URL}. Start the backend (run.ps1) and try again.`, {});
  });
  if (response.status === 401 && token) {
    useAuth.getState().logout();
  }
  const text = await response.text();
  const data = text ? safeJson(text) : {};
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : response.statusText;
    throw new ApiError(response.status, detail, data);
  }
  return data as T;
}

function safeJson(text: string): Record<string, unknown> {
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

export async function download(path: string, filename: string, params?: Params): Promise<void> {
  const token = useAuth.getState().token;
  const response = await fetch(buildUrl(path, params), { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!response.ok) throw new ApiError(response.status, "Download failed", {});
  const blob = await response.blob();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}
