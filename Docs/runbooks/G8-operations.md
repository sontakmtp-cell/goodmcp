# Vận hành GoodMCP trên VPS

Ngày 31/10/2026, Asia/Saigon. Kết quả nghiệm thu cụ thể xem [G8](../reports/G8.md).

## Địa chỉ và đăng nhập

- Trang chủ: https://goodmcp.si/
- Quản trị: https://goodmcp.si/admin
- URL thêm vào ứng dụng AI: **https://goodmcp.si/mcp**
- OAuth issuer của Hub: https://goodmcp.si/auth; đăng nhập qua Cloudflare SSO.
- `www.goodmcp.si` chuyển về tên miền chính. Subdomain Blender cũ đã được gỡ.

Mật khẩu VPS không dùng để đăng nhập Hub. Cloudflare xác minh danh tính tài khoản
được cho phép; Hub tiếp tục hỏi quyền workspace và giữ scope, PKCE, refresh/revoke.
Không mở đăng ký công khai. Khầy yêu cầu giữ lớp bảo vệ GitHub/app mobile hiện có,
không bật thêm 2FA Cloudflare trong lượt này; đây là lựa chọn chủ tài khoản xác nhận.

## SSH từ máy Khầy

Khóa riêng được tạo tại `H:\AI\goodmcp\.local\g8\id_ed25519`, public key cùng tên
có đuôi `.pub`; host key được ghim ở `.local\g8\known_hosts`. Thư mục đã hạn chế
quyền truy cập Windows. Đừng đưa khóa riêng vào Git, frontend hoặc báo cáo.

```powershell
ssh -i H:/AI/goodmcp/.local/g8/id_ed25519 -o UserKnownHostsFile=H:/AI/goodmcp/.local/g8/known_hosts root@110.172.28.251
```

Tên đăng nhập đã xác minh là **root**. SSH đã tắt password và keyboard-interactive;
root được dùng key. Host key ban đầu được ghi nhận theo lần kết nối đầu (TOFU),
chưa có đối chiếu fingerprint từ console nhà cung cấp. Muốn thay máy/host key,
đối chiếu console trước khi sửa known_hosts, không bỏ kiểm tra host key.

## Kiểm tra hằng ngày

Sau khi SSH, các lệnh sau không in mật khẩu/token:

```sh
cd /opt/goodmcp
./compose ps
curl --fail https://goodmcp.si/health/ready
docker stats --no-stream
cat /opt/goodmcp/state/health.json
systemctl status goodmcp-backup.timer goodmcp-health.timer --no-pager
journalctl -u goodmcp-backup.service -n 30 --no-pager
```

Chỉ cổng SSH và Caddy 80/443 được mở. PostgreSQL/API/auth/worker/dispatcher không
publish cổng. Dispatcher là tiến trình đặc quyền do có Docker socket; API, worker
và container Python chuyên ngành không được cấp socket đó.

Máy có 2 CPU/~4 GiB RAM, SSD khoảng 50 GB, thêm swap 1 GiB để giảm rủi ro bộ nhớ
đột biến. Swap không thay RAM. Giới hạn container nằm trong
`infra/compose.production.yml`; không tăng job concurrency hoặc bật TF-IDF/index
nặng trên cấu hình này nếu chưa đo. Giữ Python gốc và image đã được duyệt.

Health timer kiểm tra mỗi phút: đĩa từ 70% cảnh báo; từ 85% tạo cờ chặn **tạo upload
mới** ở Caddy. Job và dự án đang có không bị xóa. Kiểm tra lý do và dung lượng trước
khi giải phóng đĩa; không xóa blob theo tên/tuổi vì project có thể đang ghim version.
Sau khi đĩa giảm dưới ngưỡng, health timer tự bỏ cờ. Đây là kiểm tra mỗi phút, không
phải giới hạn cứng cho toàn bộ số byte có thể ghi trong khoảng giữa hai lần kiểm.

MCP và status của `/auth/token` ở volume Caddy `/data/logs/mcp.jsonl`, xoay 1 MiB × 2.
Chỉ ghi metadata giao thức, tên tool, status/thời gian/request ID; bỏ headers,
URI/query, body và response headers. Các đường auth khác không được access-log.

## Backup và giới hạn hiện tại

Khầy **tạm chưa bật R2**. Không tạo subscription, mua gói hoặc lưu cloud credentials.
Repository restic mã hóa hiện ở `/opt/goodmcp/backups/repository` trên VPS. Khóa mở
repository có bản giữ ngoài VPS ở máy Khầy:
`H:\AI\goodmcp\.local\g8\production-secrets\restic_password`.

Timer chạy khoảng 03:00 giờ Việt Nam, có độ lệch ngẫu nhiên tối đa 5 phút. Backup
tạm dừng API/auth/worker/dispatcher, dump PostgreSQL nhất quán rồi chụp blob và
cấu hình; bật lại các tiến trình ngay khi snapshot xong. Caddy vẫn phục vụ trang
tĩnh, nhưng thao tác cần backend có thể tạm thất bại trong cửa sổ bảo trì này.

```sh
systemctl start goodmcp-backup.service
cat /opt/goodmcp/backups/last-success.json
export RESTIC_REPOSITORY=/opt/goodmcp/backups/repository
export RESTIC_PASSWORD_FILE=/opt/goodmcp/secrets/restic_password
restic snapshots
restic check
```

Giữ 7 bản ngày + 4 bản tuần, dedup bằng restic. Backup gồm DB, blob/ZIP nguồn,
project, cấu hình và các image release cần để phục hồi chính xác; không lấy Docker
build cache, venv hoặc dự án DNS/Blender cũ. Mật khẩu restic không nằm trong snapshot.

**Bản restic trên cùng VPS không bảo vệ được khi mất toàn bộ VPS.** Bản mã hóa đã
tải về máy và phép restore được ghi trong G8.md. Chưa có backup ngoài VPS tự động;
không cam kết RPO 24 giờ cho sự cố mất VPS khi R2 còn được hoãn. Cần lấy bản mới
về máy sau thay đổi quan trọng, hoặc triển khai R2 khi Khầy cho bật dịch vụ.

Bản đã tải: `H:\AI\goodmcp\.local\g8\recovery\restic-20261031.tar`, SHA-256
`be732690dc31c0d0bfe52a18c1b922854e71ffd929de48b757edc5e0840d15c9`.
Đây là tar của repository **đã mã hóa**, không phải dump SQL plaintext.
Snapshot nghiệm thu: `2ffabcd5a7938121afd11c1d9c5a850b447172c8111943f46fce2f7ccd41bc46`.
Để dùng bản này khi mất VPS: kiểm SHA, giải tar vào thư mục private trên máy phục
hồi, đặt `RESTIC_REPOSITORY` tới thư mục `repository`, đưa khóa giải mã từ máy Khầy
vào file mode 600 rồi chạy `restic check` và `restic restore`. Không giải tar vào
repository đang có. Giữ khóa riêng với bản mã hóa khi sao chép sang thiết bị khác.

## Khôi phục và kiểm chứng

Không ghi đè database/volume production để thử. Dùng target mới, Compose project
và volumes riêng; chỉ bind loopback nếu tạm dùng password login để kiểm chứng.
Không đưa môi trường kiểm tra đó lên DNS public.

```sh
export RESTIC_REPOSITORY=/opt/goodmcp/backups/repository
export RESTIC_PASSWORD_FILE=/opt/goodmcp/secrets/restic_password
restic restore SNAPSHOT_ID --target /opt/goodmcp/restore-TEN_MOI
```

Vì snapshot có cả đường dẫn tuyệt đối và tương đối, file khôi phục nằm dưới
`restore-TEN_MOI/releases`, `secrets`, `backups/staging`, cùng
`restore-TEN_MOI/var/lib/docker/volumes/goodmcp-prod_artifacts/_data`.
Không giả định có thêm prefix `opt/goodmcp` cho các nguồn tương đối.

Lượt nghiệm thu dùng Compose project `goodmcp-restore-g8`, port
`127.0.0.1:18081`, DB/volume mới. Để lặp lại, tạo target và project tên mới, từ chối
nếu đã tồn tại. Tạo env riêng ngoài source với các giá trị sau (thay target mới):

```dotenv
HUB_PUBLIC_BASE_URL=http://localhost:8080
HUB_PORT=18081
HUB_SECRETS_DIR=/opt/goodmcp/restore-TEN_MOI/secrets
HUB_IMAGE=goodmcp-hub:g8r4-20261031
HUB_CADDY_IMAGE=goodmcp-caddy:local
HUB_G4_RELEASE_DIR=/opt/goodmcp/restore-TEN_MOI/finance
HUB_RUNNER_PROJECT=goodmcp-restore-TEN_MOI
HUB_DOCKER_GID=111
HUB_ALLOW_TEST_FIXTURES=0
```

GID 111 là số đã đo trên VPS này; máy khác phải đo lại bằng
`stat -c %g /var/run/docker.sock`. Dùng image tag trong `deploy.env` của snapshot,
nạp `app-images.tar` và `approved-finance.oci.tar`; PostgreSQL phải khớp digest
pin trong Compose (có thể pull đúng digest nếu máy sạch chưa có).

Tạo wrapper `r` cho hai file Compose **trong target đã phục hồi**, dùng env riêng:

```sh
r() {
  docker compose --project-name goodmcp-restore-TEN_MOI \
    --env-file /opt/goodmcp/restore-TEN_MOI.env \
    -f /opt/goodmcp/restore-TEN_MOI/releases/g8/infra/compose.yml \
    -f /opt/goodmcp/restore-TEN_MOI/releases/g8/infra/compose.restore.yml "$@"
}
r config --quiet
r up -d --wait --no-build --pull never postgres
r run --rm --no-deps admin python -m goodmcp.admin roles
r exec -T postgres pg_restore -U postgres -d goodmcp --exit-on-error \
  --clean --if-exists < /opt/goodmcp/restore-TEN_MOI/backups/staging/database.dump
r run --rm --no-deps migrate
r create --no-build api
```

Sau `create api`, volume artifact mới đã được tạo. Kiểm nhãn project của volume,
chép nội dung từ `restore-TEN_MOI/var/lib/docker/volumes/goodmcp-prod_artifacts/_data`
vào đúng volume mới, giữ uid/gid và mode. Không chép lên volume production.
Sau đó `r up -d --wait --no-build --pull never api auth worker dispatcher caddy`.
Chạy `scripts/audit-g8-data.py --compose WRAPPER_PATH --volume VOLUME_MOI --output FILE`
để đối chiếu từng artifact với SHA/bytes trong DB vừa restore.

Phép HTTP/MCP dùng `tests/wire_g7.py --local --base-url http://localhost:8080`
trong service `wire`, mount release JSON vào `/app/.local/g4/active/release.json` và
mật khẩu owner local gốc từ máy Khầy vào `/app/.local/secrets/owner_password`.
File `owner_password` bootstrap mới trên VPS **không đổi hash owner đã migrate**;
không dùng nó để suy rằng đã có password recovery cho tài khoản production.
Password gốc chỉ được đưa lên VPS tạm cho phép thử loopback và đã xóa sau nghiệm thu.
Production vẫn dùng SSO; chưa thử SSO trên origin riêng của một máy restore mới.

Trên máy sạch: cài Docker/Compose và restic; nạp image release đã kiểm digest;
tạo roles bằng secret đã khôi phục; restore custom dump bằng `pg_restore`; chạy
migration tiến lên; chép blob vào volume mới; kiểm hash và quyền file; sau đó kiểm
login, project pin/revision/readback và job Python. Với production phải dùng lại
OIDC config đã khôi phục và public HTTPS; password login của phép thử loopback
không thay cho phép thử Cloudflare SSO.

SSO config có client secret và state key, chỉ mount vào auth service. Runtime DB
password chỉ vào API/worker/dispatcher. Không thay các secret phục hồi tùy tiện:
đổi password file đơn lẻ mà chưa đổi role trong DB sẽ làm dịch vụ mất kết nối.

## Cập nhật và rollback

1. Chạy kiểm tra trong môi trường riêng; tạo snapshot mới và ghi snapshot ID.
2. Build frontend với `VITE_MCP_URL=https://goodmcp.si/mcp` và
   `VITE_OAUTH_ISSUER=https://goodmcp.si/auth`. Không copy `apps/web/.env` lên web.
3. Build image API từ source/lock, gắn tag release mới, lưu digest và bundle nguồn.
4. Nạp image trên VPS; cập nhật `HUB_IMAGE` trong `/opt/goodmcp/deploy.env`.
5. Chạy migration bằng profile ops, sau đó `./compose up -d --wait --no-build`.
6. Kiểm readiness, OAuth/consent, Python thật, project readback và revoke.

Rollback ứng dụng bằng tag/digest trước đó chỉ khi schema còn tương thích. Nếu đã
có migration không tương thích, phục hồi snapshot vào môi trường sạch để chọn
phương án; **không downgrade schema hoặc xóa volume production** để làm ứng dụng chạy.
Không chạy `down --volumes` trên `goodmcp-prod`.
Khi dọn môi trường thử, phải kiểm project/nhãn trước; dùng các profile đã tạo,
ví dụ `r --profile g4 --profile test down --volumes`. Lượt này dispatcher thuộc
profile g4 còn lại sau `down` mặc định; đã kiểm nhãn và dọn riêng, không còn tài
nguyên `goodmcp-restore-g8`. Không xóa thư mục target trước khi các container dùng
secret/bind mount của nó đã được gỡ.

## Sự cố thường gặp

- `401` ở `/mcp` khi chưa kết nối là yêu cầu OAuth bình thường, không phải lỗi cần
  bỏ xác thực. Dùng URL `/mcp`, không dùng `/auth` làm URL MCP.
- `invalid_origin` trên form: kiểm `Referrer-Policy: same-origin`; giữ kiểm Origin
  và CSRF, không cho `Origin:null` đi qua để chữa lỗi.
- Callback ChatGPT không quay về: CSP chỉ cho phép origin callback đã đăng ký;
  không đổi sang wildcard. Bắt đầu flow mới, không bấm lại form đã dùng CSRF.
- CIMD: ChatGPT công bố cả `none` và `private_key_jwt`. Hub chỉ nhận `none` + PKCE,
  chọn đúng giao của phương thức hỗ trợ; không chấp nhận JWT chưa xác minh.
- DNS đã đổi nhưng trình duyệt còn trang cũ: kiểm resolver/cache của thiết bị.
  Không cấp quyền OAuth nếu trang đang hiển thị dự án cũ.
- Job failed/lease hết hạn: đọc lỗi/job ID và log dispatcher; không đổi trạng thái
  failed thành succeeded trong DB, không tự duyệt image/command từ client.
