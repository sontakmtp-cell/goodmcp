# GoodMCP Web — G9

React + TypeScript + Vite. `/` là trang giới thiệu; `/app` là khu làm việc mọi
vai trò; `/admin` quản trị workspace; `/platform` quản trị toàn GoodMCP.
Dữ liệu ứng dụng đến từ API thật. Fixture chỉ dùng trong kiểm thử riêng.

## Đăng nhập và quyền

Web dùng phiên server/cookie HttpOnly, Secure trên production và CSRF cho thao tác
ghi. Reload vẫn giữ phiên còn hạn; không cấp hoặc lưu bearer MCP trong browser.
Google đăng nhập trực tiếp, chủ cũ giữ đường Cloudflare khôi phục và liên kết
Google từ tài khoản đã xác thực. Chọn workspace web không thay workspace grant AI.

Quản lý thành viên, lời mời, kết nối và audit dùng `/auth/web/...`; nghiệp vụ giữ
`/api/v1/workspaces/{workspace_id}`. Backend/RLS quyết định quyền. localStorage
chỉ giữ metadata tiếp tục upload, không giữ token đăng nhập.

## Chạy local

Cần backend schema G9 (`0007_g9`) và auth service G9 đang chạy. Không trỏ frontend
G9 vào backend G8 cũ rồi coi lỗi thiếu endpoint là lỗi mạng. Chạy setup-local để
bổ sung `web_session_key` nếu thư mục secret có từ trước; script không ghi đè khóa.

```powershell
cd H:\AI\goodmcp\apps\web
npm ci
npm run dev
```

Dev server ở `http://127.0.0.1:4173`, proxy mặc định backend
`http://127.0.0.1:18080`; backend public base/Host/Origin phải khớp. Không phơi dev
server ra Internet hoặc thêm CORS/bypass auth. G9 Google thật dùng callback production;
local không có Google config có thể dùng form chủ qua `/auth/login` để kiểm API.

Production dùng `VITE_MCP_URL=https://goodmcp.si/mcp`. Không đưa VPS/DB/OIDC secret
vào biến VITE. Google client secret chỉ nằm trong auth service.

## Kiểm tra

```powershell
npm test
npm run build
```

50 test passed / 1 opt-in live test skipped trong bàn giao. Live React/jsdom →
API/Python cần `GOODMCP_LIVE=1`, stack local phù hợp và credential fixture local;
không chạy tùy tiện trên production. Jsdom không chứng minh layout hay contrast.

G9 có kiểm browser thật local ở 320×800 với API/session giả: bốn màn, bàn phím,
navigation và workspace name dài. Đã sửa nền tối/chữ tối và heading tràn ngang.
Bằng chứng này tách khỏi Google/invitation/revoke production và lỗi ChatGPT host.

## Giới hạn

Chính sách gói/quota cấu hình, dashboard tài nguyên/backup/job/upload đầy đủ thuộc
G10; marketplace/thanh toán thuộc G11. SMTP chưa có thì lời mời chỉ queued. Chỉ
operator/platform được duyệt runtime, không tự chạy mã ZIP tải lên.

[Thiết kế G9](../../Docs/design/G9-auth-workspaces.md),
[báo cáo](../../Docs/reports/G9.md), [vận hành](../../Docs/runbooks/G9-operations.md).
Lịch sử G6 và giấy phép giữ trong báo cáo/notice riêng.

## Nguồn và giấy phép

ASCII sharks được vendored từ stackedlol/ascii-sharks, commit
`a0074c16a106f0abc665fe9712ca445f8f98ad8e` (MIT). Sáu file `.ts` nguồn giữ nguyên;
`Sharks.tsx` sở hữu vòng đời pause/visibility, CSS phối màu. Không dùng video làm
nền thay cho hiệu ứng thật. Xem `THIRD_PARTY_NOTICES.md`.
