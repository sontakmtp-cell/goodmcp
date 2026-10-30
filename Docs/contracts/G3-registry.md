# G3 → G4: local registry v1

G1 TenantTransaction/ArtifactStore và G2 bearer là nền. Migration mới `0003_g3`;
không sửa schema/migration G1/G2 đã phát hành. `hub:read` cho catalog; `hub:write`
**và owner/admin** cho upload/install. Scope mới cần consent mới, không nâng grant cũ.
Viewer không cấp scope ghi. Không có runner hoặc adapter nghiệp vụ trong G3.

## REST

Prefix `/api/v1/workspaces/{workspace_uuid}`. Workspace phải đúng OAuth grant.
Mọi UUID khác tenant trả 404, JSON theo `{data,request_id}` hoặc `{error,request_id}`.

| Method/path | Input → output |
|---|---|
| POST `/uploads` | `{bytes,sha256,idempotency_key}` → upload UUID, part_size=8388608, expected_parts, received_parts |
| GET `/uploads/{id}` | Resume/status, preview, plugin_version_id; không trả lease/path |
| PUT `/uploads/{id}/parts/{n}` | Raw bytes + `X-Content-SHA256`; part bắt đầu 0, phần cuối đúng số byte còn lại; retry cùng hash idempotent |
| POST `/uploads/{id}/complete` | Đủ parts → 202 queued; worker kiểm whole hash/ZIP, không giữ request chờ scan |
| POST `/uploads/{id}/cancel` | Hủy uploading/queued; scanning trả 409 |
| PUT `/installation` | `{version_id,enabled,expected_revision}`; revision 0 khi cài lần đầu, sau đó tăng; stale → 409 |
| GET `/plugins` | cursor UUID opaque, limit 1–100 (default 50), items + next_cursor |
| GET `/installations/{id}` | Enabled version preview/hashes |
| GET `/installations/{id}/versions` | Lịch sử immutable và số project pins; phân trang |
| GET `/installations/{id}/resources` | Active file handles, logical paths, hash/bytes; phân trang |
| GET `/installations/{id}/resources/{resource_id}` | offset byte + length 1–65536; base64, next_offset; không render HTML/PDF |
| GET `/versions/{id}/export` | Owner/admin, exact uploaded ZIP; attachment + nosniff + CSP sandbox |
| GET `/artifacts/{id}` | Owner/admin, G1 blob streaming, không nhận đường dẫn/key |

HTTP body tối đa 8 MiB; ZIP 1 GiB, expanded 3 GiB, 10.000 files, ratio 200:1.
Tối đa 3 upload đang mở/workspace, reserved 4 GiB; kiểm admission quota 20 GiB
tổng artifact metadata với dự phòng 4× dung lượng ZIP. Một worker local scan tuần tự.
Upload hết hạn sau 24 giờ; lease scan 30 phút, retry tối đa 3 lần. Đây là admission
limits cố định khởi điểm, chưa có UI điều chỉnh quota hoặc GC tự động.

Worker chỉ có runtime secret. Function `hub_claim_import()` cố định, SECURITY
DEFINER, search_path cố định, không PUBLIC EXECUTE, chỉ trả task được DB xếp hàng
cho owner/admin còn active. Chỉ phục hồi task hết lease; hoàn tất catalog trong
một transaction. Crash rollback không thay installation đang phục vụ. Blob orphan
có thể còn sau rollback; không xóa blob/pin trong G3. Thao tác đã nhận vào hàng chờ
tiếp tục theo membership, không phụ thuộc tuổi access token của request ban đầu.

## Source identity và catalog

`source_sha256` của version = SHA-256 ZIP nguyên byte; identity DB là
`(workspace, package, manifest_version, source_sha256)`. Cùng version số nhưng ZIP
khác → revision UUID riêng. ZIP giống → reuse version. ZIP metadata khác cũng có
revision riêng dù canonical tree giống. Original ZIP và mỗi source file đi qua
ArtifactStore; nguồn không bị giải nén ra đường dẫn do ZIP cung cấp.

`tree_hash_format=goodmcp-tree-v1`: SHA256 của byte prefix `goodmcp-tree-v1\n`,
tiếp theo mỗi file sắp theo **UTF-8 path bytes**, mỗi dòng
`path + NUL + lowercase_sha256 + NUL + decimal_bytes + LF`.
Độc lập Windows/Linux; đây là format mới, không thay hash inventory lịch sử G0.

Validator nhận root `plugin.json`, `.codex-plugin/plugin.json`,
`.codebuddy-plugin/plugin.json`, hoặc một wrapper folder duy nhất. Field chung
root/overlay phải khớp. Entrypoints skills/agents phải tồn tại nếu khai báo;
profile/skill giữ nguyên body. Không import module, shell, pip, pickle, NPZ,
HTML script hay URL nào lúc scan. Không tạo ToolBinding executable từ manifest.
License unknown và dữ liệu nguồn sai MANIFEST hiển thị warning; private mặc định.

`_backup_zh` giữ trong source nhưng inactive. File chứa secret bị từ chối;
**ngoại lệ policy cho trang HTML chụp về:** phát hiện credential → quarantine,
giữ trong ZIP private, inactive resource, không đọc qua MCP. Policy này áp dụng
mọi plugin, không allowlist tên ba mẫu. Không đưa nội dung credential vào preview,
log hoặc report. Export nguồn private chỉ owner/admin. Heuristic secret detection
không phải cam kết phát hiện mọi loại secret; không mở upload công khai.

`plugin_versions`, skills/agents/resources immutable bằng DB trigger. Installation
thay đổi độc lập và không di chuyển project pin. Giữ toàn bộ lịch sử trong G3;
chưa tự thu gọn về 3 bản chưa ghim vì cần bộ đếm backup/pin/GC ở giai đoạn vận hành.
Không xóa bản cũ để làm quota hoặc test qua.

## MCP G4 sử dụng

SDK official 2.3.0 / protocol 2026-07-28. Readonly:
`hub_list_plugins`, `hub_open_plugin`, `hub_get_skill`, `hub_get_agent`,
`hub_list_resources`, `hub_read_resource` (và tool G2 `hub_get_workspace`).
Các tool luôn kiểm enabled installation, workspace và resource/version binding.
UUID là handle; body role là plugin content, không phải policy của hệ thống.

G4 lấy source/index qua Registry + ArtifactStore trong tenant transaction, không
lấy storage_key từ client. Chỉ reviewed pipeline mới tạo index tin cậy mới; index
supplied vẫn untrusted. Không sửa công thức Python hoặc chuyển TF-IDF sang FTS/JS.
Giữ cảnh báo MANIFEST, PDF chưa indexed/OCR, HTML quarantine. G2 host cloud gate
vẫn blocked, không suy khả năng host từ SDK local.

SDK reference: [Tools / typed schemas](https://py.sdk.modelcontextprotocol.io/servers/tools/).
