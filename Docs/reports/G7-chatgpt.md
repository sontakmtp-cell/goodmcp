# G7 — ChatGPT

## Cập nhật G8 — 31/10/2026

**`partial_live`, chưa đủ full G7.** Tại https://goodmcp.si/mcp, ChatGPT Plus thật
đã CIMD/OAuth consent, MCP **2026-07-28**, list 3 plugin, open Finance/OPC, đọc skill
`opc-asset-ops`, search `tax`/đọc nguồn có SHA, chạy/poll CIT Python gốc **80 VND**.
Project `9529f488-da6f-45b4-b1f1-20a974d6b9bc` revision 1, file 49 bytes SHA-256
`3aa0fdf6c9bba0657cfc7639e38d1239bed5a87cb635bdb7ca0bbf76f52ebf9e`
đã được đọc lại ở **chat mới**.

Đã revoke đúng grant thử `98db754b-edcc-4094-891b-dd8a9d6217df`, 36 token, không
đụng Web grant. Host yêu cầu reconnect; request refresh tiếp theo trả **400**.
**Chưa quan sát MCP 401 bằng grant cloud này; Godot chưa open.** Không đổi thành
full pass. Grant thử vẫn revoked, reconnect mới sau reboot đã hủy. Web SSO/project
sau reboot đạt riêng; chưa chạy lại ChatGPT sau reboot.

[UI, hai chat, job/project/hash](evidence/G8/browser-chatgpt.json),
[transport](evidence/G8/chatgpt-final-tool-audit.json),
[kết quả Python thực](evidence/G8/production-data-audit.json),
[revoke](evidence/G8/chatgpt-revoke.json),
[400 sau revoke](evidence/G8/chatgpt-revoke-retry-transport.json),
[UI reconnect](evidence/G8/browser-revoke.json).

`requested_model=null`, `reported_model=unknown`; selector “Cao”. Chưa chứng minh
subagent/model selection hoặc mọi khả năng file của host. Ban đầu UI “Không thể
tải phản hồi này”; reload mới hiện kết quả thật. Không khẳng định nguyên nhân.
CIMD/Origin/CSP đã sửa có hồi quy và callback/tool thực trong [G8](G8.md).

## Lịch sử thử trước triển khai — nội dung dưới đây giữ nguyên

> **Đính chính 31/10/2026:** Khầy xác nhận `goodmcp.si` đã cung cấp nhầm. Hub thật
> chạy local, MCP `http://127.0.0.1:18080/mcp`, issuer `/auth`. Các thao tác với
> domain bên dưới là lịch sử thử nhầm endpoint; chưa thử đường cloud tới Hub local.
> Trạng thái vẫn blocked vì chưa có đường kết nối cloud → local được xác minh;
> quan sát UI tài khoản vẫn giữ giá trị trong phạm vi đã ghi.
> [Evidence đính chính](evidence/G7/endpoint-correction.json).

Ngày 31/10/2026, Asia/Saigon. **Cloud: blocked_by_host; verified_live=false.**
Blocker chính thuộc endpoint của Hub, không kết luận ChatGPT không hỗ trợ MCP.

## Tài khoản và bề mặt

Browser thật dùng profile đang đăng nhập, danh tính đã lược. UI hiện **Plus** và có
form thêm server MCP tùy chỉnh: URL/Tunnel, OAuth mặc định và OAuth nâng cao.
`requested_model=null`, `reported_model=unknown`; nhãn UI quan sát được là
“Cao”, không phải bằng chứng model đã gọi tool. Protocol cloud: **unknown**.

Quan sát được ghi lúc 13:59:13 +07:00; từng thao tác trước đó cùng ngày không có
timestamp riêng. [Bằng chứng UI](evidence/G7/browser-inventory.json).

## Phép thử và kết quả thực

1. Mở Plugin → thêm server MCP tùy chỉnh, đặt tên thử G7.
2. Nhập URL Khầy cung cấp, với đường MCP: `https://goodmcp.si/mcp`.
3. Giữ OAuth; mở cấu hình OAuth nâng cao để host tìm metadata.
4. Host báo nguyên văn: **“Không thể tìm thấy cài đặt OAuth. Hãy kiểm tra URL máy
   chủ và thử lại hoặc nhập cài đặt theo cách thủ công.”**
5. Hủy form. Không nhập credential, không đổi OAuth, không tạo connector.

[Probe HTTPS](evidence/G7/endpoint-probes.json) xác nhận `/mcp` và các discovery
trả HTML trang “Domain For Sale” từ Vercel, 200/1230 bytes, cùng SHA-256 với `/`.
Đây là lỗi discovery thực từ ChatGPT, chưa tới kết nối MCP có xác thực.

| Kịch bản cloud | Kết quả |
|---|---|
| UI tài khoản/form custom MCP | Quan sát trực tiếp |
| OAuth discovery | Thất bại, lỗi host nêu trên |
| Login/consent Hub | Chưa chạy |
| List/open plugin; đọc skill; search/read | Chưa chạy |
| Python; poll job | Chưa chạy |
| Save/reopen project qua chat mới | Chưa chạy |
| Revoke grant cloud và kiểm 401 | Chưa chạy; chưa có grant Hub cloud |

Không có ảnh chụp hoặc log request phía ChatGPT; evidence là ghi nhận trạng thái
UI qua công cụ browser của subagent theo AGENTS.md. Không có inference/chat thử.

## Đường khác và bước tiếp

ChatGPT desktop chưa thử. Codex CLI có version `0.162.0` nhưng là sản phẩm/đường
riêng, chưa cấu hình hoặc gọi Hub trong G7. API chưa chạy vì chưa có ngân sách
model riêng; không kết luận khóa API vắng mặt. [CLI inventory](evidence/G7/cli-inventory.json).

[Tài liệu chính thức](https://developers.openai.com/apps-sdk/deploy/connect-chatgpt)
cho phép public HTTPS hoặc Secure MCP Tunnel để thử server. Lượt này chưa có
tunnel/runtime key được cấu hình cho Hub. Tunnel chỉ là phương án sau; không
coi nó đã hoạt động. TOTP/triển khai/auth routing public còn thuộc G8.

Khắc phục endpoint/discovery của Hub trước, rồi chạy đủ
[kịch bản chung](../connections/G7-scenarios.md). Local `protocol_only` không nâng
trạng thái ChatGPT thành live pass.
