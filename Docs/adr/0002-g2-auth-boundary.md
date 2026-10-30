# ADR-0002 — Issuer riêng, credential hash và MCP runtime role

Ngày: 30/10/2026. Quyết định áp dụng cho local G2; host cloud/TLS production chưa nghiệm thu.

- Tách service `auth` dùng `hub_auth`; API/worker giữ `hub_runtime`. Cả hai đều
  không owner/superuser/BYPASSRLS. Migration giữ `hub_migrator` và schema G1 đã freeze.
- Issuer cần đọc password hash/membership và quản lý credential; các quyền này
  được cấp tường minh bằng role/policy RLS riêng. API không có auth_password và
  không được INSERT/UPDATE oauth_grants/tokens sau migration 0002_g2.
- API xác minh opaque access token qua hàm SQL SECURITY DEFINER
  `hub_access_identity(hash,issuer,resource)`, chủ sở hữu hub_migrator. Function
  dùng bảng được qualify, search_path cố định, revoke PUBLIC execute và chỉ trả
  identity của token còn hạn, grant/client/user/membership còn hiệu lực. Role
  runtime không được tạo schema/function hoặc kế thừa role của owner.
- Access/refresh/code/session/CSRF chỉ lưu SHA256; password mới dùng Argon2id.
  Hash scrypt G1 được nâng cấp sau login đúng. Hiện không có credential upstream
  cần giải mã từ DB; nếu bổ sung phải dùng khóa mã hóa ngoài DB dump theo PLAN.
- Khóa grant trước rồi khóa credential trong cùng transaction. Code/refresh dùng
  một lần; replay revoke family. Thứ tự khóa nhất quán tránh lock đảo chiều khi
  refresh/revoke cùng chạy. Error replay vẫn commit revocation; lỗi phát sinh
  trước publish token làm rollback toàn transaction.
- Cùng origin local `/auth` và `/mcp`, strict Host/Origin; Caddy bind loopback.
  Các subdomain production trong PLAN cần routing/config được kiểm lại ở G8.
- Thêm service auth giới hạn 512 MiB, tăng tổng cap thiết kế G0 thêm 512 MiB lên
  khoảng 7.040 MiB kể cả search/light jobs/reserve OS. Đây **không phải số đo RSS**;
  G4 phải đo toàn Compose trước chấp nhận tải trên VPS 8 GB. Build index tiếp tục
  mặc định offline, không cộng builder cùng runtime.

Wire/local evidence và blocker ở [G2.md](../reports/G2.md). Không đổi hợp đồng
runtime Python/TF-IDF hoặc thêm plugin executable trong giai đoạn này.
