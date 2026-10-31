# G5 → G6 — durable projects / OPC workflow v1

Ngày 31/10/2026, Asia/Saigon. Dùng tenant transaction/RLS/ArtifactStore G1,
bearer G2, nguồn bất biến G3 và Python job G4. Hub không gọi LLM API.

## Quyền và phiên bản

Mọi route ở `/api/v1/workspaces/{ws}`; `ws` phải khớp grant và membership còn
active. Đọc dự án cần `hub:read projects:read`. Ghi cần
`hub:read hub:write projects:write` và role owner/admin/member. Scope ghi không
tự cấp scope đọc. Bật/tắt/cài plugin vẫn là quyền admin G3.

Người tạo dự án là lead, lấy từ identity đã xác thực, không nhận `role=lead` hoặc
`lead_user_id` của client. Chỉ lead này ghi output và trạng thái chung. Brief cho
chuyên gia có `specialist_write_scope=[]`: trả đề xuất về lead, không cấp quyền
ghi qua câu lệnh trong tài liệu. MVP chưa có chuyển lead/delegated writer.

Project ghim `plugin_version_id` bất biến; mỗi file version có cùng pin qua FK.
Nâng installation không đổi pin project. Workflow/nguồn được đọc theo pin cũ khi
package còn enabled, không âm thầm chuyển sang phiên bản active mới. Disable
package chặn prepare/save/commit/source, nhưng dữ liệu project vẫn đọc được để
không mất công việc. Python job vẫn dùng binding/version đã được operator duyệt;
khác pin project bị G4 từ chối. Không tự chạy lại Python khi commit.

## REST / MCP

REST trả `{data,request_id}`, lỗi theo G1; MCP trả structured `{data}` và content.
Lỗi nghiệp vụ MCP có `is_error`; text bắt đầu bằng mã như `conflict:` hoặc
`forbidden:`. JSON input cấm field thừa. UUID không phải đường dẫn file.

| REST | MCP | Dữ liệu |
|---|---|---|
| POST `/projects` | `hub_open_project(payload)` | installation_id, name, idempotency_key, timezone (Asia/Saigon) |
| GET `/projects` | `hub_list_projects(cursor?,limit=50)` | Project handles; UUID cursor, max 100 |
| GET `/projects/{id}` | `hub_read_project(project_id,cursor?,limit=50)` | Pin, revision, checkpoint, resume_stage, latest file handles, legacy_conflicts; cursor logical path |
| POST `/projects/{id}/artifacts` | `hub_save_artifact(project_id,payload)` | expected_revision, idempotency_key, logical_path, content, media_type |
| POST `/projects/{id}/stage-commits` | `hub_commit_stage(project_id,payload)` | CommitStage bên dưới |
| GET `/projects/{id}/files/{file_id}` | `hub_read_project_file` | offset ký tự, length default 16384/max 32768; content/hash/next_offset |
| GET `/projects/{id}/file-history?path=...` | `hub_project_file_history` | File revision cursor từ 0, default 50/max 100 |
| POST `/host-profiles` | `hub_report_host(payload)` | Snapshot append-only, không idempotent; trả host_profile_id |
| GET `/projects/{id}/workflow?host_profile_id=...` | `hub_prepare_workflow` | Brief, role body, 9-role roster, pin, stage, source handles, execution mode |
| GET `/projects/{id}/resources/{resource_id}` | `hub_read_project_resource` | Source của pin, offset byte; base64, hash/next_offset; max 32768 byte |

Open phát hiện workflow OPC bằng skill `opc-orchestrator` trong version. Plugin
khác dùng `documents-v1`, vẫn tạo project/lưu mã hoặc tài liệu được; không ép
Godot/Finance/plugin thứ tư chạy workflow OPC. Logical prefix dùng chung
`opc-doc/outputs/` để giữ hợp đồng storage; không thực thi nội dung đã lưu.

Prepare chỉ trả brief và handle; không tạo job hoặc tự gọi provider. Client cần
phân trang read_project để lấy thêm output khi có next_cursor; không gửi toàn bộ
project/corpus vào context. `hub_read_project_resource` đọc trực tiếp nguồn đã ghim.

## Save và commit

`SaveArtifact`: chỉ output của bước đang resume; 256 KiB UTF-8/file,
media_type text/markdown, text/plain hoặc application/json. JSON phải parse được;
Markdown/text không rỗng. Complete còn kiểm đủ tên output được khai báo trong
mục `Đầu ra` của skill đã ghim (trừ file ghi “khi cần”), mẫu timestamp 07/08,
scorecard.json đủ tám category/field, target-segment.json đủ trường và điểm
1–5/null với tổng hợp lệ. Đây là kiểm cấu trúc/byte, không xác nhận chất lượng
nội dung kinh doanh. Save luôn draft, tăng revision, giữ checkpoint cũ. Không cho
ghi trực tiếp state, summary, review hoặc output bước tương lai.

`CommitStage`:

```json
{
  "expected_revision": 1,
  "idempotency_key": "stable-client-operation-id",
  "stage": "01-resource-audit",
  "action": "complete",
  "artifact_ids": ["ARTIFACT_UUID_FROM_SAVE"],
  "summary": "Đã xác nhận kiểm kê; nhu cầu thị trường vẫn chưa kiểm chứng",
  "authorization": "Tham chiếu xác nhận thật của người dùng",
  "decisions": [], "assumptions": [], "reviews": [],
  "skipped_stages": [], "open_questions": [],
  "checkpoint_extra": {}, "preferences": {}
}
```

`artifact_ids` là ID artifact, không phải ID project_files; phải thuộc chính
project/version/bước hiện tại và là revision mới nhất. Complete cần output đã lưu
và authorization không rỗng. Hub ghi nguyên văn tham chiếu xác nhận; không có
provider/LLM để chứng thực nội dung tham chiếu có thật. Client lead chịu trách nhiệm
chỉ commit sau xác nhận đã có. Không suy xác nhận từ role tự khai.

Mọi lần save/commit khóa hàng project, kiểm expected_revision rồi lưu bằng một
transaction. Cùng operation/key/payload trả đúng response đã lưu, kể cả sau khi
revision tăng; cùng key khác payload hoặc revision cũ trả 409 và không ghi đè.
Open key gắn workspace; save/commit key còn gắn project và loại operation.

Commit đọc/kiểm blob, giữ revision cũ, merge history/preferences, append summary,
ghi current-stage.json cuối cùng, rồi lưu stage_commit và revision trong cùng
transaction. Thất bại rollback toàn bộ metadata/checkpoint. Blob đã publish trước
rollback có thể thành orphan; không GC ở G5. Không gọi là rollback filesystem.
History, file versions, stage commits và pin được bảo vệ ở DB; file labels không
trở thành đường dẫn vật lý. Storage key vẫn do ArtifactStore server sinh.

Decision: id, stage, decision, evidence[], authorization. Assumption: id, statement,
status, evidence[]. Review: id, review, evidence[]. Server thêm timestamp theo timezone
dự án. Record cùng ID/nội dung không nhân đôi; cùng ID khác nội dung trả conflict,
muốn sửa phải thêm record ID mới để giữ lịch sử. Object legacy có đúng một list
`decisions/assumptions/reviews`, `records` hoặc `items` được giữ nguyên hình dạng
và key lạ. JSON hỏng/shape mơ hồ giữ byte cũ và từ chối ghi, không reset về rỗng.
Assumption mặc định unverified; supported/rejected/inconclusive cần evidence không
rỗng. Plan được xác nhận không tự đổi giả thuyết thành supported; chất lượng/chân
thực evidence vẫn thuộc lead và người dùng.

## Chuyển bước, legacy và tiếp tục chat

Mặc định 01 → 02 → 03 → 04 → 05 → 06 → execution. Complete 06 không tự chạy
07/08. Execution/07/08 phải có next_stage tường minh. Draft/checkpoint không chuyển
bước. Skip yêu cầu destination, và từng bước bị bỏ qua có stage/reason/authorization/
missing_evidence. Rollback dùng destination tường minh và đánh dấu downstream stale;
giữ lịch sử cũ, chỉ xóa stale của bước vừa được xác nhận lại.

New checkpoint numbering_version=2. completed resume next_stage; draft/in_progress
resume stage. Hỗ trợ semantic alias 06-mvp(-design), 07-conversion-loop,
08-asset-ops, 09-dashboard-review; số trần như `06` bị từ chối. Không sửa file
legacy; checkpoint mới giữ key lạ và previous_revision. Nếu canonical/historical
confirmed files cùng tên có hash khác nhau, read_project báo legacy_conflicts và
commit bị chặn để không tự chọn một kết quả. G5 chưa có giao diện hòa giải dữ liệu
legacy xung đột; cần operator xử lý có chủ đích ở giai đoạn tiếp theo.

Output 07/08 mới dùng filename `[prefix-]YYYYMMDD-HHmmss[-counter].md/json/txt`, theo timezone
dự án do client chọn; trùng tên yêu cầu counter. Revision cũ vẫn có timestamp/id,
không rename hoặc xóa output cũ. Lần đầu execution material thuộc 05/06.

Chat mới: xin grant có project scopes → hub_list_projects → hub_read_project →
hub_prepare_workflow → đọc file/nguồn bằng handle và cursor → làm tiếp resume_stage.
Không dùng MCP session ID làm database hoặc khóa retry.

## Host profile và model

Report gồm name, file_access/tools/subagents/model_selection (bool),
available_models[], requested_model?, reported_model?, evidence. Tất cả đều mang
nhãn `caller_reported_not_verified`, có thời điểm server nhận. Không biết thì unknown.
Chỉ người báo mới dùng profile đó trong prepare; workspace khác bị 404.

Không subagent/không biết: `single_assistant_sequential`; có khả năng do caller báo:
`native_delegation_available`. Cả hai đều `execution_status=not_started` và
`server_invokes_models=false`. Host tự dùng native selectors khi được cho phép;
phụ thuộc workflow vẫn chạy tuần tự, lead ở chat chính, chuyên gia trả draft/evidence/
assumptions/blockers. Không xem capability là bằng chứng delegation đã chạy.

preferred_model lấy từ roster nguồn đã ghim; requested_model chỉ có selector khi
model_selection và available_models có đúng tên. Thiếu selector phải báo fallback,
không tự đổi tên Codex thành API ID hãng khác hoặc hạ Sol sang Luna. reported_model
chỉ là **host_current_assistant do caller báo**, specialist_reported_model luôn
unknown cho tới khi có evidence thực tế ở host; Hub không suy model con từ model chính.
Model chính do host/người dùng kiểm soát. G5 không nghiệm thu native agent/cloud
inference; gate G2/G7 vẫn tách riêng.
