# G5 — xác minh và sửa phản hồi PR #1

Ngày 31/10/2026, Asia/Saigon. Trạng thái: **in_progress — targeted tests passed, chờ full regression**.
Theo [comment của Khầy](https://github.com/sontakmtp-cell/goodmcp/pull/1#issuecomment-6536961901).
Không merge PR, không gọi LLM API, không sửa plugin mẫu hoặc công thức Python.

## 1. Xác minh lỗi trên commit b025be6

Cả ba phản ánh đúng. Chạy trên PostgreSQL/ArtifactStore thật trong Compose project
riêng `goodmcp-g5-review-repro-d0cfc7ff`, không dùng database local của Khầy:

| Phản ánh | Chứng cứ trước sửa |
|---|---|
| Rollback tiến về phía trước | 5 test rollback đích tương lai thất bại vì code chấp nhận; case cùng stage đã chặn đúng |
| Summary vượt 256 KiB | Chuỗi checkpoint Unicode hợp lệ lỗi ở revision 23 với `Project file exceeds 256 KiB` |
| Project cũ lead NULL không ghi được | Lead fixture NULL; thử cập nhật lead bị trigger từ chối SQLSTATE `42501`; service yêu cầu đúng lead nên không ai ghi được |

[review-reproduction.json](evidence/G5/review-reproduction.json) giữ kết quả baseline;
[review-targeted.json](evidence/G5/review-targeted.json) giữ **12 targeted tests và
22 kiểm tra migration đã đạt** sau sửa.

## 2. Thay đổi

- `workflows.py`: rollback chỉ về stage trước; summary xoay segment trước trần
  256 KiB UTF-8, giữ nguyên blob/archive/handle cũ và transaction/idempotency.
  Project lead chưa rõ trả thông báo conflict có thể xử lý, thêm read flag
  `lead_assignment_required`.
- `0006_g5_review.py`: migration nối tiếp, giữ nguyên `0005_g5`; lưu bằng chứng
  assignment immutable/FORCE RLS, cập nhật lead NULL có kiểm soát và audit nguyên
  transaction. Không suy chủ sở hữu từ workspace owner hoặc contributor.
- `project_admin.py`: operator CLI list-unassigned/assign-lead với mapping,
  owner confirmation và evidence tường minh. Không có endpoint public hoặc quyền
  runtime để tự nhận lead, không cho đổi pin/lead đã có.
- `test_workflows.py`: từ chối rollback sai hướng, giữ context khi rollback thật;
  75 commit lớn gồm tiếng Việt/emoji, đọc đủ lịch sử, retry; lỗi checkpoint đúng
  lúc xoay summary phải rollback archive/pointer và giữ byte legacy chính xác.
- `migration_g5.py`, `verify.py`: tạo database test riêng, migrate tới G4, seed
  project/artifact/stage history cũ, nâng cấp thật rồi kiểm assignment hợp lệ,
  từ chối thiếu proof/foreign/viewer/inactive/non-owner, chống runtime claim,
  giữ pin/revision/state/bytes/history và ghi tiếp sau xác nhận.
- `wire_g5.py`: HTTP rollback tiến bị từ chối, chuỗi summary trên 512 KiB qua HTTP
  và đọc archive/handle cũ sau recreate. `test_g1.py` thêm RLS cho bảng mới;
  `version.py` chuyển revision tới `0006_g5_review`, stage vẫn G5.
- [Contract G5](../contracts/G5-workflows.md): mô tả segment history và runbook
  gán lead project cũ. Input/API hiện có giữ nguyên; không xóa lịch sử đã lưu.

## 3. Toàn bộ kiểm thử G1–G5

Đang chuẩn bị chạy `python scripts/verify.py --stage G5 --evidence-dir Docs/reports/evidence/G5-review` từ **git archive** của
commit sửa lỗi. Harness chạy fresh install, migration G4 có dữ liệu cũ, 47 parity
cases, pytest, HTTP/OAuth/MCP, timeout/cancel/crash/fencing, tenant isolation,
recreate/resume và health failure/recovery; cleanup đúng project kiểm thử.

Không coi targeted pass là full regression pass. Kết quả cuối và commit được
kiểm sẽ được ghi tại đây cùng evidence trước khi push lên PR.

## 4. Vận hành

Chưa tự gán lead cho project thực tế nào. Mapping chưa được xác minh phải giữ NULL.
CLI dựa trên admin credential và xác nhận operator đã kiểm; không chứng thực một
user ID hoặc nội dung evidence bằng API/LLM. Chưa chuyển lead đã có hoặc tự ghim
plugin cho project chưa có pin. UI, host cloud và production acceptance vẫn ở các
giai đoạn sau; không biến kết quả local thành live-host pass.
