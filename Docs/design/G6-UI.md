# G6 — Thiết kế User Portal và Admin Dashboard

Ngày 31/10/2026 (Asia/Saigon). Phạm vi local G6; không deploy production/G7/G8.

## 1. Quyết định thiết kế

Hai bề mặt dùng chung React app, backend và OAuth G2. `/` là User Portal; `/admin` là Admin Dashboard. Reference: `UI-mock/GoodMCP_landing_page.png` (1448 × 1086) và `UI-mock/1-tile.mp4`. Giữ hero tối, chữ lớn giữa, cá mập xanh và khung chọn AI → sao chép URL → hướng dẫn. Bỏ đăng ký, tuyên bố hàng trăm plugin và catalog minh họa không có thật trong ảnh. Không dùng ảnh mock làm giao diện.

Admin nền sáng, sidebar 240px trên desktop; mobile menu xếp ngang/cuộn trong vùng riêng, không làm rộng toàn trang. Cùng font Be Vietnam Pro phục vụ local, fallback system sans hỗ trợ dấu Việt, blue primary, border mảnh, radius 12–20px. Nội dung tối đa 1200px, khoảng cách 8/16/24/32px; nút/touch target tối thiểu 44px. Không dashboard biểu đồ giả.

Hiệu ứng dùng mã nguồn thật https://github.com/stackedlol/ascii-sharks (MIT), vendored kèm LICENSE và commit. Canvas trang trí aria-hidden, không chặn click, có nút dừng, ngừng khi tab ẩn và reduced-motion; giới hạn kích thước/mật độ cho mobile. Không cần model API hoặc asset trả phí.

## 2. User Portal

- Header: GoodMCP, Plugin, Hướng dẫn, đăng nhập/tài khoản; Admin chỉ xuất hiện cho owner/admin đã xác minh.
- Hero: “Kết nối AI của bạn với GoodMCP”; mô tả công cụ/tài liệu cá nhân, không hứa chức năng chưa có.
- Khung kết nối: ChatGPT, Claude, Gemini, Grok, CLI. Native buttons aria-pressed; URL mặc định `https://mcp.example.invalid/mcp`, nhãn “URL mẫu — chưa triển khai”, copy có thông báo thành công/lỗi. Không đặt token trong URL.
- Hướng dẫn 3 bước theo host; nói rõ phụ thuộc khả năng MCP/OAuth của tài khoản, cloud không truy cập localhost, chưa nghiệm thu G7. Không suy rằng chọn host nghĩa là đã kết nối.
- Danh mục: trước login chỉ mô tả nhóm khả năng chung, không fetch API riêng; sau login lấy plugin enabled trong workspace của token. Mô tả theo manifest nếu có, fallback trung thực theo tên mẫu. Không mặc định public catalog.
- Tài khoản: phiên web xác minh bằng `/api/v1/me/workspaces`; phân biệt với trạng thái connector AI chưa có API. Thu hồi chỉ grant web hiện tại. Không UI token/password kỹ thuật.

## 3. Admin — 5 nhóm

| Menu | Nội dung ưu tiên | Trang chi tiết |
|---|---|---|
| Tổng quan | Workspace/role, lối tắt tải plugin/dự án, giới hạn dịch vụ | Không thống kê ước đoán |
| MCP & Plugin | Danh sách phân trang, ZIP/resume và preview | Bật/tắt, versions/chuyển bản, export ZIP, tài liệu/tìm từ khóa, Python schema form, job |
| Dự án | Danh sách phân trang, tạo từ installation enabled | Revision, pin, bước tiếp tục, file plain text theo trang, lưu draft |
| Người dùng & Kết nối | Danh tính workspace/role, phiên web, revoke | Quản trị người dùng/toàn bộ kết nối: chưa hỗ trợ API |
| Hệ thống | Kiểm tra readiness thật, theo dõi job ID | Logs/tài nguyên/backup: chưa hỗ trợ API |

Không thêm quyền UI thay backend. Route admin chặn member/viewer; server tiếp tục kiểm quyền trên từng request. Revoke, tắt/chuyển phiên bản và hủy công việc cần xác nhận có mô tả tác động. Project pin không đổi khi đổi installation. Export dùng fetch xác thực rồi Blob download, không query token.

## 4. Đối chiếu hợp đồng thực tế trước build

Đã đọc `apps/api/{auth,main,registry_api,jobs_api,documents_api,workflows_api,mcp_auth}.py`, `packages/core/goodmcp/{registry,jobs,workflow_spec,finance_spec}.py` và contracts G3–G5. Backend local `/health/ready` trả HTTP 200 ngày 31/10/2026. Giữ nguyên kiến trúc, schema và hợp đồng API G1–G5. Lượt đóng gate G6 sửa riêng cache xác thực thừa hưởng trong mcp_auth.py để mỗi request mới kiểm quyền lại; xem báo cáo G6.

| Chức năng | API / quy tắc |
|---|---|
| OAuth | POST `/auth/register`; GET `/auth/authorize`; POST `/auth/token`, `/auth/revoke`; PKCE S256, state, issuer, exact redirect. Login/consent server hiện hữu |
| Workspace | GET `/api/v1/me/workspaces`; không tin workspace/role client tự khai |
| Upload | POST `/uploads` bytes/sha256/idempotency_key; GET status; PUT `/parts/{part}` raw + X-Content-SHA256; POST complete/cancel. Resume bỏ received_parts server; SHA-256 file phải khớp |
| Plugin | GET `/plugins`, `/installations/{id}/versions`; PUT `/installation` version_id/enabled/expected_revision; GET `/versions/{id}/export` |
| Tài liệu | GET `/installations/{id}/documents`; POST `/search` keywords/match/cursor; GET `/{resource_id}` offset/length; chỉ text |
| Python | GET `/installations/{id}/bindings` có input_schema; POST `/invocations` binding_id/arguments/key; GET `/jobs/{id}`; POST cancel |
| Project | GET/POST `/projects`; GET `/{id}`; GET files/{id} offset/length; POST artifacts với expected_revision/key/logical_path/content/media_type |
| Chưa có API | List jobs/uploads toàn cục; uninstalled-version discovery; user CRUD; all connections; audit logs; resource usage; backup; full project export; approve runtime |

Các đường nghiệp vụ tương đối với `/api/v1/workspaces/{workspace_id}`. Phân trang không lấy âm thầm toàn bộ. Job chờ/running không báo xong; import ready vẫn cần người dùng bật. Runtime không approved thì không có calculator giả.

## 5. Xác thực và bảo mật frontend

SPA public OAuth client, không secret; server đăng nhập G2 giữ cookie HttpOnly. Bearer/refresh chỉ trong RAM, không localStorage/sessionStorage/logs. SessionStorage chỉ tạm PKCE verifier/state/client_id/return path, xóa sau callback. Reload cần xác thực lại qua cookie/consent G2. Khi hết hạn 401, xóa dữ liệu riêng khỏi UI và yêu cầu đăng nhập; 403 không xóa phiên. Không render HTML plugin hoặc lỗi server thô bằng innerHTML.

Dev Vite proxy chỉ tới backend loopback cố định/env do operator đặt; normalize Host/Origin phía proxy theo authority local đã cấu hình G2. Không thêm CORS hay bypass backend. Production cùng-origin routing/OAuth config thuộc G8; không coi dev proxy là production deployment. URL MCP public placeholder độc lập địa chỉ backend local đang chạy.

Resume upload giữ duy nhất upload ID + filename/size/hash, gắn workspace, không lưu nội dung ZIP/token. Chọn lại cùng file, hash trước, GET trạng thái server; sai hash/kích thước từ chối trước PUT. Key idempotency ổn định qua retry; whole-file hash tính theo luồng để không đọc 1 GiB vào RAM. Upload progress chỉ tính chunk server đã nhận. Dừng gửi giữ resume; cancel server là hành động riêng.

## 6. Trạng thái và khả năng tiếp cận

Loading có aria-busy/status; empty giải thích và CTA phù hợp; lỗi tiếng Việt theo 401/403/404/409/413/422/429/5xx/network, request ID để đối chiếu; success chỉ sau response thật. Retry đọc rõ ràng; ghi giữ idempotency key cho cùng payload, không tự retry thao tác nguy hiểm. Không copy raw exception chứa dữ liệu nhạy cảm.

Skip-link đến main, landmark/nav labels, heading có trật tự, label cho input, focus-visible tương phản, native form validation, Escape/Tab của confirm dialog, focus trả về nút gọi. Alert/status không giành focus. Không chỉ dùng màu để báo trạng thái. Min 320px; lưới 1 cột mobile, control wrap; pre/plain text wrap và scroll riêng nếu cần. Reduced-motion là yêu cầu nghiệm thu.

## 7. Kiểm thử và ranh giới bàn giao

UI tests dùng fixture có nhãn trong test code, không ship fixture trong app: auth/callback/failure, private catalog, admin role, upload multipart/resume/hash/retry, schema form→invocation, job cancel/results, pagination, revision conflict, XSS text, clipboard errors, offline/401/403/429/5xx. Kiểm accessibility tự động trên DOM và browser bàn phím/responsive khi công cụ hỗ trợ. Chạy build/typecheck và API local smoke riêng; báo rõ test giả lập so với backend thật. Design QA đối chiếu reference và screenshot cùng khung. Mọi giới hạn ghi trong `Docs/reports/G6.md`.
