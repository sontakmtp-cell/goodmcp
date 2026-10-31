# G5 — xác minh và sửa phản hồi PR #1

Ngày 31/10/2026, Asia/Saigon. Trạng thái: **passed (local, clean git archive)**.
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

Đã chạy:

```powershell
python scripts/verify.py --stage G5 --evidence-dir Docs/reports/evidence/G5-review
```

Source **2609bffd44807f8a1965f45e1a04f962e9551e61**, mode **clean_git_archive**,
run `20261031T011953Z-a72508`. 77 hash file của source archive được giữ trong
[source-manifest.json](evidence/G5-review/source-manifest.json). Thời gian cộng
các lệnh harness **425,45 giây**; không coi đây là benchmark production.

| Kiểm tra cuối | Kết quả |
|---|---|
| Toàn bộ pytest PostgreSQL/ArtifactStore G1–G5 | **199 passed** |
| Database G4 có project/artifact/decision cũ → migration mới → recovery có proof | **22/22** |
| G5 HTTP/OAuth/MCP, gồm rollback sai hướng và tổng summary trên 512 KiB | **41/41** |
| Sau recreate, đúng pin/revision/checkpoint và summary archive/handle cũ | **19/19** |
| Python gốc/container parity G4 | **47/47** |
| G1–G4: tenant/RLS/pool/storage, import/version/ZIP export, OAuth/negative tokens, document lookup, queue/cancel/timeout/crash/fencing | **Pass** |
| Fresh install, migration idempotent, DB outage/recovery, secret/port boundaries | **Pass** |
| Cleanup hai Compose project kiểm thử và volume của chúng | **Đã dọn, không đụng dữ liệu local thật** |

[verify.json](evidence/G5-review/verify.json) và
[verify-console.txt](evidence/G5-review/verify-console.txt) giữ toàn bộ lệnh/exit
code/kết quả. Các phần đọc nhanh: [upgrade.json](evidence/G5-review/upgrade.json),
[wire-tests.json](evidence/G5-review/wire-tests.json), [resume.json](evidence/G5-review/resume.json).
Kết quả G5 ban đầu trong `evidence/G5` được giữ để đối chiếu; không ghi đè bằng
chứng của lần này. 832 file plugin mẫu vẫn đúng byte/SHA-256 G0:
[plugin-unchanged.json](evidence/G5-review/plugin-unchanged.json).

## 4. Vận hành

Đã chạy `python scripts/local.py up`, nâng stack persistent lên **0006_g5_review**;
HTTP readiness vẫn **G5/ready**, một user/workspace, ba plugin enabled, 16 vai trò.
Bootstrap owner `created=false`; số project/lead trước và sau giữ nguyên, bảng
assignment không phát sinh bản ghi. [local-smoke.json](evidence/G5-review/local-smoke.json).

Không tự gán lead cho project thực tế nào. Mapping chưa được xác minh phải giữ NULL.
CLI dựa trên admin credential và xác nhận operator đã kiểm; không chứng thực một
user ID hoặc nội dung evidence bằng API/LLM. Chưa chuyển lead đã có hoặc tự ghim
plugin cho project chưa có pin. UI, host cloud và production acceptance vẫn ở các
giai đoạn sau; không biến kết quả local thành live-host pass.
