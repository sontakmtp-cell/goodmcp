# Rà soát trước khi mở goodmcp-hub cho nhiều người dùng

**Ngày**: 2026-10-31
**场景 (loại)**: Pre-launch check — Product + Security + QA/Release + Code health
**参与成员 (thành viên tham gia)**: 产品官 (product-reviewer) · 安全卫士 (security-officer) · 质量门神 (qa-lead) · 排障手 (investigator)
**Phạm vi**: `H:/AI/goodmcp` — review tĩnh, read-only. Không deploy, không đụng production goodmcp.si.

---

## 📌 TL;DR (tóm tắt thực thi)

- **Kết luận tổng**: 🔴 **No-Go** cho "mở cho nhiều người dùng thật". 🟡 **Conditional-Go** cho pilot đóng 2–3 người đã tạo tài khoản thủ công.
- **Lý do gốc, không phải chuyện code dở**: hệ thống hiện tại **chưa có khái niệm "người dùng thứ hai"**. `allowed_email` là một giá trị duy nhất; không có lệnh tạo user; không có trang để người dùng tự thu hồi quyền.
- **Số blocking**: 6 blocker (3 product + 1 security + 2 vận hành).
- **Phát hiện nguy hiểm nhất**: một người lạ **không cần tài khoản** có thể khoá đăng nhập của toàn bộ hệ thống trong 15 phút, lặp vô hạn (F-01).
- **Điều đáng khen**: lõi auth/tenant rất chắc — không tìm thấy lỗ hổng đọc chéo dữ liệu tenant, không bypass đăng nhập, RLS bật FORCE trên 31 bảng, ZIP import chống zip-slip/symlink/bomb. Vấn đề nằm ở **tầng vận hành và tầng danh tính**, không nằm ở tầng cách ly dữ liệu.

---

## 🎯 Thẻ kết luận cốt lõi

| Mục | Nội dung |
|---|---|
| Go / No-Go | 🔴 No-Go cho multi-user · 🟡 Conditional-Go cho pilot ≤3 người |
| Điểm an ninh | **B-** (lõi chắc, nhưng 1 lỗi chặn launch) |
| Phân bố mức độ | 🔴 6 · 🟠 9 · 🟡 7 · ✅ nhiều điểm tốt |
| Hành động chính | 8 mục (4 việc phải làm trước khi mở) |
| Người chịu trách nhiệm | Khầy (quyết định) + 1 dev (sửa code) + người thứ 2 (vận hành dự phòng) |
| Chặn tuyệt đối | Không có cách tạo user #2; không có alert khi sập; backup không ra khỏi VPS |

---

## 1. Kết luận cốt lõi từng thành viên

### 🔍 产品官 — Product review
- **Phán đoán**: Đây vẫn là hệ thống **một owner** đúng như thiết kế PLAN. Code và bằng chứng khá chắc, nhưng tầng danh tính chưa có "người dùng thứ hai".
- **Bằng chứng đau nhất**: người không phải Khầy đăng nhập sẽ nhận `{"error":"sso_failed"}` HTTP 403 — không giải thích, không lối thoát. Đó chính là first-run experience của mọi khách hàng đầu tiên.
- **Khuyến nghị**: hạ định vị marketing còn "ChatGPT trước" thay vì bày 5 nền tảng; thêm trang "Kết nối của tôi" có nút thu hồi — với sản phẩm bán "AI đọc tài liệu riêng của bạn", không trả lời được "ứng dụng nào đang có quyền" là **lỗi niềm tin**, không phải lỗi tính năng.

### 🛡️ 安全卫士 — Security audit (OWASP + STRIDE)
- **Phán đoán**: **B-**. Không có lỗ hổng chiếm dữ liệu chéo tenant, không bypass đăng nhập. Nhưng có **1 lỗi chặn launch**.
- **F-01 (Critical)**: rate limit khoá theo `request.client.host`, mà uvicorn chạy **không có `--proxy-headers`** → mọi request đều mang IP của container Caddy. Ba bucket `dcr:` / `login-form:` / `login-ip:` trở thành **một hạn mức chung toàn hệ thống**. Kẻ tấn công bắn 30 lần sai mật khẩu là **khoá đăng nhập của tất cả mọi người** trong 15 phút, lặp vô hạn. Tương tự, 20 lượt DCR/giờ chặn mọi người dùng mới đăng ký client.
- **Điểm tốt đã kiểm chứng**: scope ép ở tầng nghiệp vụ, RLS + FORCE mọi bảng tenant, token/code/session chỉ lưu hash, PKCE bắt buộc S256, SSO state HMAC + bind cookie + chống replay, ArtifactStore dùng `O_NOFOLLOW`/`openat`, runner container cô lập tốt (NetworkMode none, ReadonlyRootfs, CapDrop ALL, no-new-privileges, image pin digest), không có secret trong git history.

### ✅ 质量门神 — QA & Release
- **Phán đoán**: **No-Go** cho nhiều user; **Conditional** nếu chỉ pilot ≤3 người tạo tay.
- **Tóm một dòng**: *hệ thống đủ tốt để chạy 1 owner, chưa đủ để mở cho người thứ hai.*
- **Lỗ hổng kiểm thử**: `/admin` là route client-side React (`apps/web/src/App.tsx:336`), verify.py chạy pytest Python nên **về mặt kiến trúc không thể chạm**. `cloudflare_sso.py` chỉ có 3 unit test pure function; route `/auth/callback` thật + tiêu thụ DB session + cổng "chỉ owner" **không được test end-to-end ở đâu cả** — chỉ được chứng minh bằng 1 lần bấm tay trong G8.
- **Pipeline**: `scripts/verify.py` chỉ nhận `--stage G1..G5` → **G6/G7 nằm ngoài pipeline verify hoàn toàn**. Không có CI, không có script deploy; quy trình là 6 bước tay trong runbook.
- **Điểm tốt đã kiểm**: RLS/tenant isolation có test thật (`tests/test_g1.py:38-103`, `test_registry.py:185`, `test_workflows.py:124`); ZIP bomb (`test_registry.py:38-68`); path traversal/symlink (`test_g1.py:155-182`); pytest không đụng dữ liệu thật.

### 🔧 排障手 — Code health & runtime
- **Phán đoán**: thứ vỡ đầu tiên khi 1 → 100 user **không phải** DB, mà là **hàng đợi job** và **pool 5 kết nối**.
- **Cỗ máy thời gian ma**: `hub_claim_job` chặn cứng `count(running) < 2` **theo từng loại job, toàn hệ thống** (`0004_g4.py:75`) + dispatcher `max_workers=2`; trong khi `deadline_at = now + 10 phút`. Quá 2 job đồng thời → job xếp hàng, quá 10 phút bị đánh `failed/timeout` **dù chưa hề chạy**. User thấy "timeout" mà không ai làm gì sai.
- **Nút thắt kết nối**: 1 uvicorn process, `pool_size=5, max_overflow=0`, `pool_timeout` 30s. Request thứ 6 trở đi xếp hàng 30 giây rồi ném `TimeoutError` → 500.
- **Download giữ connection DB suốt thời gian stream** (`registry_api.py:113-115`) + hash toàn bộ file trước khi trả byte đầu (`storage.py:157-162`) → 5 người tải file lớn là cả API chết vì cạn pool. Kết hợp F-03 của Security: mỗi lần đọc 1 byte vẫn băm SHA-256 cả GiB.
- **Working tree**: `plugin_example/` bị tái cấu trúc chưa commit (56 file xoá, 3 thư mục untracked ~610 MB). Runtime **không** đọc thư mục này nên deploy vẫn chạy — nhưng **`git clean -fd` hoặc `git stash -u` sẽ xoá mất 3 gói plugin gốc, không có backup**.

---

## 2. Phát hiện tổng hợp (đã gộp trùng, xếp theo mức độ)

| # | Mức | Nhóm | Vị trí | Vấn đề | Cách sửa | Nguồn |
|---|---|---|---|---|---|---|
| 1 | 🔴 | Bảo mật | `apps/api/auth.py:116,132,161` + `infra/Dockerfile:14` | Rate limit khoá theo IP peer, uvicorn thiếu `--proxy-headers` → mọi request cùng IP Caddy → **một bucket chung**, ai cũng khoá được đăng nhập toàn hệ thống | Thêm `--proxy-headers --forwarded-allow-ips=<IP Caddy>`; rate limit theo IP thật ở Caddy/Cloudflare; tách bucket theo email | Security |
| 2 | 🔴 | Sản phẩm | `packages/core/goodmcp/cloudflare_sso.py:81`, `admin.py:86` | Chỉ 1 `allowed_email`, không có lệnh tạo user → **người thứ 2 không thể đăng nhập**; user #2 phải INSERT SQL tay bằng role migrator | Thêm bảng users + lệnh `admin invite` / danh sách email cho phép | Product + QA |
| 3 | 🔴 | Vận hành | `infra/backup.sh:7,28` | Repository restic nằm **cùng ổ đĩa VPS**; `off_vps_automatic: False`. Mất VPS = mất DB + blob + image; chỉ còn tar tay 31/10 | Bật R2/B2 hoặc `rclone` đẩy repository ra ngoài; thêm timer kiểm tra | QA + Security |
| 4 | 🔴 | Vận hành | `apps/api/main.py:134-137`, `infra/Dockerfile:14`, `Caddyfile.production:25` | Handler 500 **không log gì**; uvicorn `--no-access-log`; Caddy skip log mọi path trừ `/mcp`,`/auth/token` → sự cố 24h đầu **không có dấu vết để tra** | `logging.exception()` + bật access-log; gửi log Caddy cho mọi 5xx | QA + Investigator |
| 5 | 🔴 | Vận hành | `infra/health.py`, `goodmcp-health.timer` | Health chỉ ghi JSON + stdout; **không webhook/email/SMS, không `OnFailure=`** → site sập 2h sáng không ai biết | Uptime monitor ngoài (BetterStack/UptimeRobot) poll `/health/ready` mỗi 1 phút → Telegram | QA |
| 6 | 🔴 | Sản phẩm | `apps/api/auth.py:267-278`, `apps/web/src/App.tsx:311` | `/auth/account` chỉ có "Đăng xuất"; UI tự thừa nhận "chưa có trạng thái kết nối AI"; không route DELETE nào | Trang "Kết nối của tôi" + revoke/revoke-all + xoá project | Product |
| 7 | 🟠 | Hiệu năng | `infra/migrations/versions/0004_g4.py:75`, `dispatcher.py:106`, `jobs.py:66` | Trần **2 job đồng thời toàn hệ thống**, deadline 10 phút → job bị đánh timeout **khi chưa chạy** | Nâng trần theo CPU, hoặc tính deadline từ lúc bắt đầu chạy thay vì lúc enqueue | Investigator |
| 8 | 🟠 | Hiệu năng | `packages/core/goodmcp/database.py:50` | `pool_size=5, max_overflow=0` cho toàn API, `pool_timeout` 30s → request thứ 6 chờ 30s rồi 500 | `pool_size=10`, `pool_timeout=5`, đo lại với `max_connections=30` | QA + Investigator |
| 9 | 🟠 | Hiệu năng | `registry_api.py:113-115`, `storage.py:157-162` | Stream giữ connection DB suốt thời gian tải; hash cả file trước khi trả byte đầu | Lấy handle ra ngoài generator; cache verify theo (sha256,size,mtime) hoặc `pread` | Investigator + Security |
| 10 | 🟠 | Bảo mật | `apps/api/mcp_auth.py:50-134` | **Không rate limit** trên `/api/v1` và `/mcp` | Token bucket theo (user, workspace) ở Caddy hoặc middleware | Security + Investigator |
| 11 | 🟠 | Bảo mật | `packages/core/goodmcp/oauth_store.py:94,112` | Trần **500 OAuth client toàn cục**, không có lệnh dọn → hết chỗ là **không ai đăng ký được nữa, vĩnh viễn** | Cho phép xoá client hết hạn + job dọn định kỳ | Security |
| 12 | 🟠 | Vận hành | `infra/backup.sh:14` | `compose stop api auth worker dispatcher` mỗi 03:00 → **downtime toàn hệ thống hằng đêm** (vài phút → vài chục phút) | Blob đã publish-trước-metadata; thử chỉ stop `worker dispatcher` | QA + Investigator |
| 13 | 🟠 | Vận hành | `Docs/reports/G8.md:50-51` | Image production build từ **working tree**, không pin digest; HEAD không khớp | Commit sạch → build lại → pin digest vào deploy.env | Product |
| 14 | 🟠 | Vận hành | `.local/g8/*` | SSH key + khóa restic + Cloudflare chỉ **1 bản trên máy Khầy**; SSH password đã tắt → mất laptop = mất VPS | Bản sao thứ 2 của 3 secret + 1 người thứ 2 chạy thử restore | Product |
| 15 | 🟠 | Kiểm thử | `scripts/verify.py:40` | Chỉ nhận `--stage G1..G5` → **G6/G7 ngoài pipeline**; không CI | Thêm stage G6/G7 + GitHub Actions | QA |
| 16 | 🟡 | Bảo mật | `Caddyfile.production:36-40` | SPA không có CSP; admin UI giữ bearer token trong RAM | Thêm `default-src 'self'` + hash inline script | Security |
| 17 | 🟡 | Bảo mật | `registry.py:56` | Quota chỉ 20 GiB **mỗi workspace** → 100 workspace = 2 TB trên 1 ổ 50 GB | Quota toàn cục + cảnh báo 70% | Security + Investigator |
| 18 | 🟡 | Bảo mật | `compose.yml:179` | `docker.sock` trong dispatcher = quyền root host nếu dispatcher bị chiếm (runner đã cô lập tốt) | Dùng docker-socket-proxy chỉ mở `/containers/*` | Security |
| 19 | 🟡 | Dead code | `Caddyfile.production:45-56` | Matcher `@storage_full` ghép `method POST` + `file` → `file` matcher chỉ chạy GET/HEAD → **không bao giờ match**, cờ chặn upload khi đĩa 85% vô hiệu | Sửa matcher (bỏ `method POST`, dùng `path`/`header`) — *cần verify docs Caddy 2.x* | Investigator |
| 20 | 🟡 | Vận hành | `worker.py:11,14-16` | `assert` revision → lệch migration là crash-loop vô hạn; nuốt mọi exception không log | Fail-fast có log + `restart: on-failure:5` | Investigator |
| 21 | 🟡 | Hiệu năng | `jobs.py:61`, `documents.py:72-79` | Không index `jobs(workspace_id,state)`; `strpos(body_fold,…)` full-scan trên text 2 MB | Thêm index + GIN/trigram | Investigator |
| 22 | 🟡 | Dọn dẹp | working tree | 56 file `plugin_example` xoá + ~610 MB untracked **không bị .gitignore chặn** | Commit ngay; thêm `.gitignore` cho gói lớn | QA + Investigator |

---

## 3. ✅ Danh sách hành động

| # | Hành động | Bên làm | Mức ưu tiên | Khi nào |
|---|---|---|---|---|
| 1 | Thêm `--proxy-headers --forwarded-allow-ips` cho `api` + `auth`; rate limit theo IP thật | Dev | **P0** | Trước khi mở |
| 2 | Thêm cơ chế tạo user (bảng users + `admin invite` hoặc danh sách email) | Dev | **P0** | Trước khi mở |
| 3 | Bật uptime monitor ngoài poll `/health/ready` → Telegram/email | Khầy | **P0** | Trước khi mở (15 phút) |
| 4 | `logging.exception()` ở handler 500 + bật access-log | Dev | **P0** | Trước khi mở (5 phút) |
| 5 | Đẩy repository restic ra ngoài VPS tự động (R2/B2/rclone) | Khầy | P1 | Tuần 1 |
| 6 | Trang "Kết nối của tôi" + revoke/revoke-all | Dev | P1 | Tuần 1 |
| 7 | `pool_size=10`, `pool_timeout=5`; bỏ `api auth` khỏi `backup.sh:14` | Dev | P1 | Tuần 1 |
| 8 | Commit sạch working tree + build lại image + pin digest | Dev | P1 | Tuần 1 |
| 9 | Bản sao thứ 2 của 3 secret + 1 người thứ 2 chạy thử restore | Khầy | P1 | Tuần 2 |
| 10 | Nâng trần job + tính deadline từ lúc bắt đầu chạy | Dev | P2 | Tuần 2–3 |

---

## 4. Checklist 24 giờ đầu (nếu vẫn quyết định mở)

1. **Trước khi mở**: uptime monitor ngoài hoạt động — đây là thứ **duy nhất** đánh thức Khầy lúc 2h sáng.
2. **Trước khi mở**: `journalctl -u goodmcp-backup.service -n 50` + `cat /opt/goodmcp/backups/last-success.json` — xác nhận đêm qua backup chạy xong, không đoán.
3. **1h đầu**: đăng nhập SSO → chạy 1 job CIT → lưu và mở lại 1 project, bằng **đúng tài khoản user thật đầu tiên** (không dùng owner).
4. **Mỗi 4h**: `./compose ps` (restart count phải = 0), `docker stats --no-stream`, `df -h`. Ghi lại số.
5. **Cuối ngày**: `restic snapshots` + copy tar mới về máy. R2 chưa bật → **không copy = không có backup**.

### Ngưỡng rollback
- `/health/ready` ≠ 200 liên tục > 5 phút
- Bất kỳ 500 nào user báo — vì không có log, mặc định coi là nghiêm trọng
- restart count > 0 trên `api`/`auth`/`postgres`
- Upload trả 503 "Storage capacity reached" ngoài dự kiến (đĩa ≥ 85%)
- ≥ 2 job Python fail liên tiếp

**Cách rollback**: đổi `HUB_IMAGE` trong `/opt/goodmcp/deploy.env` về tag trước → `./compose up -d --wait --no-build`. **Chỉ khi chưa có migration mới.** Nếu đã migrate: **không downgrade schema, không xoá volume** — phải restore snapshot sang môi trường sạch, mất nhiều giờ. Vì vậy mọi deploy có migration phải coi là "không rollback nhanh được".

---

## 5. ⚠️ Chưa hoàn thiện / giới hạn đã biết

- **Chưa có load test đồng thời** (`G8.md:169`) → mọi con số về "chịu được bao nhiêu user" đều suy ra từ config, không phải đo. Không thể cam kết SLA uptime.
- **Chưa ai khác vận hành độc lập từ runbook**; restore drill chạy **trên cùng VPS**, dùng image store sẵn có → chưa chứng minh dựng lại được trên máy mới.
- **Chưa đối chiếu giá VPS thực** (`G8.md:29`).
- **Security không verify được**: chính sách Cloudflare Access phía edge (không có trong repo), CVE dependency (không chạy được scanner offline), hành vi RLS thực tế (không có DB để test).
- **Investigator chưa verify**: Caddy `file` matcher + POST (cần đọc docs Caddy 2.x); bỏ stop `api auth` khi backup có an toàn tuyệt đối không (lý thuyết là có).
- Báo cáo này là **review tĩnh read-only**. Không có xâm nhập thử, không có pentest, không đụng production.

---

## 6. 📚 Chỉ mục sản phẩm của thành viên

- **product-reviewer (产品官)**: verdict No-Go + B1–B5 + danh sách defer-ok và missing-evidence. Điểm nhấn: `cloudflare_sso.py:81` một email duy nhất, `auth.py:180-182` trả 403 câm.
- **security-officer (安全卫士)**: rating B-, F-01→F-09 kèm file:line, danh sách điểm tốt đã kiểm chứng, 5 mục could-not-verify.
- **qa-lead (质量门神)**: verdict, 11 finding, first-24h checklist 5 mục, rollback triggers + cách rollback, xác nhận `/admin` và `/auth/callback` không có test end-to-end.
- **investigator (排障手)**: thứ tự vỡ 1→100 user, 8 finding + 6 quick win, phân tích working tree, 4 mục suspected-chưa-verify.

### Đã kiểm chứng độc lập bởi主理人 (team lead)
5 phát hiện nặng nhất được đọc lại trực tiếp trong code và **xác nhận đúng nguyên văn**: thiếu `--proxy-headers` (`infra/Dockerfile:14`, `compose.yml:87`); handler 500 không log (`main.py:134-137`); `pool_size=5, max_overflow=0` (`database.py:50`); `allowed_email` một giá trị (`cloudflare_sso.py:81`); `backup.sh:14` stop 4 service + `off_vps_automatic: False`; trần job `<2` (`0004_g4.py:75`).

---

> Báo cáo do Software Workshop AI cộng tác tạo. Quyết định cuối cùng thuộc về người phụ trách kỹ thuật.
