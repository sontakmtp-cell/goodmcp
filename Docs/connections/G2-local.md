# Kết nối OAuth/MCP — G2 local

Đây là cấu hình local đang triển khai. Các domain production trong PLAN chưa được
deploy; không dùng localhost làm URL connector chạy trên máy chủ cloud.

## 1. Các địa chỉ

Mặc định `HUB_PUBLIC_BASE_URL=http://127.0.0.1:18080`:

| Mục | URL |
|---|---|
| MCP Streamable HTTP | `http://127.0.0.1:18080/mcp` |
| Issuer | `http://127.0.0.1:18080/auth` |
| AS discovery | `http://127.0.0.1:18080/.well-known/oauth-authorization-server/auth` |
| Discovery alias | `http://127.0.0.1:18080/auth/.well-known/oauth-authorization-server` |
| Protected-resource discovery | `http://127.0.0.1:18080/.well-known/oauth-protected-resource/mcp` |
| Login / account / logout | `/auth/login`, `/auth/account`, POST `/auth/logout` |
| Authorize / token / revoke | `/auth/authorize`, `/auth/token`, `/auth/revoke` |
| Dynamic client registration | `/auth/register` |

MCP SDK chính thức **2.3.0**, protocol pin **2026-07-28**. Không có stdio backend,
legacy initialize/SSE hoặc tự downgrade trong G2. MCP GET/DELETE bị từ chối;
modern request-scoped response vẫn do SDK xử lý. Tool duy nhất:
`hub_get_workspace(workspace_id: UUID string)` → workspace_id/name/role, readonly.
Không có calculator, corpus, plugin runner hoặc công cụ ghi dữ liệu ở G2.

## 2. Thử từ máy local

Khởi động/cập nhật (không xóa volume):

```powershell
python scripts/local.py up
uv run python scripts/connect-local.py
```

Lệnh thứ hai mở trình duyệt đăng nhập và xin **hub:read** cho một workspace. Owner
email mặc định `owner@local.invalid`; password bootstrap ở `.local/secrets/owner_password`
trên máy chủ local, không nằm trong tài liệu/Git/chat. Nếu đã bootstrap email khác,
dùng email đó. Chưa có UI đổi password/reset/TOTP; các gate trước production được
ghi ở G2.md.

CLI lắng nghe callback `http://127.0.0.1:8766/callback`, kiểm state/iss/PKCE, gọi
tool đọc qua SDK rồi **thu hồi grant tạm khi xong**. Không in/lưu token. Cần port
8766 trống; nếu từ chối cấp quyền hoặc không callback trong 5 phút thì dừng.
Không gửi password cho CLI, không gọi API model trả phí.

Client cần hỗ trợ URL/OAuth có thể dùng [mcp-url.json](../../configs/connections/mcp-url.json).
Cú pháp thuộc từng host có thể khác; file này không phải bằng chứng host cụ thể
đã kết nối được. [local-sdk.json](../../configs/connections/local-sdk.json) dùng
cho evaluator/SDK adapter của repo: Authorization lấy từ biến `GOODMCP_BEARER`
(cả chuỗi `Bearer ...`), không điền token vào JSON hoặc Git. Ưu tiên CLI tương tác
để khỏi quản lý token thủ công.

Nếu đổi port, đặt **cả** `HUB_PORT` và `HUB_PUBLIC_BASE_URL` nhất quán trước `up`;
issuer/resource của grant cũ không tự chuyển sang địa chỉ mới. G2 dùng cùng một
origin cho `/auth` và `/mcp`; nhiều subdomain/TLS routing của PLAN thuộc G8.

## 3. Client registration và consent

- DCR nhận public client (`token_endpoint_auth_method=none`), code/refresh, 1–10
  exact redirect URI và scope hợp lệ. HTTPS bắt buộc; HTTP chỉ cho loopback khi
  server bật chế độ local. Không có wildcard/prefix redirect match.
- Client ID metadata document (CIMD) dùng HTTPS URL công khai trên 443, không query/
  fragment/credentials. Fetch giới hạn 64 KiB, TLS kiểm hostname, pin IP sau DNS,
  chặn mọi private/link-local/reserved address và redirect. URL/logo khác trong
  document không được fetch. Cache 1 giờ; không fetch client lạ tại token endpoint
  nếu chưa có credential còn hiệu lực gắn đúng client.
- Public registration có rate limit và tổng 500 clients; không tạo user/workspace
  hay cấp quyền dữ liệu. Đăng nhập + consent rõ client/scope/workspace vẫn bắt buộc.
- Có [operator-client.json](../../configs/connections/operator-client.json) cho
  pre-registration qua operator CLI `goodmcp.auth_admin register --file <JSON>`;
  file cần mount read-only vào service admin nếu chạy trong Compose. Không có
  public route sửa client registration hoặc cài plugin.

Scope được khai báo: `hub:read`, `tools:run`, `projects:read`, `projects:write`.
G2 chỉ sử dụng `hub:read` cho tool đọc; các scope khác chưa có runtime nghiệp vụ.
Scope thêm cần consent mới; refresh chỉ giữ hoặc giảm scope đã cấp. Viewer không
được cấp tools:run/projects:write. Token gắn một user/workspace/client/issuer/resource.
`X-Workspace-ID` nếu có chỉ là lựa chọn phải trùng grant; không phải danh tính.
Danh tính không lấy từ X-User-ID hoặc model/clientInfo.

## 4. Thời hạn, refresh, revoke và secret

Access 5 phút; refresh 7 ngày; code 120 giây; phiên browser 30 phút. DB lưu hash
của opaque access/refresh/code/session/CSRF, không lưu các giá trị plaintext đó.
Password mới là Argon2id; owner G1 dùng scrypt được nâng cấp **sau login thành công**,
không yêu cầu đặt lại mật khẩu. Auth service có role riêng, không owner/superuser/
BYPASSRLS; API/worker không được mount auth/admin secret hoặc tạo token bằng SQL.

POST `/auth/token` refresh phải gửi grant_type=refresh_token, client_id,
refresh_token và resource đúng. Mỗi lượt trả refresh mới; refresh cũ dùng lại sẽ
thu hồi **toàn family**, gồm access/refresh con. Không retry mù refresh sau mất
response; nếu bị từ chối phải đăng nhập/cấp quyền lại. Code cũng chỉ đổi một lần,
replay có thể làm mất quyền cả family đã cấp.

POST `/auth/revoke` với client_id + access/refresh token của client đó thu hồi
toàn grant/family; token lạ trả 200 để tránh dò tìm. Thu hồi được kiểm trên từng
request, không có token cache trì hoãn. Logout xóa session browser; grant OAuth
đã cấp vẫn cần revoke riêng.

Cookie HttpOnly/SameSite=Lax, CSRF trên login/consent/logout. HTTPS mode có Secure;
HTTP loopback là ngoại lệ local được cấu hình rõ. Login và DCR có throttle DB;
peer là kết nối tới issuer (qua Caddy có thể dùng chung một proxy IP), chưa làm
trusted forwarded-IP mapping cho nhiều người. TOTP/recovery trước production
vẫn là gate G8, chưa công bố triển khai Internet an toàn chỉ bằng đổi URL.

## 5. Kiểm tra và cloud

```powershell
./scripts/verify.ps1 -Stage G2
```

POSIX: `scripts/verify.sh G2`. Cùng gọi launcher Python; checkout sạch cần source
G2 đã commit. Bộ kiểm chạy DB, auth, API, Caddy và client thật trong Compose;
fixtures/credential test ở volume riêng và bị dọn sau pass.

Wire test dùng `http://localhost:8080` **bên trong network namespace Caddy của
project test**, không phải cấu hình localhost:18080 giao cho người dùng. Không dùng
ASGI TestClient hoặc Client(server) trong memory để thay bằng chứng HTTP.

ChatGPT/Claude/Gemini/Grok cloud: **chưa live-test** trong G2 local. Chưa có endpoint
HTTPS public được phép triển khai và kết nối host thật cho lượt này; không tự mở
tunnel/đổi DNS để thay đổi phạm vi. Endpoint localhost không truy cập được từ
cloud. G2.md tách kết quả protocol local khỏi gate host cloud ở G2/G7/G8.
