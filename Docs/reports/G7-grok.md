# G7 — Grok

> **Cập nhật sau G8, 31/10/2026:** Hub production hiện tại là
> https://goodmcp.si/mcp, issuer https://goodmcp.si/auth. Chưa thử lại Grok với
> endpoint mới: `not_retested_after_deploy`, chưa pass. Lịch sử Blender/endpoint
> bên dưới được giữ để đối chiếu; binding Blender cũ đã được gỡ trong G8 theo
> chỉ định Khầy, không còn là cấu hình hiện tại. Xem [G8](G8.md).

> **Đính chính 31/10/2026:** Khầy xác nhận `goodmcp.si` đã cung cấp nhầm. Hub thật
> chạy local, MCP `http://127.0.0.1:18080/mcp`, issuer `/auth`. Các thao tác với
> domain bên dưới là lịch sử thử nhầm endpoint; chưa thử đường cloud tới Hub local.
> Trạng thái vẫn blocked vì chưa có đường kết nối cloud → local được xác minh;
> quan sát UI tài khoản vẫn giữ giá trị trong phạm vi đã ghi.
> [Evidence đính chính](evidence/G7/endpoint-correction.json).

Ngày 31/10/2026, Asia/Saigon. **Cloud: blocked_by_host; verified_live=false.**
Chưa thử kết nối với endpoint sai; không có lỗi MCP/discovery của Grok để báo.

## Quan sát thật

Trang xác minh bảo mật ban đầu tự hoàn tất; phiên Grok web đang đăng nhập.
Plugin → Trình kết nối mới → Tùy chỉnh mở form có Tên, URL máy chủ MCP và nút
thêm connector. Không thấy thao tác kiểm URL/metadata riêng trước nút thêm.

Không submit `https://goodmcp.si/mcp` vì probe đã xác nhận URL trả trang “Domain
For Sale”. Form được hủy; không cấp quyền/tạo connector và không gửi chat.
Connector **Blender** có sẵn tại `mcp.goodmcp.si` hiện “Cần chú ý”, được giữ nguyên;
đó không phải chứng cứ Hub G7 hoặc lỗi đã xác định của Hub.

`requested_model=null`, `reported_model=unknown`; selector ghi “Nhanh”, không có
model ID cụ thể. Protocol cloud unknown. Evidence UI ghi lúc 13:59:13 +07:00,
không timestamp riêng từng thao tác. [UI evidence](evidence/G7/browser-inventory.json).
Không screenshot hoặc request log MCP từ Grok.

| Kịch bản cloud | Kết quả |
|---|---|
| Phiên đăng nhập/form custom connector | Quan sát trực tiếp |
| Submit URL/discovery/login Hub | Chưa chạy; endpoint chưa đúng |
| List/open plugin; skill; search/read | Chưa chạy |
| Python/poll job | Chưa chạy |
| Save/reopen project và revoke | Chưa chạy; chưa có grant Hub |

## Tài liệu và đường khác

[Tài liệu Grok connectors](https://docs.x.ai/grok/connectors) mô tả custom MCP
qua URL và yêu cầu server truy cập được từ Internet. Khả năng này của hãng không
chứng minh Hub hiện đã được nối. [Probe HTTPS](evidence/G7/endpoint-probes.json)
thấy subdomain MCP trả 401 Cloudflare Access và discovery trỏ issuer Cloudflare,
khác issuer Hub local; chưa xác minh backend, không bypass xác thực.

Grok CLI `1.0.46 (2765805b9442) [stable]` chỉ kiểm version; chưa auth/configure/
connect/inference. Desktop/mobile/API chưa thử. Model API không có ngân sách riêng
trong nhiệm vụ; không gọi API để thay bằng chứng web.

Sau khi có endpoint Hub thật, chạy đủ
[kịch bản chung](../connections/G7-scenarios.md), ghi chính xác protocol/model và
grant revoke. Không công bố Grok `verified_live` hoặc `unsupported` từ form UI.
