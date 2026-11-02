# G9 — Vận hành nhóm kiểm chứng

Xem [thiết kế/API](../design/G9-auth-workspaces.md) và [báo cáo](../reports/G9.md).
Giữ SSH và khôi phục G8; không thay dữ liệu bằng bộ fixture khi triển khai.

## Cấu hình

Google Cloud project `goodmcp`, app **GoodMCP**, client **GoodMCP web**, External /
Testing. Ba tài khoản thử do Khầy chỉ định được giữ trong cấu hình riêng của máy chủ.
Server cũng kiểm allowlist riêng;
`signup_enabled=false`. Chỉ mở công khai sau cổng vận hành G10.

Google config nằm ngoài source tại `/opt/goodmcp/secrets/google_config`:
`client_id`, `client_secret`, `state_key`, `testing_emails`, `signup_enabled`.
Mẫu không có secret: [google.example.json](../../configs/google.example.json).
`web_session_key` là secret riêng dùng giữa API/auth. Không gửi các file này cho
frontend, không in bằng `cat` hoặc lưu log cấu hình Compose đầy đủ.

Compose gồm base + production + `compose.g9.yml`, wrapper `/opt/goodmcp/compose`.
Env triển khai G9 tại `/opt/goodmcp/deploy-g9.env`. Thư mục source/web G9 ở
`/opt/goodmcp/releases/g9-r2` (image `goodmcp-hub:g9r2-20261102`), symlink `current` trỏ bản vận hành. Bản G9 đầu vẫn được giữ để đối chiếu. Unit backup/health
dùng `current`; backup thu cả thư mục releases để giữ bản G9.

## Liên kết tài khoản chủ

1. Vào `https://goodmcp.si/auth/login?return_to=/app/account` bằng đường Cloudflare
   đã xác thực chủ cũ.
2. Chọn **Liên kết Google với tài khoản này**, chọn đúng Google của Khầy.
3. Kiểm tra vẫn thấy workspace/plugin/dự án cũ và **Đã liên kết Google**.
4. Những lần sau dùng Google bình thường. Không ghép tài khoản chỉ vì cùng email.

Email hiển thị của chủ có thể vẫn là email legacy; điều đó giữ đường khôi phục.
Nếu không khớp email Google, chủ không được dùng phiên đó để nhận lời mời gửi đến
email legacy chưa được Google xác minh. Không sửa database để giả chứng minh email.

Quyền nền tảng cấp rõ ràng bằng CLI operator, không gắn với vai trò workspace:

```sh
./compose run --rm --no-deps admin python -m goodmcp.platform_admin --user-id USER_UUID_DA_XAC_MINH
```

## Email SMTP

Chưa có cấu hình SMTP được Khầy cung cấp ở lượt triển khai này. Không bật dịch vụ
email trả phí. Lời mời ở hàng đợi cho đến khi cấu hình được kiểm tra.

Mẫu [smtp.example.json](../../configs/smtp.example.json). Đặt config thật trong
`/opt/goodmcp/secrets/smtp_config`, chủ UID 10001, quyền 0400. Dùng sender đã xác
minh với nhà cung cấp, TLS `ssl` hoặc `starttls`; không lưu password trong env web.
Sau khi có dịch vụ được chấp thuận, bật profile `email` của Compose G9.
Kiểm thư thực đến đúng tài khoản, sau đó xem `sent_at`/`last_error` đã lọc secret.
Không gọi thư còn queued là đã gửi. Không tự gửi thư đến địa chỉ ngoài nhóm đã chỉ định.

## Kiểm tra và xử lý

```sh
./compose ps
curl -fsS https://goodmcp.si/health/ready
systemctl status goodmcp-backup.timer goodmcp-health.timer --no-pager
```

Không token: `/mcp` phải trả 401; có cookie web vẫn phải 401. `/auth/web/session`
không đăng nhập trả 401. Không CSRF/Origin hợp lệ thì yêu cầu ghi trả 403.
Thu hồi grant qua `/app/connections`; khóa user ở `/platform` khi cần chặn cả web/AI.
Đăng xuất mọi thiết bị chỉ kết thúc phiên web, các kết nối AI được thu hồi riêng.

Job đang chạy mất quyền không xuất kết quả; container dừng, trạng thái có thể chờ
hết lease khoảng 30 giây trước khi trở thành cancelled. Đọc trạng thái thật,
không báo thành công chỉ vì đã gửi yêu cầu hủy.

## Tắt Google, sửa lỗi và dữ liệu

Tạm ngừng đăng nhập Google mới: đặt `HUB_GOOGLE_ENABLED=0` trong deploy env G9 và
tạo lại auth bằng wrapper; giữ Cloudflare khôi phục và dữ liệu. Không xóa user,
identity, workspace hoặc migration để xử lý lỗi đăng nhập.

Client MCP chưa có phiên đi thẳng từ authorize sang Google khi Google được bật;
không đưa thành viên mới qua cửa Cloudflare chỉ dành cho chủ. `/auth/login` trực
tiếp vẫn là đường khôi phục chủ. Nhánh này đã kiểm riêng trong bản g9r2.

Migration `0007_g9` chỉ đi tới; không downgrade xóa danh tính hoặc ghi đè database
production bằng bản trước nâng cấp. Bản G8 nguyên trạng kiểm revision cũ nên không
được trỏ trực tiếp vào schema G9. Đã giữ image `goodmcp-hub:g9-recovery-20261101`
cùng schema G9, kiểm API readiness, đọc phiên/user/workspace mới và giữ hash dữ liệu
nghiệp vụ trên bản sao production. Có thể đổi HUB_IMAGE sang bản này và tạo lại
API/auth/worker/dispatcher; giữ frontend G9, secrets và database. Bản recovery có
quy tắc dự án chặt hơn (chỉ lead ghi), vì vậy chỉ là cầu nối sửa lỗi; không nhận là
đã diễn tập rollback toàn bộ production. Giữ snapshot trước nâng cấp và source/image
để phục vụ khôi phục thảm họa riêng.

Thay client secret: lưu secret mới kín, xác nhận hoạt động, vô hiệu hóa bản cũ trong
Cloud Console. Secret đầu tiên của lượt này đã bị vô hiệu hóa sau sự cố output
công cụ; tuyệt đối không khôi phục bản đó.

## Chạy lại kiểm chứng local

```powershell
./scripts/verify.ps1 -Stage G9 -WorkingTree -G4Release .local/g4/active/release.json
```

Hoặc `verify.sh G9 --working-tree --g4-release PATH`. Bỏ WorkingTree để dùng git
archive sạch sau khi source đã được commit. Không lấy local pass làm Google thật,
SMTP thật hoặc ChatGPT thật. Status G9 local là `local_passed_acceptance_pending`.
