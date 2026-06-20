/**
 * QuantYield API client
 *
 * Thin fetch wrapper that:
 * - Reads the base URL from the VITE_API_BASE env variable (injected at build
 *   time by Vite, defaults to /api/v1 so it works through the nginx proxy).
 * - Attaches the JWT access token stored in localStorage on every request.
 * - Returns parsed JSON on success, throws a structured ApiError on failure.
 *
 * Usage:
 *   import api from "@/lib/apiClient";
 *   const bonds = await api.get("/bonds/");
 *   const bond  = await api.post("/bonds/", { coupon_rate: 0.05, ... });
 */

const BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

export class ApiError extends Error {
  constructor(status, data) {
    super(data?.detail ?? data?.message ?? `HTTP ${status}`);
    this.status = status;
    this.data = data;
  }
}

function getToken() {
  try {
    const stored = localStorage.getItem("qy_tokens");
    return stored ? JSON.parse(stored).access : null;
  } catch {
    return null;
  }
}

async function request(method, path, body) {
  const token = getToken();
  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  let data;
  try {
    data = await res.json();
  } catch {
    data = null;
  }

  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}

const api = {
  get: (path) => request("GET", path),
  post: (path, body) => request("POST", path, body),
  put: (path, body) => request("PUT", path, body),
  patch: (path, body) => request("PATCH", path, body),
  delete: (path) => request("DELETE", path),
};

export default api;
