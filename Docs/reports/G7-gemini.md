# G7 — Gemini

> **Cập nhật sau G8, 31/10/2026:** Hub production hiện tại là
> https://goodmcp.si/mcp, issuer https://goodmcp.si/auth. Chưa thử lại Gemini với
> endpoint mới: `not_retested_after_deploy`, chưa pass. Các blocker endpoint bên
> dưới thuộc lần G7 trước deploy, không chứng minh Gemini hiện không kết nối được.
> Xem [G8](G8.md). Giữ nguyên lịch sử dưới đây.

> **Đính chính 31/10/2026:** Khầy xác nhận `goodmcp.si` đã cung cấp nhầm. Hub thật
> chạy local, MCP `http://127.0.0.1:18080/mcp`, issuer `/auth`. Các thao tác với
> domain bên dưới là lịch sử thử nhầm endpoint; chưa thử đường cloud tới Hub local.
> Trạng thái vẫn blocked vì chưa có đường kết nối cloud → local được xác minh;
> quan sát UI tài khoản vẫn giữ giá trị trong phạm vi đã ghi.
> [Evidence đính chính](evidence/G7/endpoint-correction.json).

Ngày 31/10/2026, Asia/Saigon. **Cloud: blocked_by_host; verified_live=false.**
Blocker là endpoint Hub chưa đúng; chưa có lỗi MCP trực tiếp từ Gemini để kết luận.

## Phiên thực và phép thử

Gemini web đang đăng nhập. Tùy chỉnh → Trình kết nối → Tạo ứng dụng tùy chỉnh mở
được form “Kết nối với máy chủ MCP”, yêu cầu URL HTTPS; phần bổ sung có client
ID/secret. UI tiếng Việt; gói và vùng tài khoản chưa xác định.

Đã nhập `https://goodmcp.si/mcp`, nhấn Tiếp theo. Gemini chuyển tới màn xin đồng ý
chia sẻ thông tin tài khoản/skills. **Không có kết quả discovery hoặc lỗi MCP
được quan sát.** Dừng trước tick đồng ý và Kết nối vì probe cho thấy URL trả
trang rao bán, chưa phải Hub. Hủy form, không tạo connector, không cấp quyền.

`requested_model=null`, `reported_model=unknown`; nhãn selector là “Flash”.
Protocol cloud unknown. Evidence UI ghi lúc 13:59:13 +07:00, không timestamp riêng
từng thao tác; [browser-inventory.json](evidence/G7/browser-inventory.json).
Không screenshot hoặc inference/chat thử.

| Kịch bản cloud | Kết quả |
|---|---|
| Form custom MCP | Quan sát trực tiếp, nhập URL và Next |
| Màn consent của Gemini | Đã tới; chưa chấp thuận |
| Discovery MCP/login/consent Hub | Chưa chứng minh/chưa chạy |
| List/open plugin; skill; search/read | Chưa chạy |
| Python/poll job | Chưa chạy |
| Save/reopen project và revoke | Chưa chạy; chưa có grant Hub |

## Tài liệu và ranh giới

[Tài liệu Google](https://support.google.com/gemini/answer/17209137?hl=en-SY)
ghi điều kiện tuổi 18+, ở US, tài khoản cá nhân, Keep Activity bật và English.
Lần này UI tiếng Việt vẫn mở form được; chưa kiểm tuổi/vùng/activity và không đổi
các thiết lập đó. Không dùng điều kiện tài liệu để bịa ra blocker tài khoản hay
gắn `unsupported`. [Probe endpoint](evidence/G7/endpoint-probes.json) là bằng
chứng độc lập với màn consent Gemini.

Gemini CLI `0.45.2` chỉ được kiểm version; chưa cấu hình/kết nối/inference.
Desktop/mobile/API chưa thử; API không có ngân sách riêng trong nhiệm vụ này.
Không dùng CLI hoặc màn consent để công bố Gemini cloud hỗ trợ Hub.

Sau khi endpoint/discovery đúng, thử lại form và hoàn tất
[kịch bản chung](../connections/G7-scenarios.md). Không tự sửa giao thức hoặc bỏ OAuth.
