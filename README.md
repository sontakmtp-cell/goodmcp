# goodmcp-hub — Python, tài liệu và dự án local G5

Hub quản lý plugin theo workspace, giữ công cụ Python. **G5 thêm dự án ghim phiên
bản, output có lịch sử, checkpoint OPC và brief theo khả năng host** trên nền
Python/tài liệu G4. Chat mới tìm/mở dự án và tiếp tục đúng bước; draft không tự
hoàn thành, ghi cạnh tranh bị báo conflict. AI đang chat tự điều phối; Hub không gọi
LLM API, xây TF-IDF hoặc FTS. Chưa có UI
quản trị, chưa deploy/live-test connector cloud; gate host G2 vẫn mở.

Hợp đồng G5 cho client/UI: [G5-workflows.md](Docs/contracts/G5-workflows.md).
Luồng MCP: xin scopes `hub:read hub:write projects:read projects:write` →
`hub_open_project` → `hub_prepare_workflow` → `hub_save_artifact` (draft) →
`hub_commit_stage` sau xác nhận người dùng. Chat sau dùng `hub_list_projects` và
`hub_read_project`; đọc file/nguồn theo handle. Brief không phải subagent đã chạy.

## Chạy local

Cần Docker Desktop Linux/Compose v2 và Python 3.12+ trên host. Python host chỉ dùng
stdlib; dependency ứng dụng được cài từ lockfile trong image. Tại repo root:

```powershell
python scripts/local.py up
```

Mở [login local](http://127.0.0.1:18080/auth/login),
[readiness local](http://127.0.0.1:18080/health/ready) hoặc
[liveness local](http://127.0.0.1:18080/health/live).
Chỉ Caddy publish port **127.0.0.1:18080**; API/database không publish port. DB và
file nằm trong named volumes của project `goodmcp-local`, giữ qua restart/recreate.

```powershell
python scripts/local.py status
python scripts/local.py down
```

`down` giữ dữ liệu; không chạy `down --volumes` trên stack có dữ liệu cần giữ.
Lệnh `up` chạy migration và bootstrap owner một lần, chạy lại không nhân đôi.
Mặc định owner email là
`owner@local.invalid`; password nằm ở `.local/secrets/owner_password`, không đưa lên
Git/chat. Có thể đặt `HUB_OWNER_EMAIL` **trước bootstrap lần đầu**. Đổi port cần
đặt cả `HUB_PORT` và `HUB_PUBLIC_BASE_URL`; mọi port vẫn bind loopback.

## Secret và phân quyền

`scripts/setup-local.py` tạo password ngẫu nhiên ở `.local/secrets/` (Git ignored),
không in giá trị và không ghi đè file có sẵn. Không đưa thư mục này lên Git hoặc
gửi cùng log. Compose chỉ mount từng secret cho service cần nó:

| Service | Secret | Quyền |
|---|---|---|
| postgres | admin_password | DB nội bộ, không publish port |
| admin (CLI ngắn hạn) | admin/migrator/runtime/owner | Tạo role/seed, không nhận lưu lượng public |
| migrate (CLI ngắn hạn) | migrator_password | DDL, tài khoản khác runtime |
| API, worker, tests | runtime_password | Không owner/superuser/BYPASSRLS, không secret admin |
| auth | auth_password | Issuer role riêng, không mount vào API/worker |
| Caddy | Không | Proxy local |

API/worker non-root, rootfs read-only, không mount Docker socket hoặc plugin mẫu.
Worker G3 chỉ kiểm/nhập dữ liệu ZIP; xử lý job/container plugin thuộc G4.
Dispatcher G4 riêng có Docker socket để tạo container theo cấu hình cố định;
API/import worker và container calculator không có socket. Chỉ bật với release
được operator duyệt; chưa phải sandbox cho mã công khai.

## Kết nối và verify

[Cấu hình OAuth/MCP G2](Docs/connections/G2-local.md) gồm các URL discovery,
SDK/host JSON mẫu và giới hạn. Có thể thử bằng CLI:

```powershell
uv run python scripts/connect-local.py
```

CLI mở browser xin hub:read, gọi tool đọc rồi revoke grant tạm, không lưu/in token.

Tạo snapshot ZIP bất biến của ba mẫu (không sửa `plugin_example`), rồi nhập bằng
browser OAuth có scope `hub:write` và quyền owner/admin:

```powershell
python scripts/pack-g3-samples.py
uv run python scripts/connect-local.py --import-zip ".local/g3-samples/OPC Team.zip" --enable
```

Mặc định không có `--enable` thì chỉ kiểm/preview. CLI in upload UUID để tiếp tục
bằng `--resume-upload UUID`; cập nhật cần `--expected-revision N`. Các ZIP tạo từ
folder không được gọi là ZIP gốc nhà phát hành. [Hợp đồng G3](Docs/contracts/G3-registry.md)
ghi API, canonical tree hash, quotas, cảnh báo nguồn và HTML quarantine.

Sau khi nhập ba mẫu, build và bật các calculator Python:

```powershell
python scripts/prepare-g4.py
python scripts/local.py up
python scripts/local.py runtime --release PATH_TO_RELEASE_JSON
uv run python scripts/connect-local.py --run-tool cit_estimate --arguments-file configs/examples/g4-cit.json
```

Lệnh prepare in đường dẫn release.json. CLI xin `tools:run`, nhận job, chờ kết quả
và revoke grant cuối lượt. [Contract G4](Docs/contracts/G4-runtime.md) ghi tool tài
liệu readonly, job/cancel/isolation và giới hạn PDF/encoding/source.

Từ checkout có source **đã commit**, chạy:

```powershell
./scripts/verify.ps1 -Stage G5
```

Linux/POSIX:

```sh
sh scripts/verify.sh G5
```

Cả hai gọi `scripts/verify.py`: xuất **git archive HEAD** vào thư mục sạch, build
image từ đó, tạo project/DB/volume test riêng, chạy pytest trong Compose, kiểm
hai tenant, RLS thật, file traversal/symlink, pool context, migrations và recreate
không mất dữ liệu. G2 còn chạy browser flow HTTP, official SDK client, evaluator,
replay/concurrency/revocation và session/token/code qua recreate. G3 thêm nhập
ba ZIP thật/16 vai trò, plugin thứ tư, wire catalog, export/file hashes, partial
upload qua recreate, phiên bản lỗi và giới hạn ZIP. Thử readiness
khi thiếu migration/DB ngừng rồi khôi phục. `-Stage G1` vẫn chạy core regressions.
Project test được dọn đúng tên sau khi thành công; failure giữ test state để điều
tra. Không tác động dữ liệu `goodmcp-local` hoặc `plugin_example`.

Bằng chứng G4: `Docs/reports/evidence/G4/verify.json` và `verify-console.txt`.
G4 chạy 47 parity cases, keyword/read paging, Docker job boundaries, timeout,
cancel/crash/fencing và lấy mẫu memory Compose; không xây hoặc đo TF-IDF.
`--working-tree` chỉ dùng phát triển, **không tính đạt clean-checkout acceptance**.

G5 kế thừa hồi quy G1–G4, thêm concurrent project writes, draft/complete/skip/
rollback, legacy checkpoints, lịch sử, host reports, MCP bằng grant mới và resume
sau recreate. [Báo cáo G5](Docs/reports/G5.md) và
`Docs/reports/evidence/G5/verify.json` ghi đúng source mode đã chạy. Khi kiểm mã
đang sửa chưa commit, dùng `python scripts/verify.py --stage G5 --working-tree`;
muốn tái dùng image Python đã build offline, thêm
`--g4-release .local/g4/active/release.json`. Mọi test vẫn chạy trong database và
volume test mới, không dùng dữ liệu workspace thật.
Script không thực hiện deploy hay API model trả phí.

## Cấu trúc và bước tiếp

- `apps/api`: API/MCP + issuer ở service riêng; `apps/web` dành cho G6.
- `packages/core/goodmcp`: TenantContext, DB transaction, schema, ArtifactStore.
- `infra`: Compose, pinned images, Caddy, Alembic. `schema_v1.py` được freeze cho
  migration `0001_g1`; thay đổi tiếp bằng revision/migration mới, không sửa lịch sử.
- `tests`: PostgreSQL/filesystem/HTTP tests và persistence probes.
- `packages/plugin-adapters`, `runners`: phạm vi G4, chưa chạy plugin ở G1.

ArtifactStore nhận tenant transaction đã kiểm membership; handle là UUID, key do
server sinh. Blob ghi temp/fsync/publish atomic trước DB commit; rollback có thể
để orphan blob. Delete chỉ tombstone và giữ blob để không xóa dữ liệu backup/pin;
physical GC và backup snapshot accounting thuộc các giai đoạn sau. G3 có admission
quota cho upload; chưa tự xóa lịch sử phiên bản hoặc blob.

Đọc [PLAN](Docs/PLAN.md), [contract G0](Docs/contracts/G1-contract.md),
[G0](Docs/reports/G0.md), [G1](Docs/reports/G1.md), [G2](Docs/reports/G2.md), [G3](Docs/reports/G3.md), [G4](Docs/reports/G4.md).
G5 tiếp theo làm workflow/project. Local wire pass không chứng minh
đã kết nối host cloud hoặc đạt backup/restore/production.
