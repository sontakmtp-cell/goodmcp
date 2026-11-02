import { ApiError } from "./api";
export type WebUser = { id: string; email: string; name?: string; platform_admin: boolean; email_verified: boolean; google_linked?: boolean };
export type WebWorkspace = { id: string; name: string; role: string; archived_at?: string | null };
export type WebSession = { user: WebUser; csrf: string; workspaces: WebWorkspace[]; workspace_id: string | null; google_enabled: boolean };
// Browser credentials are a CSRF value; the session itself is an HttpOnly cookie.
export type Credential = { csrf?: string; admin?: boolean; access_token?: string; client_id?: string };
export async function webRequest<T = any>(path: string, csrf = "", init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (typeof init.body === "string") headers.set("Content-Type", "application/json");
  if (!/^(GET|HEAD)$/i.test(init.method || "GET")) headers.set("X-CSRF-Token", csrf);
  let response: Response;
  try { response = await fetch("/auth/web" + path, { ...init, headers, credentials: "same-origin", cache: "no-store", signal: init.signal || AbortSignal.timeout(20000) }); }
  catch { throw new ApiError(0); }
  if (!response.ok) throw new ApiError(response.status, response.headers.get("x-request-id") || "");
  return (await response.json()).data;
}
export async function loadSession(): Promise<WebSession> { return webRequest<WebSession>("/session"); }
export async function signIn(_admin = false) { location.assign("/auth/google/start?" + new URLSearchParams({return_to: location.pathname.startsWith("/app") || location.pathname.startsWith("/admin") || location.pathname.startsWith("/platform") ? location.pathname + location.search : "/app"})); }
export async function revoke(credential: Credential, allDevices = false) {
  await webRequest("/logout", credential.csrf || "", { method: "POST", body: JSON.stringify({ all_devices: allDevices }) });
}
