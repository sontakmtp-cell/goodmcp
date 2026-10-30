# goodmcp-hub — nền local G1

Hub quản lý plugin theo workspace, giữ công cụ Python. **G1 hiện có core, database,
kho file và hạ tầng local**; chưa có UI, login/OAuth/MCP production, importer hay
plugin runner. Các endpoint nghiệp vụ trả 401 cho tới G2. Không deploy cloud.

## Chạy local

Cần Docker Desktop Linux/Compose v2 và Python 3.12+ trên host. Python host chỉ dùng
stdlib; dependency ứng dụng được cài từ lockfile trong image. Tại repo root:

```powershell
python scripts/local.py up
```

Mở [readiness local](http://127.0.0.1:18080/health/ready) hoặc
[liveness local](http://127.0.0.1:18080/health/live).
Chỉ Caddy publish port **127.0.0.1:18080**; API/database không publish port. DB và
file nằm trong named volumes của project `goodmcp-local`, giữ qua restart/recreate.

```powershell
python scripts/local.py status
python scripts/local.py down
```

`down` giữ dữ liệu; không chạy `down --volumes` trên stack có dữ liệu cần giữ.
Lệnh `up` chạy migration và bootstrap owner một lần, chạy lại không nhân đôi.
Chưa có trang đăng nhập để dùng password này ở G1. Mặc định owner email là
`owner@local.invalid`; có thể đặt `HUB_OWNER_EMAIL` **trước bootstrap lần đầu**.
Đặt `HUB_PORT` trước chạy nếu cần port local khác; mọi port vẫn bind loopback.

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
| Caddy | Không | Proxy local |

API/worker non-root, rootfs read-only, không mount Docker socket hoặc plugin mẫu.
G1 worker chỉ kiểm readiness DB; xử lý job/container plugin thuộc G4.

## Verify G1

Từ checkout có G1 **đã commit**, chạy:

```powershell
./scripts/verify.ps1 -Stage G1
```

Linux/POSIX:

```sh
sh scripts/verify.sh G1
```

Cả hai gọi `scripts/verify.py`: xuất **git archive HEAD** vào thư mục sạch, build
image từ đó, tạo project/DB/volume test riêng, chạy pytest trong Compose, kiểm
hai tenant, RLS thật, file traversal/symlink, pool context, migrations và recreate
không mất dữ liệu. Còn thử readiness khi thiếu migration/DB ngừng rồi khôi phục.
Project test được dọn đúng tên sau khi thành công; failure giữ test state để điều
tra. Không tác động dữ liệu `goodmcp-local` hoặc `plugin_example`.

Bằng chứng: `Docs/reports/evidence/G1/verify.json` và `verify-console.txt`.
`--working-tree` chỉ dùng phát triển, **không tính đạt clean-checkout acceptance**.
Script không thực hiện deploy hay API model trả phí.

## Cấu trúc và bước tiếp

- `apps/api`: health và shell API fail-closed; `apps/web` dành cho G6.
- `packages/core/goodmcp`: TenantContext, DB transaction, schema, ArtifactStore.
- `infra`: Compose, pinned images, Caddy, Alembic. `schema_v1.py` được freeze cho
  migration `0001_g1`; thay đổi tiếp bằng revision/migration mới, không sửa lịch sử.
- `tests`: PostgreSQL/filesystem/HTTP tests và persistence probes.
- `packages/plugin-adapters`, `runners`: phạm vi G4, chưa chạy plugin ở G1.

ArtifactStore nhận tenant transaction đã kiểm membership; handle là UUID, key do
server sinh. Blob ghi temp/fsync/publish atomic trước DB commit; rollback có thể
để orphan blob. Delete chỉ tombstone và giữ blob để không xóa dữ liệu backup/pin;
physical GC, quota và backup snapshot accounting thuộc các giai đoạn sau.

Đọc [PLAN](Docs/PLAN.md), [contract G0](Docs/contracts/G1-contract.md),
[G0](Docs/reports/G0.md), [G1](Docs/reports/G1.md). G2 bổ sung xác thực/session,
G3 importer/registry, G4 runner/jobs/search. Không dùng kết quả G1 để công bố đã
đạt OAuth, nhiều host cloud hoặc backup/restore production.
