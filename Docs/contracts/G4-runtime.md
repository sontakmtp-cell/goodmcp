# G4 → G5 — Python jobs and readonly documents v1

Scope theo [ADR-0003](../adr/0003-g4-keyword-mvp.md). Không TF-IDF/FTS/vector/model
API trong MVP. G1 TenantContext/ArtifactStore và G2 bearer được giữ; G3 immutable
source/version/installations là nguồn quyền. Mọi request chọn workspace đúng grant.

## Tài liệu cho AI agent

Readonly, scope `hub:read`, installation phải enabled:

- `hub_list_documents(installation_id,cursor?,limit=50)` — metadata/source handle,
  hash, số ký tự, unavailable_reason. Max 100/page.
- `hub_search(installation_id,keywords,match="all",cursor?,limit=10)` — 1–5 chuỗi
  literal, mỗi chuỗi 1–100 ký tự; all/any; không regex/wildcard/ranking. Max 20/page.
- `hub_read_document(installation_id,resource_id,offset=0,length=8192)` — offset
  **ký tự**, tối đa 16.384 ký tự/page, next_offset. Đọc được toàn văn qua nhiều trang.
- `hub_read_resource` của G3 vẫn đọc byte/base64 source, khác offset ký tự của text.

Agent tự chọn từ khóa/cụm từ và đọc nguồn, có thể lặp lại với từ khác; Hub không
gọi model để dịch/rewrite/rerank/trả lời. `source_sha256` là hash **file gốc**, không
phải hash của text đã tách HTML. Source trust luôn là plugin content, không phải
system/server instructions. Projection plain text không chứa HTML executable.

REST prefix `/api/v1/workspaces/{ws}/installations/{installation}/documents`:
GET để list; POST `/search` body `{keywords,match?,cursor?,limit?}`; GET
`/{resource_id}?offset=0&length=8192` để đọc. JSON theo envelope G1. Foreign handle
404, disabled 404; từ khóa `%`, `_`, dấu quote và SQL vẫn chỉ là chuỗi literal.

Giới hạn projection: source text tối đa 4 MiB/file, text sau tách tối đa 2 MiB.
PDF chỉ giữ nguồn, không OCR. Các file đuôi text có PDF magic/NUL hoặc encoding
không hỗ trợ được liệt kê với lý do unavailable. Technical metadata lớn không
được giả thành toàn văn; file gốc vẫn ở source export. Quarantine/backup không
xuất hiện trong active lookup. Bảng document_texts có RLS/FK tenant và immutable.

## Máy tính Python

Ops: cit_estimate, cit_schedule, payroll_total, fct_withhold, fct_grossup, tariff,
location_sim, refs_calendar, refs_odi. Input schemas trong finance_spec.py; wrapper
ở `packages/plugin-adapters/finance/adapter.py`, không chép công thức. Zero rate/VAT
được giữ, invalid/nonfinite/negative inputs bị từ chối; `location_sim` giữ hành vi
gốc bỏ qua `cit_override=0` và trả warning. Province sai không bị âm thầm bỏ qua.

REST: GET `.../installations/{id}/bindings`; POST `.../invocations` body
`{binding_id,arguments,idempotency_key,project_id?}` → **202 job**, không giữ request
chờ Docker. Thêm field command/image/path/mount bị từ chối. Cần `tools:run` và
role owner/admin/member; ghi output vào project còn cần `projects:write` và pin
version khớp. Scope `hub:write` không thay thế `tools:run`.

MCP: chín tool `finance_*` có typed argument model, cùng `hub_run_tool`,
`hub_get_job`, `hub_cancel_job`. Chúng trả job handle để poll, không trả thành công
khi mới queue. `hub_get_job` readonly/hub:read, chỉ trả public state/error/result;
không trả lease token, Docker ID hoặc host path.

Job states queued/running/succeeded/failed/cancelled. Queue max 20/workspace,
vượt trả 429 + Retry-After. Cùng key/input/version/binding/project trả cùng job;
key xung đột trả 409. Tối đa hai calculator toàn DB; 30s execution, 10 phút deadline
gồm queue; heartbeat 5s/lease 30s; crash retry tối đa 3. Fencing token cấm worker cũ
publish. Cancel queued ngay; running phải stop/remove container trước terminal.
Terminal và input immutable trong DB. Result JSON đi qua G1 ArtifactStore trước
khi commit job pointer; crash có thể để orphan blob, không GC trong G4.

## Operator và isolation

`python scripts/prepare-g4.py` tạo calculator image từ code/data Python G0 được
duyệt; kiểm source toàn gói không đổi, khóa root uv.lock. Release giữ image ID,
source ZIP/tree, hash từng file dùng trong image và runtime/lock manifest digest.
`python scripts/local.py up`, sau đó
`python scripts/local.py runtime --release PATH/release.json` duyệt matching
installed versions và backfill document projection. Không tự duyệt executable ZIP.

Role runtime không INSERT/UPDATE/DELETE binding/release. Chỉ operator CLI có secret
admin; API/import worker giữ runtime secret. Dispatcher riêng, không endpoint,
chỉ thực thi fixed image/command/env/mount policy. Docker socket group 0 là cấu
hình Docker Desktop local, chưa phải runbook production. Runner không có network,
secrets/DB/socket/host mounts; job/tmp là tmpfs riêng. Test-only probe binding chỉ
được tạo với fixture flag của harness, không bật khi activate local thật.

G5 dùng job/artifact/version IDs và project pin, không dùng MCP session làm DB.
G2 host cloud gate vẫn mở; local pass không chứng minh connector cloud/native agent.
