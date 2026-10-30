# Contract G0 → G1, version 1.0.0

Ngày chốt: 30/10/2026 (Asia/Saigon). Trạng thái: **accepted_for_local_implementation**.
Đây là hợp đồng cần triển khai từ G1, không phải API/DB đã tồn tại. PoC ở `poc/g0`
không phải code production. Thay đổi phá tương thích phải tăng major và ghi ADR.

## 1. Stack, layout và quy ước

- CPython 3.12/Linux; lock khởi điểm `poc/g0/uv.lock`. Đã chạy cùng image:
  MCP chính thức 2.3.0, Authlib 1.9.1, FastAPI 0.162.0, Pydantic 2.14.2,
  SQLAlchemy 2.1.6, Alembic 1.20.1, psycopg 3.3.6; PostgreSQL 18 là mục tiêu G1,
  **chưa chạy database trong G0**. G1 tách dependency API/runner nếu cần và giữ lock.
- `apps/api`, `apps/web`, `packages/core`, `packages/plugin-adapters`, `runners`,
  `infra`, `tests`, `scripts`, `Docs/reports`. Không sửa/di chuyển `plugin_example`.
- API REST prefix `/api/v1`; UUID do server sinh; timestamp UTC RFC3339; trình bày
  cho Khầy theo Asia/Saigon. SHA-256 lowercase 64 hex. Số tiền giữ rounding Python
  gốc; không tính lại bằng JS, không tự sửa công thức/dữ liệu thuế.
- Schema máy đọc: [g0.schema.json](g0.schema.json), JSON Schema 2020-12. Các schema
  công khai cấm field thừa. `arguments` được kiểm tiếp bằng schema của ToolBinding.
- Không dùng protocol session hoặc JSON-RPC request ID làm project/job/idempotency key.

## 2. TenantContext và database

`TenantContext = {user_id, workspace_id, membership_id, role, scopes, request_id}`
là **đối tượng nội bộ**, tạo sau khi xác thực. Client không được tự cấp đối tượng này.
Session/token xác định user; workspace trong URL chỉ là lựa chọn. Tra membership còn
hiệu lực, rồi kiểm role + scope + quyền object trên mỗi thao tác.

G1 tạo `users`, `workspaces`, `memberships` và nền các bảng ở PLAN §3.2. Mọi bảng
riêng (plugin/version/install, project/artifact/stage, job/attempt/audit, connection/
grant/token/host profile) có `workspace_id NOT NULL`. PK có thể là UUID đơn, nhưng
phải thêm `UNIQUE(workspace_id,id)` và FK `(workspace_id,parent_id)` để cấm quan hệ
chéo tenant. Không áp workspace cho bảng identity toàn cục một cách máy móc.

RLS bắt buộc trên bảng riêng: cả `USING` và `WITH CHECK`, không có context thì deny.
Mỗi transaction runtime dùng `set_config('app.workspace_id', ..., true)` và user
context nếu policy cần. Kết thúc transaction là hết context; không dùng `SET` theo
session. Pool reused phải có test A → B → no context. Runtime role khác migration
owner, `NOSUPERUSER NOBYPASSRLS`, không sở hữu bảng; dùng `FORCE ROW LEVEL SECURITY`
như lớp bổ sung. Audit policy cũng cấm ghi giả workspace.

MVP seed đúng một owner/workspace; signup/invite disabled. Tests dùng ít nhất hai
workspace và kiểm DB, file, job, search, cache, download/export. Không xem fixture
token workspace B bị chặn trong PoC là bằng chứng RLS đã đạt.

Role sàn: viewer đọc; member chạy tool và ghi project; admin quản lý installation;
owner quản lý membership/kết nối. Mọi quyền còn bị scope và trạng thái plugin giới
hạn. G1 kiểm các primitive, G2 ánh xạ token, G3–G5 hoàn thiện endpoint tương ứng.

## 3. Bề mặt API thống nhất

| REST hoặc MCP | Input chính | Output/hành vi | Giai đoạn |
|---|---|---|---|
| `GET /health/live`, `/health/ready` | Không secret | liveness/readiness riêng; ready kiểm DB/migration | G1 |
| `GET /api/v1/me/workspaces` | Session | Membership mà user thật có quyền | G1/G2 |
| `POST /api/v1/workspaces/{ws}/invocations` / `hub_run_tool` | InvocationRequest | InvocationResult completed hoặc accepted + job_id | G4 |
| `GET .../{ws}/jobs/{id}` / `hub_get_job` | opaque ID | PublicJob đã bỏ lease/worker/internal path | G4 |
| `POST .../{ws}/jobs/{id}/cancel` / `hub_cancel_job` | ID, idempotency key | cancel_requested hoặc terminal hiện tại | G4 |
| `GET .../{ws}/artifacts/{id}` / `hub_read_resource` | ID + bounded range/cursor | Metadata hoặc stream đã kiểm quyền | G3 |
| `hub_search` | installation_id, query 1–2000 chars, top_k 1–20 | chunk_id, source resource ID, score, preview; đọc full qua resource | G4 |
| `POST .../{ws}/projects/{id}/stage-commits` | expected_revision, idempotency key, artifact IDs | Revision mới hoặc 409, transaction atomic | G5 |

JSON REST thành công `{data, request_id}`; lỗi `{error:{code,message,retryable},
request_id}`. HTTP 400/422 invalid input; 401 authentication; 403 insufficient scope;
404 object không tồn tại **hoặc ngoài tenant**; 409 revision/idempotency conflict;
429 quota; 503 runner not ready. Không đưa stack trace, token, host path ra client.
MCP trả typed structured output + content; lỗi nghiệp vụ dùng `is_error`, lỗi auth
trước dispatch; không bọc subprocess exit != 0 thành thành công. Không coi tool
annotations là permission. List phân trang cursor opaque, default 50/max 100.

InvocationRequest chỉ có binding_id, arguments, project_id tùy chọn,
idempotency_key. Cấm shell/module/image/mount/workspace_id trong payload. Client
chọn workspace qua transport/API context đã kiểm membership, không thêm vào args
của hàm tài chính. ToolBinding không nhận cập nhật từ caller.

## 4. ToolBinding và adapter Python

ToolBinding nội bộ bất biến:
`{id, workspace_id, plugin_version_id, mcp_name, adapter_id, image_digest,
input_schema, output_schema, limits, network_policy, file_policy}`.
Digest dạng `sha256:<64hex>`; adapter_id thuộc allowlist code đã review. Không nhận
tên module/command từ ZIP/client và không cài dependency lúc gọi.

Interface adapter:
`run(context, binding, arguments, job_workspace) -> AdapterResult`.
AdapterResult `{data, provenance, warnings}`; provenance chứa plugin tree SHA,
adapter ID/version, index SHA nếu search, ngày dữ liệu nguồn nếu có. Khi không biết
ngày nguồn phải trả unknown, không dùng ngày benchmark làm ngày hiệu lực thuế.
Exception nội bộ phân biệt validation/tool_exit/timeout/cancel/runtime_unavailable;
worker chuyển thành mã lỗi ổn định. Stdout dữ liệu tách stderr log; CLI dùng argv,
`shell=False`, check exit code. CLI hiện có output JSON trộn lời giải nên ưu tiên
gọi hàm Python, không `json.loads` cả stdout một cách máy móc.

Binding Finance–Tax dự kiến: `cit_estimate`, `cit_schedule`, `payroll_total`,
`fct_withhold`, `fct_grossup`, `tariff.calc`, `location_sim.simulate`,
`refs.calendar`, `refs.odi`, `search_corpus.search`. G0 mới smoke CIT/refs/tariff/
location/search, chưa đủ 30 parity cases G4. Cần validation hữu hạn/nonnegative;
`tariff.cif > 0` tránh chia 0; `location.provinces` phải thuộc danh mục, không âm
thầm bỏ tỉnh sai; không tự thay semantics gốc như `cit_override=0` bị bỏ qua.

Mount plugin và trusted index read-only. Job chỉ ghi namespace riêng; non-root,
cap_drop ALL, no-new-privileges, PID/CPU/RAM/timeout; default network none. Public
API và plugin runner không mount Docker socket. Worker đặc quyền chỉ dùng cấu hình
allowlist server, không chuyển nguyên payload client thành Docker args.

## 5. Job, idempotency và budget

Public states: `queued → running → succeeded | failed | cancelled`.
Queued được cancel trực tiếp. Running: ghi `cancel_requested_at`, worker dừng cả
process group/container, chỉ `cancelled` sau xác nhận dừng. Terminal bất biến;
cancel tới sau success trả success hiện tại. Heartbeat mỗi 10s, lease 30s, deadline
riêng; claim bằng transaction `FOR UPDATE SKIP LOCKED`, dùng fencing/attempt token.
Worker cũ hết lease không được commit output. `attempts` tăng khi claim, max 3 cho
lỗi hạ tầng có thể retry; không retry mù tác dụng ghi bên ngoài. Timeout là failed
với error.code=timeout. Crash chưa có output bền vững không được success.

Trong DB job cần: id/workspace/user, type, plugin_version/binding/project,
input_hash/idempotency_key, state, attempt/max_attempts, deadline_at,
lease_owner/lease_token/lease_expires_at/heartbeat_at, cancel_requested_at,
result_artifact_id, error_code, created/started/finished timestamps.
Succeed phải publish artifact đã checksum + job pointer trong transaction; blob
ghi trước/DB commit sau, orphan được dọn có grace period. Không expose lease qua API.

Idempotency UNIQUE `(workspace_id, operation, idempotency_key)`; hash canonical
validated input **và version/binding**. Cùng key/cùng hash trả cùng kết quả/job;
cùng key/khác hash trả 409. Giữ record ít nhất 7 ngày và luôn giữ khi job còn chạy.
Retention/migration không được làm biến mất active key. Stage commit thêm
expected_revision + transaction, không cho draft tự hoàn thành stage.

Budget đồng bộ 10s; chọn async trước khi có khả năng vượt budget, hoặc tiếp tục
chính job đang chạy rồi trả accepted; không khởi động tác dụng ghi lần hai.
Heavy toàn máy tối đa 1; nhẹ tối đa 2; queue 20/workspace, vượt trả quota, retry-after.
Tìm kiếm warm dùng một runner/index process theo version; không load matrix ở mỗi
API worker. Search/query đang tính cũng có peak tạm thời, phải tính vào memory cap.

| Lớp | Trần ban đầu cho G1/G4 | Ghi chú |
|---|---|---|
| calculator/refs | 256 MiB, 1 CPU, 30s | Chỉ chạy code đã duyệt |
| Finance search | 3 GiB, 2 CPU, 60s | 1 warm process, tuần tự query nặng |
| build index | 5 GiB, 4 CPU, 30 phút | **Mặc định build offline**, cùng locked image |
| API / PostgreSQL / worker / Caddy | 512 / 1024 / 256 / 128 MiB | Budget thiết kế, chưa benchmark Compose |

Runtime search + 2 light + các service trên + reserve OS 1024 MiB = 6528 MiB.
8 GB thập phân ≈ 7629 MiB, còn khoảng 1101 MiB; không cộng builder 5 GiB vào đó.
Không chạy builder trên VPS cùng search. Chỉ đổi sang build trên VPS sau đo full
Compose có chứng cứ. Xem [ADR-0001](../adr/0001-g0-runtime-and-gold8.md).

## 6. ArtifactStore và index tin cậy

Interface độc lập backend:
`put(ctx, byte_stream, media_type, expected_sha256?, max_bytes) -> ArtifactDescriptor`;
`get(ctx, artifact_id) -> descriptor`;
`stream(ctx, artifact_id, byte_range?) -> stream`;
`delete(ctx, artifact_id, expected_revision) -> deleted/tombstoned`.
put ghi temp trong filesystem cùng volume, tính hash/count, fsync+atomic rename,
sau đó DB pointer; get/stream/delete luôn lookup DB theo ctx rồi kiểm path.
Khóa blob do server sinh: `workspaces/<workspace_uuid>/blobs/<sha256>`.
Artifact UUID là public handle, storage key/absolute path là private. Không nhận
key do AI gõ làm quyền filesystem. Resolve path phải nằm trong storage root;
chặn traversal/symlink, namespace cross-tenant, range quá lớn; deletion chỉ khi
không còn pin/project/backup reference. Không giả R2 đã hoạt động.

Nguồn ZIP (khi có) và source tree bất biến; normalized catalog/index/full chunks
là artifact riêng. G0 **chỉ có folder**, không có hash ZIP gốc. Version identity
gồm manifest version + package SHA/revision; project pin immutable version.
Giữ `_backup_zh` trong source nhưng không index hoạt động.

Chỉ reviewed builder image được tạo `tfidf_vectorizer.pkl`, NPZ, metadata và
full-text JSONL. Không nạp pickle từ upload/source plugin. Manifest tin cậy chứa
source tree SHA, builder SHA, image digest, lock SHA, params, corpus file hashes,
output hashes/counts; lưu trong registry chỉ pipeline có quyền ghi, runner chỉ đọc.
Checksum đơn lẻ không chứng minh nguồn đáng tin nếu attacker sửa được cả manifest.
G0 manifest cục bộ chưa có đầy đủ provenance production; G4 phải bổ sung chuỗi trên.

Chỉ TXT/HTML được builder gốc xử lý; 39 PDF giữ nguyên, coverage phải hiện rõ.
Search result preview ≤200 chars không phải full source; ánh xạ chunk handle → text,
source resource được sinh đồng thời trong cùng build và kiểm số hàng/preview.
**ID gốc bị trùng giữa TXT/HTML cùng stem:** G0 đo 83.736 rows nhưng chỉ 49.488
ID gốc khác nhau. Sidecar G0 dùng cặp `(source_file, id)` (83.736 cặp duy nhất),
không lookup `id` đơn. G4 mint chunk handle theo version/index digest + source_file
+ chunk_index; giữ original id trong provenance, không sửa thuật toán TF-IDF gốc.
MANIFEST nguồn có 1 PDF thiếu và 535 size mismatch: G3 ghi source warnings/preview,
không tin MD5/size cũ làm hash source hiện tại, không tự tải bù hoặc sửa gói gốc.
Cache key nội bộ có version/index digest; quyền installation/workspace kiểm trước
mỗi lần dùng, không coi shared immutable matrix là quyền đọc của tenant khác.
Embedding chưa nghiệm thu, không cài sentence-transformers/tải model trong MVP.

## 7. OAuth/MCP: phần đã chứng minh và phần phải viết tiếp

Wire PoC chạy MCP 2.3.0 qua TCP với pin `2026-07-28`, modern metadata/header,
`server/discover`, typed tool, không initialize/session header; chứng cứ G0.
SDK có resource server/verifier/discovery, **không cung cấp login/token issuer**.
Authlib cung cấp grant/PKCE core; đã viết ASGI bridge riêng trong `auth_poc.py`:
buffer form/query có giữ duplicates → OAuth2Request/Payload → grant response →
Starlette response; hook query client/save code/save token/user và S256-only.

G2 cần thay dict memory bằng transaction DB với consume code atomic; login/password
hash/session/CSRF/consent/rate limit thật; refresh rotation/replay family revocation;
revoke/scope step-up; resource/audience/issuer binding và registration theo host.
PoC chỉ pre-registered client và owner pre-approved, không phải OAuth production.
Loopback HTTP exception chỉ trong smoke child process, không dùng trong deployment.
Tất cả MCP route aliases/mounts phải chung quyền. Custom HTTP route SDK không tự
được bảo vệ; route riêng chỉ public health/discovery/login hoặc tự kiểm auth.
ASGI host lifespan bắt buộc enter `mcp.session_manager.run()` khi mount SDK.

## 8. Điều kiện bàn giao G1

G1 dùng contract này để tạo nền và migrations, không tiếp tục triển khai G2–G8.
Tạo `scripts/verify.ps1 -Stage G1` và `scripts/verify.sh G1` gọi kiểm tra trong
Compose. Test thật: dựng checkout sạch, migrations, restart vẫn còn dữ liệu,
role runtime không bypass RLS, A không đọc/ghi DB/file B, foreign-key cross-tenant
bị chặn, pool không giữ tenant cũ, path traversal/symlink bị chặn, private health
không lộ secrets. Ghi Docs/reports/G1.md với lệnh và evidence. G0 không mua VPS,
không sửa DNS/R2, không thử tài khoản cloud/model trả phí.
