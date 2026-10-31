# G7 — Claude

> **Cập nhật sau G8, 31/10/2026:** Hub production hiện tại là
> https://goodmcp.si/mcp, issuer https://goodmcp.si/auth. Chưa thử lại Claude với
> endpoint mới: `not_retested_after_deploy`, chưa pass. Nút connector bị khóa và
> các blocker bên dưới là quan sát tại lần G7 trước deploy; không quy endpoint
> cũ thành lỗi hiện tại của Claude. Xem [G8](G8.md). Giữ nguyên lịch sử dưới đây.

> **Đính chính 31/10/2026:** Khầy xác nhận `goodmcp.si` đã cung cấp nhầm. Hub thật
> chạy local, MCP `http://127.0.0.1:18080/mcp`, issuer `/auth`. Các thao tác với
> domain bên dưới là lịch sử thử nhầm endpoint; chưa thử đường cloud tới Hub local.
> Trạng thái vẫn blocked vì chưa có đường kết nối cloud → local được xác minh;
> quan sát UI tài khoản vẫn giữ giá trị trong phạm vi đã ghi.
> [Evidence đính chính](evidence/G7/endpoint-correction.json).

Ngày 31/10/2026, Asia/Saigon. **Cloud: blocked_by_host; verified_live=false.**
Hai điều kiện còn thiếu: quyền thêm connector ở phiên hiện tại và endpoint Hub đúng.

## Quan sát tài khoản thật

Claude web đang đăng nhập, UI hiện **Free**. Tùy chỉnh → Trình kết nối → Thêm
hiện **“Thêm trình kết nối tùy chỉnh” bị vô hiệu hóa**. Nguyên nhân chưa biết;
không suy ra hết quota, gói tài khoản hay chính sách vùng khi chưa có thông báo.
Không sửa connector/tài khoản và không gửi chat.

`requested_model=null`, `reported_model=unknown`; selector hiện “Sonnet 5.5 Cao”.
Đó là nhãn UI, chưa có model thực hiện tool để xác minh. Protocol cloud unknown.
Ghi nhận UI lúc 13:59:13 +07:00, không có timestamp riêng từng thao tác.
[Bằng chứng UI](evidence/G7/browser-inventory.json), không có screenshot.

| Kịch bản cloud | Kết quả |
|---|---|
| Đăng nhập tài khoản Claude | Phiên đang đăng nhập được quan sát |
| Thêm custom connector | Bị khóa trong UI; chưa submit URL |
| Discovery/login/consent Hub | Chưa chạy |
| List/open plugin; skill; search/read | Chưa chạy |
| Python/poll job | Chưa chạy |
| Save/reopen project và revoke | Chưa chạy |

Đăng nhập Claude không phải đăng nhập OAuth Hub. Endpoint chung
`https://goodmcp.si/mcp` còn trả trang rao bán; subdomain MCP trả Cloudflare Access,
chưa chứng minh backend Hub. [Probe](evidence/G7/endpoint-probes.json).

## Đối chiếu tài liệu và các đường khác

[Tài liệu remote connector](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)
hiện ghi Free có một custom connector và kết nối remote xuất phát từ cloud của
Anthropic, kể cả Claude Desktop. Vì thế không dùng loopback hoặc lý do “Free
không hỗ trợ” để thay cho quan sát thực tế. Quyền UI phiên này vẫn chưa được giải thích.

Claude Desktop chưa thử. Claude Code là đường riêng; chạy binary đã cài với
`--version` trả exit **3221225477**, không có stdout/stderr. Chỉ xác nhận lệnh
thất bại, chưa xác định nguyên nhân và chưa thử kết nối. Không coi đây là lỗi
Claude web hay MCP server. [CLI evidence](evidence/G7/cli-inventory.json).
API chưa inference, chưa có ngân sách riêng; không suy cấu hình hợp lệ thành pass.

Sau khi có endpoint và khả năng thêm connector thật, chạy
[kịch bản chung](../connections/G7-scenarios.md), giữ nguyên kiểm quyền/revoke,
ghi riêng model/protocol đã quan sát. Không có bằng chứng `unsupported` cho toàn bộ Claude.
