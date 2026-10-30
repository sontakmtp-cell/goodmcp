# goodmcp-hub — OAuth/MCP local G2

Hub quản lý plugin theo workspace, giữ công cụ Python. **G2 có login/consent,
OAuth PKCE/refresh/revoke và MCP HTTP với một tool đọc workspace** trên nền core/DB
G1. Chưa có UI quản trị, importer, công cụ tài chính hoặc plugin runner. Chưa
deploy cloud hoặc live-test connector cloud; xem báo cáo G2 để biết gate còn lại.

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
G1 worker chỉ kiểm readiness DB; xử lý job/container plugin thuộc G4.

## Kết nối và verify

[Cấu hình OAuth/MCP G2](Docs/connections/G2-local.md) gồm các URL discovery,
SDK/host JSON mẫu và giới hạn. Có thể thử bằng CLI:

```powershell
uv run python scripts/connect-local.py
```

CLI mở browser xin hub:read, gọi tool đọc rồi revoke grant tạm, không lưu/in token.

Từ checkout có source **đã commit**, chạy:

```powershell
./scripts/verify.ps1 -Stage G2
```

Linux/POSIX:

```sh
sh scripts/verify.sh G2
```

Cả hai gọi `scripts/verify.py`: xuất **git archive HEAD** vào thư mục sạch, build
image từ đó, tạo project/DB/volume test riêng, chạy pytest trong Compose, kiểm
hai tenant, RLS thật, file traversal/symlink, pool context, migrations và recreate
không mất dữ liệu. G2 còn chạy browser flow HTTP, official SDK client, evaluator,
replay/concurrency/revocation và session/token/code qua recreate. Thử readiness
khi thiếu migration/DB ngừng rồi khôi phục. `-Stage G1` vẫn chạy core regressions.
Project test được dọn đúng tên sau khi thành công; failure giữ test state để điều
tra. Không tác động dữ liệu `goodmcp-local` hoặc `plugin_example`.

Bằng chứng G2: `Docs/reports/evidence/G2/verify.json` và `verify-console.txt`.
`--working-tree` chỉ dùng phát triển, **không tính đạt clean-checkout acceptance**.
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
physical GC, quota và backup snapshot accounting thuộc các giai đoạn sau.

Đọc [PLAN](Docs/PLAN.md), [contract G0](Docs/contracts/G1-contract.md),
[G0](Docs/reports/G0.md), [G1](Docs/reports/G1.md), [G2](Docs/reports/G2.md).
G3 làm importer/registry, G4 runner/jobs/search. Local wire pass không chứng minh
đã kết nối host cloud hoặc đạt backup/restore/production.
