# Software Workshop — GoodMCP G9

## Kết luận

Conditional Go cho nhóm kiểm chứng ba Google; No-Go cho beta công khai.
G9 đã triển khai, dữ liệu cũ giữ nguyên, bốn vai trò/invitation/revoke thật đạt.
SMTP được Khầy hoãn; responsive 320 px local fixture đã đạt; ChatGPT web chưa có kết quả cuối
được xác minh. Không dùng điểm tổng hợp để đổi các thiếu sót này thành PASS.

## Đội thực sự tham gia

| Native task ID | Vai trò và cấu hình | Sở hữu/kết luận |
|---|---|---|
| `/root` | Điều phối/triển khai, mô hình tác vụ chính | OIDC, migration, session/API boundary, hạ quyền job, shared project, Compose/production, kiểm chứng và bàn giao |
| `/root/google_console` | Worker trình duyệt, GPT-6.1 Terra medium theo AGENTS.md | Google Console, client/testing users, rotate secret; Google thật, mời/nhận, vai trò và revoke; 320 px local đạt, Chrome production bị chặn và ChatGPT chưa xác minh |
| `/root/workspace_backend` | General implementation worker, kế thừa mô hình tác vụ | WorkspaceAdmin/router, invitation, SMTP worker và các test; running downgrade harness |
| `/root/g9_frontend` | General implementation worker, kế thừa mô hình tác vụ | apps/web/src; build đạt, 50 test passed/1 skipped; không tự nhận browser pass |
| `/root/g9_security` | Security Officer, GPT-6.1 Sol high | Tái hiện và kiểm lại hai lỗi recovery, review delta shared-project; không còn finding xác minh đang mở trong phạm vi |

Không gán hai general worker thành Designer/MCP Builder hoặc người kiểm thử browser.
Native agents trả kết quả về root; không giả kết quả của agent hay sinh đội ngoài.

## Phát hiện và sửa

- Hai lỗi mức medium đã sửa: Google login sau link đổi email recovery; email trùng
  làm Cloudflare owner lookup mơ hồ. Có kiểm chứng rollback-only trên DB test.
- Root phát hiện G5 lead-only mâu thuẫn G9 chia sẻ dự án; sửa API/RLS cùng nhau,
  giữ scope/revision/composite FK và lead metadata. Member write/viewer deny test đạt.
- Root phát hiện client MCP mới vẫn vào CF owner login; sửa nhánh unauth authorize
  sang Google, giữ recovery. 40 kiểm tra auth và redirect production đạt.
- Không gọi lỗi ChatGPT UI là lỗi API đã xác minh: server có 200, UI chưa có phản
  hồi cuối. Có project thử revision 0 phát sinh, giữ nguyên và ghi rõ ID trong G9.md.

## Kiểm thử và phát hành

240 kiểm thử nền, 23 G9 có ca trùng, 47 parity Python, HTTP/MCP/job/workflow/restart
đạt trong bộ r3. Bản sửa login cuối chạy 40 ca auth riêng và probe production.
Browser thực ba Google/bốn workspace/bốn vai trò, ba invitation nhận qua link;
SMTP delivery không đạt vì chưa có SMTP. Revoke thật HTTP200 → 401 cả API/MCP khi
token còn hạn, refresh400. Running Python downgrade không xuất artifact, container dừng.

Image cuối g9r2-20261102, migration0007; thử trước trên bản sao DB production và
backup trước cutover. Recovery image giữ schema và dữ liệu mới, có phép kiểm DB copy;
chưa diễn tập rollback toàn production. Source working tree, chưa clean release commit.

## Việc còn lại và chủ xử lý

1. Khầy: chọn/cấp SMTP; agent cấu hình và kiểm thư thật sau khi được giao. Không
   tự mua dịch vụ hoặc báo thư queued là đã gửi.
2. Browser local fixture đã kiểm 320 px/bàn phím và hai lỗi đã sửa; phiên Chrome
   production vẫn cần công cụ hỗ trợ URL policy nếu muốn kiểm trực tiếp.
3. Chủ host/agent trình duyệt: kiểm lại phản hồi cuối ChatGPT web khi host hoạt động.
4. G10: vận hành beta, backup ngoài VPS, quotas/tải và phục hồi; chưa thuộc triển khai này.

## Chỉ mục chứng cứ và giới hạn

[Báo cáo G9](../../Docs/reports/G9.md), [security review](../../Docs/reports/evidence/G9/security-review.md),
[verify r3](../../Docs/reports/evidence/G9/local-final-r3/verify.json),
[browser](../../Docs/reports/evidence/G9/browser-production.json),
[revoke](../../Docs/reports/evidence/G9/production-revoke.json),
[runbook](../../Docs/runbooks/G9-operations.md).

Không có số đo token/cost đầy đủ cho từng worker; không quy thành 0 hoặc cộng tổng.
Quyết định mở công khai cần chủ vận hành kiểm lại những cổng còn mở, không dựa riêng
vào kết quả build hoặc số test.
