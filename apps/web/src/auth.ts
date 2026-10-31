import { ApiError } from "./api";
export const scopes =
  "hub:read hub:write tools:run projects:read projects:write";
const issuer =
  import.meta.env.VITE_OAUTH_ISSUER || "http://127.0.0.1:18080/auth";
const resource = issuer.replace(/\/auth$/, "") + "/mcp";
const base64url = (bytes: Uint8Array) =>
  btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
async function oauth(path: string, init: RequestInit) {
  let r: Response;
  try {
    r = await fetch(path, {
      ...init,
      cache: "no-store",
      signal: AbortSignal.timeout(20000),
    });
  } catch {
    throw new ApiError(0);
  }
  if (!r.ok) throw new ApiError(r.status);
  return r;
}
export async function signIn(admin = false) {
  const redirect_uri = location.origin + "/oauth/callback";
  const cacheKey = "goodmcp:public-client:" + issuer + ":" + redirect_uri;
  let client_id = localStorage.getItem(cacheKey);
  if (!client_id) {
    const client = await (
      await oauth("/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_name: "GoodMCP Web",
          redirect_uris: [redirect_uri],
          token_endpoint_auth_method: "none",
          grant_types: ["authorization_code", "refresh_token"],
          response_types: ["code"],
          scope: scopes,
        }),
      })
    ).json();
    client_id = client.client_id;
    if (typeof client_id !== "string")
      throw new Error("Chưa đăng ký được ứng dụng web.");
    localStorage.setItem(cacheKey, client_id);
  }
  const verifier = base64url(crypto.getRandomValues(new Uint8Array(32))),
    state = base64url(crypto.getRandomValues(new Uint8Array(32)));
  const challenge = base64url(
    new Uint8Array(
      await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)),
    ),
  );
  sessionStorage.setItem(
    "goodmcp:oauth",
    JSON.stringify({
      verifier,
      state,
      client_id,
      redirect_uri,
      admin,
      created: Date.now(),
    }),
  );
  location.assign(
    "/auth/authorize?" +
      new URLSearchParams({
        client_id,
        redirect_uri,
        response_type: "code",
        scope: admin ? scopes : "hub:read projects:read",
        state,
        code_challenge: challenge,
        code_challenge_method: "S256",
        resource,
      }),
  );
}
export type Credential = {
  access_token: string;
  client_id: string;
  admin: boolean;
};
export async function completeSignIn(): Promise<Credential> {
  const raw = sessionStorage.getItem("goodmcp:oauth");
  sessionStorage.removeItem("goodmcp:oauth");
  const params = new URLSearchParams(location.search);
  history.replaceState(null, "", "/");
  let p;
  try {
    p = JSON.parse(raw || "null");
  } catch {
    throw new Error("Thông tin đăng nhập không hợp lệ. Hãy bắt đầu lại.");
  }
  if (
    !p ||
    params.get("state") !== p.state ||
    params.get("iss") !== issuer ||
    Date.now() - p.created > 600000 ||
    params.has("error") ||
    !params.get("code")
  )
    throw new Error("Đăng nhập bị từ chối hoặc đã hết hạn. Hãy bắt đầu lại.");
  const token = await (
    await oauth("/auth/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        code: params.get("code")!,
        code_verifier: p.verifier,
        client_id: p.client_id,
        redirect_uri: p.redirect_uri,
        resource,
      }),
    })
  ).json();
  // No access or refresh credential is persisted in web storage.
  if (typeof token.access_token !== "string")
    throw new Error("Máy chủ chưa trả phiên đăng nhập hợp lệ.");
  return {
    access_token: token.access_token,
    client_id: p.client_id,
    admin: p.admin,
  };
}
export async function revoke(credential: Credential) {
  await oauth("/auth/revoke", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      token: credential.access_token,
      token_type_hint: "access_token",
      client_id: credential.client_id,
    }),
  });
  // A 200 alone does not prove that an existing session lost access.
  let probe: Response;
  try {
    probe = await fetch(
      "/api/v1/me/workspaces?revoke_check=" + crypto.randomUUID(),
      {
        headers: { Authorization: "Bearer " + credential.access_token },
        cache: "no-store",
        signal: AbortSignal.timeout(10000),
      },
    );
  } catch {
    throw new Error(
      "Đã gửi yêu cầu nhưng chưa kiểm tra được việc thu hồi. Hãy thử lại.",
    );
  }
  if (probe.status !== 401)
    throw new Error(
      "Máy chủ chưa xác nhận thu hồi: phiên vẫn còn quyền hoặc dịch vụ chưa sẵn sàng. Không thể báo đã thu hồi.",
    );
}
