# G9 — Danh tính, phiên web, API và quyền

Ngày 01/11/2026. Phạm vi theo [PLAN-phase-2](../PLAN-phase-2.md).

## Danh tính và đường đăng nhập

Google OIDC trực tiếp dùng code flow + PKCE S256, state ký gắn với cookie, nonce,
RS256/JWKS, issuer/audience/expiry và email đã xác minh. Chỉ xin `openid email profile`.
Flow lưu trong database và tiêu thụ trước token exchange; lỗi mạng phải bắt đầu lại.
Danh tính là `(provider, subject)`, không tự ghép tài khoản theo email. Hai subject
có cùng email vẫn là hai tài khoản. Lần cấp mới tạo user + workspace + owner trong
một giao dịch; khóa theo subject chống tạo đôi khi đồng thời.

`GET /auth/google/start?return_to=/app/...` bắt đầu đăng nhập.
Callback chính xác: `https://goodmcp.si/auth/google/callback`.
Chỉ cho return path nội bộ đã cho phép. Không nhận endpoint Google từ trình duyệt.
OAuth authorize chưa có phiên chuyển sang Google khi Google được bật; CF chỉ giữ
ở đường đăng nhập khôi phục trực tiếp. Thành viên mới không cần tài khoản Cloudflare.

Chủ cũ đăng nhập Cloudflare qua `/auth/login?return_to=/app/account`, sau đó dùng
**Liên kết Google với tài khoản này**. Liên kết cần phiên chủ + CSRF; không dựa vào
email. Giữ địa chỉ đăng nhập khôi phục của chủ khi Google khác địa chỉ đó. Phiên
chỉ được coi đã chứng minh email tài khoản khi Google thực sự xác minh đúng địa chỉ.

Cookie `hub_session` phía server: HttpOnly, SameSite=Lax, Secure trên HTTPS, path `/`,
TTL 30 phút. Khi cấp cookie mới dọn cookie path `/auth` cũ. Database chỉ giữ hash
cookie. Browser giữ CSRF trong bộ nhớ, không lưu bearer token trong localStorage.
localStorage chỉ còn metadata tiếp tục upload, không phải credential đăng nhập.

## Tách web và MCP

API web gửi cookie, yêu cầu ghi có Origin đúng và `X-CSRF-Token`. API gọi dịch vụ
auth nội bộ `/internal/web-session`, dùng secret riêng `web_session_key`; không
nhận secret auth database. Caddy không chuyển đường internal này ra Internet.
Mọi lần xác minh đều kiểm user active và membership hiện tại.

MCP luôn cần bearer token riêng. Cookie web không cấp quyền MCP. Danh sách workspace
của phiên web là đầy đủ; bearer token chỉ trả workspace đã được cấp. Bộ chọn web
không đổi workspace của grant MCP. Client phải xin grant mới nếu muốn workspace khác.

## API phiên và quản lý

API quản lý dùng phiên web, prefix `/auth/web`; bearer MCP không thay cho phiên này.
API nghiệp vụ giữ `/api/v1/workspaces/{workspace_id}`. Kết quả thành công có `data`,
lỗi có mã và thông báo. Không trả raw invitation token trong API quản trị.

| Nhóm | Đường và hành động |
|---|---|
| Phiên | GET `/session`, GET `/config`, POST `/select-workspace`, POST `/logout` (`all_devices`) |
| Liên kết | POST `/google/link` trả URL Google, cần phiên + CSRF |
| Workspace | GET/POST `/workspaces`, PATCH `/workspaces/{ws}`, POST `/{ws}/archive`, `/{ws}/leave`, `/{ws}/transfer` |
| Thành viên | GET `/workspaces/{ws}/members`, PATCH/DELETE `/{ws}/members/{user}` |
| Lời mời | GET/POST `/workspaces/{ws}/invitations`, DELETE `/{ws}/invitations/{id}`, POST `/invitations/accept` |
| Kết nối | GET `/connections`, DELETE `/connections/{grant}`, GET `/workspaces/{ws}/connections`, DELETE `/{ws}/connections/{grant}` |
| Nhật ký | GET `/workspaces/{ws}/audit` |
| Nền tảng | GET `/platform/users`, PATCH `/platform/users/{user}`, GET `/platform/workspaces` |

## Ma trận quyền

| Hành động | Owner | Admin | Member | Viewer |
|---|---|---|---|---|
| Đọc plugin/dự án trong workspace | Có | Có | Có | Có |
| Chạy công cụ, tạo/cập nhật dự án | Có | Có | Có | Không |
| Nhập/bật/tắt plugin, quản lý job | Có | Có | Không | Không |
| Mời/quản lý member/viewer | Có | Có | Không | Không |
| Quản lý admin/chuyển owner/lưu trữ | Có | Không | Không | Không |
| Xem nhật ký workspace | Có | Có | Không | Không |
| Thu hồi kết nối của mình | Có | Có | Có | Có |
| Thu hồi kết nối người khác | Có | Có | Không | Không |

`platform_admin` độc lập, chỉ được cấp bằng operator CLI với user ID xác định.
Workspace owner không có quyền duyệt runtime hoặc quản lý toàn bộ người dùng.
Không thể tự khóa quản trị đang dùng hoặc khóa quản trị cuối cùng.

Mỗi workspace có đúng một owner active; constraint PostgreSQL kiểm ở commit.
Chuyển owner khóa workspace và đổi cả hai vai trò trong cùng giao dịch. Không xóa
membership có lịch sử; đặt inactive để giữ khóa tham chiếu và bằng chứng.

G9 thay quy tắc chỉ người tạo dự án được ghi của G5: mọi workspace writer được
cập nhật dự án dùng chung. `lead_user_id` giữ nguyên làm thông tin điều phối,
không phải quyền riêng của dự án. RLS `project_files`/`project_operations` thay tương
ứng. Revision, idempotency, lịch sử bất biến và phiên bản plugin ghim vẫn giữ.

## Thu hồi và lời mời

Trigger database trên đổi vai trò/inactive thu hồi grant/token, hủy job queued,
đánh dấu cancel job running. Dispatcher kiểm quyền khi bắt đầu, heartbeat và trước
công bố kết quả. Khóa user xóa toàn bộ phiên và thu hồi mọi grant. Không phục hồi
token cũ khi mở khóa. Job bị mất quyền không công bố artifact kết quả.

Lời mời dùng token ngẫu nhiên, hash trong bảng invitation, TTL 7 ngày, một lần,
thu hồi được. Nhận cần phiên đã chứng minh đúng email; kiểm lại quyền người mời.
Tạo invitation và outbox cùng giao dịch. SMTP worker dùng TLS, khóa hàng đợi,
retry tối đa 8 lần. Chưa có SMTP thì trạng thái là **queued**, không báo đã gửi.
SMTP có thể gửi trùng nếu chết sau khi server nhận thư mà DB chưa commit;
Message-ID ổn định hỗ trợ bên nhận nhận biết trùng.

## Giao diện

`/app`: plugin, dự án, tài khoản, workspace và kết nối cho tất cả vai trò.
`/admin`: đúng năm nhóm quản trị workspace hiện có, thêm thành viên/nhật ký thật.
`/platform`: tài khoản/workspace toàn nền tảng, chỉ quản trị nền tảng.
Nút ẩn theo vai trò giúp người dùng; backend và RLS vẫn là nơi quyết định quyền.
Mất quyền trên trang đang mở trả lỗi thật; có nút tải lại quyền. Không tự sửa grant AI.
