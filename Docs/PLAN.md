# goodmcp-hub — Kế hoạch MVP và lộ trình mở rộng

> Cập nhật 30/10/2026, múi giờ Asia/Saigon. Đây là đặc tả để giao việc cho AI agent; trạng thái thực hiện và chứng cứ nghiệm thu được cập nhật riêng trong `Docs/reports/Gx.md`.
>
> **Chọn VPS chạy ứng dụng và công cụ Python, Cloudflare giữ DNS/HTTPS, R2 dùng cho backup ngoài VPS.** MVP chỉ phục vụ Khầy với ba plugin mẫu; kiến trúc dữ liệu và quyền truy cập phải sẵn sàng cho nhiều người dùng và nhiều plugin.
>
> **Điều chỉnh G4 theo Khầy, 30/10/2026:** MVP dùng MCP liệt kê, tìm từ khóa và đọc tài liệu; AI agent tự điều phối. Không xây/benchmark TF-IDF hoặc yêu cầu recall@5 trong MVP. TF-IDF/tìm kiếm nâng cao để sau nếu thực tế cần; giữ nguyên máy tính Python.

## 1. Mục tiêu và phạm vi đã chốt

### 1.1. Trải nghiệm cần đạt

Khầy quản lý plugin trên web, kết nối Hub từ ChatGPT, Claude, Gemini, Grok hoặc CLI hỗ trợ MCP, chọn kỹ năng/chuyên gia/công cụ và tiếp tục công việc qua nhiều cuộc chat. Hub cung cấp công cụ, tài liệu và trạng thái; AI đang chat vẫn là bên suy nghĩ và điều phối.

| Plugin mẫu | Phạm vi nghiệm thu MVP |
|---|---|
| OPC Team | 9 vai trò, tài liệu, quy trình, quyết định và tiến độ |
| Godot–Roblox | 6 hồ sơ chuyên gia, đầu ra mã/tài liệu; chưa bao gồm chạy engine |
| Finance–Tax | 1 chuyên gia, corpus, các máy tính/tra cứu và tìm kiếm Python |

**MVP có một người dùng thật và một workspace cá nhân.** Workspace là vùng dữ liệu riêng của một người hoặc nhóm. Không mở đăng ký công khai, thanh toán hay marketplace trong MVP.

### 1.2. Những thay đổi thay thế kế hoạch cũ

- Ngân sách hạ tầng mục tiêu **5–15 USD/tháng**, thay yêu cầu hoàn toàn miễn phí. Không bao gồm thuê bao AI, phí model API hoặc tên miền đã có.
- **Giữ công cụ chuyên ngành bằng Python.** Không port công thức hoặc thuật toán sang TypeScript/JavaScript, không chuyển Python sang chạy trong trình duyệt.
- Được thêm lớp gọi mỏng, khóa thư viện và sửa lỗi Python có chứng cứ/kiểm thử. Giữ bản nguồn plugin bất biến.
- Lưu được ZIP gốc, PDF, mã Python và phiên bản; không loại bỏ file chỉ vì giới hạn Workers/D1.
- Chọn PostgreSQL và SSD VPS làm nơi lưu chính; bỏ kiến trúc D1/KV/Workers làm lõi của bản trước.
- R2 là kho file/sao lưu, không chạy được Python. Dùng R2 bổ trợ VPS, không coi hai sản phẩm thay thế hoàn toàn cho nhau.
- Hub không tự gọi API model trả phí. Mẫu API chạy phía người dùng, nếu có chi phí model thì tách riêng.
- Thiếu native subagent hoặc quyền chọn model: AI hiện tại làm lần lượt và báo rõ, không giả vờ đã chạy đội AI thật.

### 1.3. Làm nhỏ nhưng không đóng cứng

**Làm trong MVP:** một owner, nhập ZIP, catalog plugin, phiên bản/bật tắt, OAuth MCP, công cụ Python được duyệt, tìm tài liệu, lưu dự án, job nền, nhật ký và backup.

**Thiết kế ngay:** user/workspace/membership, phân quyền theo workspace, quota, plugin schema có phiên bản, adapter/runtime độc lập, giao diện lưu file có thể chuyển sang R2.

**Để sau MVP:** invitation nhiều người, chia sẻ plugin, billing, marketplace, mã do người lạ tải lên, tự cài dependency tùy ý, GPU/LLM trên VPS, embedding mặc định, OCR diện rộng và nhiều máy chủ.

Ba plugin là bộ dữ liệu nghiệm thu, không phải giới hạn viết cứng trong lõi. Kiểm thử phải có hai workspace giả dù production chỉ có Khầy.

## 2. So sánh R2/Cloudflare và VPS

### 2.1. Kết luận lựa chọn

| Phương án | Khả năng giữ Python hiện có | Chi phí và đánh đổi |
|---|---|---|
| Chỉ R2 | Không chạy script/API/database; chỉ lưu object/file | Rẻ cho lưu trữ nhưng vẫn cần nơi chạy ứng dụng |
| Workers + R2 | Có Python Workers, nhưng môi trường Pyodide khác CPython/Linux | Phải kiểm tra/tùy biến thư viện và xử lý tiến trình; không chọn làm mặc định |
| Workers + Containers + R2 | Chạy Python trong container | Nhiều dịch vụ, tính phí theo tài nguyên/thời gian bật; cần đo cold start |
| VPS + Cloudflare DNS/proxy | CPython, thư viện khoa học, database, SSD bình thường | Phí máy cố định; phải quản trị Linux và backup |
| **VPS + Cloudflare + R2 backup** | **Phù hợp nhất với ba mẫu và yêu cầu giữ Python** | **Chọn cho MVP; R2 chỉ giữ bản sao ngoài VPS** |

R2 Standard có miễn phí 10 GB-tháng, 1 triệu thao tác Class A và 10 triệu Class B mỗi tháng; vượt mức có tính phí. Egress R2 miễn phí, không có nghĩa mọi dịch vụ Cloudflare đều miễn phí. [Bảng giá R2](https://developers.cloudflare.com/r2/pricing/).

Ví dụ minh họa Containers, không phải báo giá tải thật: cấp 4 GiB RAM và bật 720 giờ/tháng, riêng RAM khoảng (4 × 720 − 25) × 3600 × 0,0000025 = **25,695 USD**; cộng Workers Paid 5 USD thành khoảng **30,70 USD**, chưa tính đĩa/CPU và phần khác. Cho container ngủ sẽ giảm phí nhưng phải nạp lại môi trường/index. Không khẳng định Containers luôn đắt; chỉ không chọn mặc định giữ index nóng cả ngày trong ngân sách này. [Giá Containers](https://developers.cloudflare.com/containers/platform/pricing/).

### 2.2. Gói VPS đề xuất

Giá niêm yết tra ngày 30/10/2026 tại [VPS GOLD](https://vpssieutoc.vn/store/vps-gold), không tính mã giảm giá:

| Gói | vCPU | RAM | SSD | Giá/tháng | Nhận định |
|---|---:|---:|---:|---:|---|
| GOLD 4 | 2 | 4 GB | 50 GB | 160.000đ | Chỉ chọn để tiết kiệm nếu benchmark chứng minh đủ RAM |
| GOLD 5 | 3 | 6 GB | 60 GB | 250.000đ | Mức trung gian |
| **GOLD 8** | **4** | **8 GB** | **80 GB** | **320.000đ** | **Cấu hình mặc định đề xuất** |

Chọn **GOLD 8, Ubuntu 24.04 LTS, thanh toán từng tháng**. Trước khi mua, đối chiếu tổng tiền gồm thuế/phụ phí/tỷ giá với trần 15 USD; không dựa vào khuyến mãi để bảo đảm ngân sách. Nếu vượt trần, báo Khầy số tiền cụ thể, không tự nâng ngân sách hoặc trả nhiều tháng.

Cơ sở chọn RAM: Finance–Tax khoảng 608 MiB; TF-IDF nén khoảng 383 MiB. Khảo sát header NPZ, không thực thi pickle, cho thấy các mảng giải nén khoảng **539 MiB**, 80.204 hàng. Python, metadata, tìm kiếm và dựng index cần bộ nhớ bổ sung. Đây chưa phải peak RAM đã benchmark. RAM 8 GB dành chỗ cho API/PostgreSQL/runner, không phải cam kết nhiều tác vụ nặng đồng thời.

Giá và cấu hình là thông tin nhà bán công bố, chưa chứng minh hiệu năng CPU chia sẻ, uptime, backup, SLA hay hoàn tiền. G0 phải kiểm tra: quyền root/Docker, hệ điều hành, thuế, nâng cấp RAM/đĩa, phí backup, điều khoản thử/hoàn tiền và kết nối tới AI cloud. Không mua control panel hoặc license Windows.

### 2.3. Ngân sách vận hành

- VPS là chi phí chính: 320.000đ/tháng theo lần tra này; tổng checkout phải nằm trong trần đã chốt.
- Cloudflare DNS/proxy dùng gói hiện có; không cần Workers Paid cho kiến trúc này.
- R2 Standard cho backup, mục tiêu dưới 8 GB để có khoảng đệm so với hạn mức 10 GB. Tính cả bucket khác của tài khoản.
- Chi phí R2 bằng 0 chỉ là mục tiêu khi nằm trong hạn mức; cảnh báo của Hub không phải hard cap hóa đơn Cloudflare.
- Không thêm dịch vụ trả phí, email giao dịch hoặc embedding API trong MVP.
- Lượt chỉnh tài liệu này không mua VPS, kích hoạt R2 hoặc đổi DNS.

## 3. Kiến trúc và nền móng nhiều người dùng

### 3.1. Các thành phần

Luồng chính: **AI cloud/trình duyệt → Cloudflare → Caddy trên VPS → API/MCP → PostgreSQL + SSD + Python runner**. Tác vụ backup chuyển bản sao mã hóa sang R2.

- Backend: **Python 3.12, FastAPI, SDK MCP Python chính thức v2, Pydantic, SQLAlchemy và Alembic**. G0 xác minh phiên bản tương thích và tạo lockfile; không nhầm SDK chính thức với package fastmcp bên thứ ba.
- Frontend: React + TypeScript + Vite. Frontend chỉ là giao diện; công thức chuyên ngành vẫn chạy Python ở server.
- PostgreSQL 18 lưu user, plugin, project, OAuth, job và audit; dùng một engine từ MVP tới beta nhiều người.
- Docker Compose gồm caddy, api, worker, postgres và image runner được duyệt. MVP dùng bảng job PostgreSQL có lease/heartbeat, chưa cần Redis/Celery.
- Worker nội bộ điều phối container bằng quyền giới hạn cấu hình. API public và container plugin không được mount Docker socket. Worker có quyền Docker là thành phần đặc quyền, tuyệt đối không nhận image/command/mount tùy ý từ client.
- Chỉ Caddy nhận lưu lượng public. Database/runner không mở cổng ra Internet.
- Volume bền vững giữ database/file qua restart và cập nhật image.

| Địa chỉ dự kiến, chưa triển khai | Chức năng |
|---|---|
| https://goodmcp.si | Giới thiệu và hướng dẫn |
| https://admin.goodmcp.si | UI, đăng nhập, REST API cùng origin |
| https://mcp.goodmcp.si/mcp | Streamable HTTP MCP |
| https://auth.goodmcp.si | OAuth authorize/token/discovery |
| https://www.goodmcp.si | Redirect về tên miền chính |

Tổ chức mã: apps/api cho API/MCP/auth; apps/web cho UI; packages/core cho nghiệp vụ; packages/plugin-adapters cho định dạng/công cụ; runners cho runtime; infra cho Compose/proxy/backup; tests và Docs/reports. Không sửa/di chuyển plugin_example khi tích hợp.

### 3.2. Mô hình dữ liệu

| Nhóm | Nội dung |
|---|---|
| users, workspaces, memberships | Tài khoản, vùng dữ liệu, vai trò owner/admin/member/viewer |
| plugin_packages, plugin_versions, installations | Gói nguồn, phiên bản bất biến, bật/tắt/ghim trong workspace |
| skills, agents, resources, tool_bindings | Kỹ năng, chuyên gia, tài nguyên, adapter công cụ |
| projects, artifacts, stage_commits | Dự án, đầu ra, revision và checkpoint |
| jobs, job_attempts, audit_events | Công việc nền, lần thử và hoạt động |
| connections, oauth_grants, tokens, host_profiles | Kết nối AI, quyền cấp, token và capability |

Các ràng buộc phải có ngay:

- Mọi dữ liệu riêng, job, file, cache và truy vấn search gắn workspace_id. Khóa/tham chiếu phải bảo đảm cùng workspace.
- Danh tính lấy từ token/session xác thực. Workspace client gửi chỉ là lựa chọn cần kiểm tra membership.
- PostgreSQL bật Row-Level Security trên bảng riêng tư; runtime không dùng owner/superuser/BYPASSRLS. Migration dùng tài khoản riêng; context workspace đặt theo transaction, không rò qua connection pool.
- Storage key do server tạo có namespace workspace; đường dẫn do AI gửi không phải quyền truy cập filesystem.
- Plugin mặc định private. Chia sẻ cho người khác cần quyền phân phối; OPC Team hiện ghi CC-BY-NC-SA-4.0, không tự đưa vào marketplace thương mại.
- ArtifactStore có put/get/delete/stream; filesystem là backend đầu tiên. Backend R2/S3 tương lai không làm đổi hợp đồng MCP/UI.
- Registry nạp plugin từ database. Thêm gói tài liệu thứ tư không cần sửa core/redeploy; executable mới cần adapter/image đã duyệt.
- Production seed một owner/một workspace, public signup và invitation tắt; test vẫn phải có hai workspace.

## 4. Nhập plugin và giữ runtime Python

### 4.1. Quy trình nhập/cập nhật

1. UI tải ZIP theo chunk 8 MiB, có resume; không gửi một request hàng trăm MB qua Cloudflare.
2. Server kiểm tra hash/tổng dung lượng rồi đưa vào vùng chờ. Giới hạn ban đầu: ZIP 1 GiB, giải nén 3 GiB, 10.000 file; cấu hình được theo workspace.
3. Job nhận diện root plugin.json, overlay .codex-plugin/.codebuddy-plugin, skills/ và agents/. Manifest xung đột phải báo, không đoán.
4. Kiểm tra path traversal, symlink, file trùng, dung lượng, secret và tham chiếu; không thực thi script lúc scan.
5. Giữ ZIP và cây nguồn bất biến; tạo catalog chuẩn hóa riêng. _backup_zh giữ trong gói gốc nhưng không index hoạt động mặc định.
6. Hiện preview: nguồn/giấy phép, vai trò, tài liệu, runtime và công cụ đã/chưa hỗ trợ.
7. Chỉ kích hoạt sau khi kiểm tra bắt buộc đạt; cập nhật lỗi không làm hỏng bản đang phục vụ.

Version nhận dạng bằng phiên bản manifest + SHA-256. Cùng số phiên bản nhưng khác nội dung có revision riêng. Dự án ghim phiên bản; giữ ba phiên bản chưa ghim theo mặc định, không tự xóa bản đang được project sử dụng. Có xuất ZIP gốc và xuất dữ liệu project theo quyền.

### 4.2. Hợp đồng gọi Python

Mỗi ToolBinding khai báo tên MCP, schema input/output, adapter ID, digest image, plugin version, timeout, RAM/CPU và quyền mạng/file. Client chỉ truyền tham số nghiệp vụ; không truyền lệnh shell, module, image hay mount.

- Runner dùng CPython/Linux. Dependency được khóa và cài khi build image, không pip install mỗi lượt gọi hoặc theo yêu cầu từ ZIP.
- Finance–Tax image có NumPy, SciPy, scikit-learn, BeautifulSoup theo code thật. README nói không cần dependency không thay thế kiểm tra source.
- Wrapper Python gọi hàm/module gốc, chuyển JSON thành tham số và chuẩn hóa output/lỗi; không đổi công thức để dễ triển khai.
- Khi gọi CLI, dùng danh sách argument, không shell=True; kiểm tra exit code, phân biệt stdout dữ liệu và stderr log. Thất bại subprocess không được trả thành công.
- Plugin mount read-only; chỉ thư mục job riêng được ghi. Runner non-root, bỏ Linux capabilities, giới hạn PID/CPU/RAM, không mạng mặc định, không nhận secret quản trị/database/Cloudflare.
- Container cho code đã duyệt giảm tác động, chưa đủ để nhận mã thù địch công khai. Muốn người lạ chạy code cần sandbox mạnh hơn ở giai đoạn sau.

### 4.3. Tác vụ dài và tài nguyên

- Budget đồng bộ 10 giây; việc lâu hơn trả job_id, theo dõi/hủy qua hub_get_job và hub_cancel_job. Không giữ một request MCP nhiều phút để dựng index.
- Job có queued/running/succeeded/failed/cancelled, lease, heartbeat, attempts và deadline. Kiểm tra quyền trên mọi lần poll/cancel/lấy output.
- Idempotency key gắn workspace/thao tác; retry không nhân đôi tác dụng ghi. Crash hết lease được xử lý, không đánh dấu thành công nếu chưa có kết quả bền vững.
- MVP tối đa 2 job máy tính đồng thời, queue 20 job/workspace. Liệt kê/tìm từ khóa/đọc tài liệu là công cụ đọc có phân trang, không tạo job TF-IDF.
- Máy tính giới hạn 30 giây/256 MiB. Không chạy builder/index/search process nặng trong MVP; các ngân sách search 3 GiB/build 5 GiB ở nghiên cứu G0 là tài liệu cho giai đoạn sau.
- Context và đường dẫn job tách workspace. Công cụ tài liệu kiểm quyền và installation trên mỗi lần đọc; lưu plain text để tìm từ khóa không cấp quyền bỏ qua tenant.

### 4.4. Tích hợp từng mẫu

**OPC Team**

- Giữ 9 vai trò, lead tại cuộc chat chính, các bước phụ thuộc chạy tuần tự.
- Folder logic opc-doc/ ánh xạ sang project/artifact store; lưu output, decision, assumption rồi commit stage bằng transaction.
- Specialist trả đề xuất, lead hợp nhất trạng thái theo workflow. Quyền bảo mật vẫn dựa token/workspace, không tin lời tự khai role=lead.
- Có revision check và idempotency; draft không tự hoàn thành bước, cập nhật cạnh tranh không ghi đè lịch sử.

**Godot–Roblox**

- Giữ đủ 6 hồ sơ, lấy hướng dẫn và lưu mã/tài liệu.
- Godot/Roblox Studio phải do host cung cấp hoặc có runner bổ sung sau; không đồng nhất nhập hồ sơ với chạy game engine.

**Finance–Tax**

- Bọc trực tiếp calculators.py, location_sim.py, tariff.py, refs.py. Kiểm tra CIT/schedule/payroll/FCT/tariff/địa điểm/compliance/ODI bằng cùng tham số với bản Python gốc.
- MCP MVP cung cấp **liệt kê tài liệu, tìm từ khóa literal và đọc plain text theo trang**. AI đang chat tự chọn từ khóa, đọc nguồn và tổng hợp; Hub không thêm model API hoặc tự đóng vai agent suy luận.
- Không FTS, embedding hoặc semantic ranking trong MVP. Không chạy search_corpus.py/build_index.py, không nạp pickle/NPZ từ ZIP. TF-IDF hoặc tìm kiếm nâng cao sẽ được đánh giá sau theo nhu cầu thật.
- Đọc nội dung tài liệu từ source resource bất biến, không coi preview trong metadata supplied là toàn văn. Trả handle nguồn, SHA-256 và offset trang; không tạo điểm relevance gây hiểu nhầm.
- Giữ PDF gốc và báo rõ PDF chưa trích text/OCR. HTML chỉ tách chữ, không render script; các file đã quarantine ở G3 không tham gia tìm/đọc active.
- Widget MVP gọi cùng tool Python. Không dùng kết quả công thức JS trong HTML cũ làm số liệu chính; HTML chưa review không chạy script trên origin quản trị.
- Ghi nguồn/ngày dữ liệu/giả định. Khớp chương trình gốc chứng minh tích hợp đúng, không chứng minh nội dung thuế được kiểm toán pháp lý.

## 5. MCP, OAuth và khả năng nền tảng

### 5.1. Giao thức và công cụ

SDK Python v2, **MCP 2026-07-28, Streamable HTTP**; client kiểm tra pin đúng revision. Đường tương thích cũ chỉ bật/test theo nhu cầu host đã chứng minh; không suy protocol từ tên hãng, không downgrade vì 401/403/5xx. Nghiệp vụ dùng project/job ID, không dùng phiên MCP làm database.

| Nhóm | Công cụ |
|---|---|
| Catalog | hub_list_plugins, hub_open_plugin, hub_get_skill, hub_get_agent |
| Tài liệu | hub_list_documents, hub_search (từ khóa), hub_read_document, hub_read_resource |
| Quy trình | hub_prepare_workflow, hub_open_project, hub_read_project |
| Lưu kết quả | hub_save_artifact, hub_commit_stage |
| Job | hub_get_job, hub_cancel_job |
| Chẩn đoán | hub_connection_info |
| Chuyên ngành | Tool Python có tên/schema riêng; không có execute_shell tổng quát |

Tên snake_case ổn định, tối đa 64 ký tự; JSON input object có giới hạn độ dài/số lượng. Trả text ngắn, structured output, nguồn và cursor. Schema tương thích được kiểm tra, không bỏ validation để nối được host.

Khả năng cốt lõi đều có đường qua tools, không phụ thuộc resources/prompts/MCP Apps. Tool list chỉ chứa plugin được bật và được quyền dùng; mỗi invocation kiểm tra lại quyền/trạng thái dù host cache tên cũ. Nạp skill/tài liệu theo nhu cầu, không đổ toàn corpus vào context.

### 5.2. Xác thực trên VPS

- Dùng Authlib cho OAuth, tích hợp API và SDK MCP; không coi SDK MCP đã cung cấp sẵn đầy đủ authorization server/trang login. G0 phải chứng minh ASGI/auth integration trước khi làm UI lớn.
- Owner bootstrap bằng lệnh cài đặt, password hash Argon2id, không hard-code credential; session Secure/HttpOnly/SameSite, CSRF, rate limit đăng nhập. Trước production bật TOTP, recovery code giữ ngoài VPS.
- OAuth Authorization Code + PKCE S256, exact redirect URI, discovery cho authorization server/protected resource; kiểm tra issuer/resource/audience/scope/expiry, refresh rotation và revoke.
- Hỗ trợ CIMD và DCR tương thích theo host; fetch client metadata chỉ HTTPS và chặn truy cập mạng riêng/redirect nguy hiểm.
- Grant/token gắn user/workspace/client/scope. Access token ngắn hạn; opaque token chỉ lưu hash; credential cần khôi phục phải mã hóa bằng khóa ngoài DB dump.
- API/CLI có token riêng, thu hồi riêng. Không dùng Cloudflare token hoặc khóa AI provider làm token Hub.
- Scope đọc plugin/tài liệu, gọi tool, đọc/ghi project. Cài/xóa plugin/quản lý user chỉ ở UI admin, không qua MCP trong MVP.
- MCP/discovery/token không bị trang login Cloudflare Access, CAPTCHA hay JS challenge chặn. HTTPS strict tới origin; không cache auth/API/MCP hoặc tài liệu riêng tư.

### 5.3. Host và model

| Host | Đường tích hợp | Ranh giới |
|---|---|---|
| ChatGPT | Custom MCP/Plugins nếu tài khoản có quyền | Không tự đổi model chat hoặc mặc định có subagent |
| Claude | Remote connector; cấu hình Claude Code riêng | Không gộp khả năng chat và CLI |
| Gemini | Custom app khi đủ điều kiện; CLI/API bổ sung | Kiểm tra theo sản phẩm, model, tài khoản và khu vực |
| Grok | Custom connector, mẫu API | Multi-agent của hãng không đồng nghĩa đội vai trò của plugin |

Giới hạn hãng trong khảo sát trước là ảnh chụp ngày 30/10/2026; G7 phải đọc lại tài liệu và thử tài khoản thật. Host bị chặn do tài khoản/model ghi blocked_by_host, không đánh dấu pass.

Host profile ghi khả năng file/tool/subagent/model selection. Plugin khai báo vai trò nhẹ/phân tích/lập trình và ưu tiên gốc. Không đổi selector Codex thành API ID khác hãng bằng phỏng đoán. Ghi requested_model, reported_model, nguồn chứng cứ/thời điểm; không biết thì unknown.

Thiếu subagent: AI hiện tại làm tuần tự. Có native subagent được host cho phép: cấp brief, đầu vào, quyền ghi và đầu ra cho từng vai trò. Hub không spawn model trả phí; lời dẫn nhiều vai trò không phải bằng chứng chạy nhiều agent.

## 6. Vận hành, sao lưu và mở rộng

### 6.1. Vận hành MVP

- Health/readiness, restart policy, JSON log có request/job ID và xoay log; không ghi secret/toàn văn tài liệu mặc định.
- Dashboard RAM/CPU/đĩa, queue, lỗi, latency và backup. Đĩa 70% cảnh báo, 85% dừng upload/index mới, giữ khoảng trống cho DB/khôi phục.
- SSH key, firewall, cập nhật bảo mật; không public DB/runner. Secret không vào Git, image hoặc plugin.
- Một VPS là điểm lỗi duy nhất, chưa có HA. Mục tiêu RPO 24 giờ, RTO 4 giờ chỉ công nhận sau backup/restore thực tế.

### 6.2. Backup dữ liệu mới

Không backup rác cũ không có nghĩa bỏ backup dữ liệu mới của Hub.

- R2 Standard bucket private, backup phía client mã hóa bằng restic; credential giới hạn bucket, khóa giải mã lưu ngoài VPS.
- Hằng đêm PostgreSQL dump nhất quán và manifest file tương ứng. Tạm chặn ghi lúc tạo snapshot; blob bất biến, không garbage-collect file thuộc snapshot. Không chỉ copy thư mục PostgreSQL đang chạy.
- Backup ZIP gốc, metadata, project/artifact và cấu hình cần khôi phục. Không backup Docker cache/venv/log/index tái tạo được.
- Giữ 7 bản ngày + 4 bản tuần có dedup; theo dõi dung lượng thật, không giả định luôn dưới 8 GB.
- Gần hết hạn mức: dọn theo retention và cảnh báo. Không xóa bản tốt cuối cùng để đạt quota; backup lỗi hoặc quá 24 giờ phải hiện rõ.
- Restore vào môi trường sạch, kiểm tra hash, login, project và tool Python. Backup chưa restore chưa được tính đạt.
- Nếu R2 chưa kích hoạt, bản thử private có thể tải backup mã hóa về máy Khầy; chưa đạt mục tiêu production backup tự động.

### 6.3. Giai đoạn mở rộng sau MVP

**G9 — Nhiều người được mời:** invitation, role thật, quota và audit theo user; kiểm tra isolation lại. Chỉ admin duyệt runtime; kiểm tra quyền phân phối plugin trước chia sẻ, chưa cho người lạ chạy code.

**G10 — Nhiều plugin/tải lớn:** chuyển blob chính sang R2 qua ArtifactStore, giữ cache nóng runner; migration theo hash và kiểm tra trước đổi pointer. Tách runner sang máy khác nếu peak RAM vượt 75% hoặc queue chờ trên 30 giây kéo dài. Scale API/database theo số đo, không tự chuyển sang microservice.

**G11 — Plugin công khai:** review/chữ ký/nguồn phát hành, sandbox mạnh hơn container dùng chung, egress policy, quét dependency, quota/billing và quy trình gỡ plugin. Không bật chỉ bằng mở nút đăng ký.

## 7. Giai đoạn giao việc cho AI agent

### 7.1. Quy tắc bàn giao

Agent đọc PLAN.md, hướng dẫn repo và báo cáo giai đoạn trước; chỉ sửa phần được giao, giữ thay đổi của người khác. Không tự mua dịch vụ, mở đăng ký công khai, gọi model tính phí hoặc triển khai ngoài phạm vi nhiệm vụ.

Mỗi giai đoạn ghi **Docs/reports/Gx.md**: mục tiêu, file phụ trách/thay đổi, quyết định, lệnh kiểm tra thật, kết quả, số đo, lỗi còn lại và bước tiếp theo. Trạng thái not_started/in_progress/passed/blocked; thiếu chứng cứ không ghi passed. Không đưa secret vào báo cáo.

G1 tạo entrypoint **scripts/verify.ps1 -Stage Gx** cho Windows và **scripts/verify.sh Gx** cho Linux, cùng gọi bộ kiểm tra trong Compose. Đây là lệnh cần xây dựng, chưa tồn tại/chưa chạy ở thời điểm viết kế hoạch.

| Giai đoạn | Phụ thuộc | Phần phụ trách | Kết quả |
|---|---|---|---|
| G0 | Không | inventory, benchmark, runtime/auth PoC | Chứng minh khả thi trước thuê máy |
| G1 | G0 | core, DB, Compose, test harness | Nền local, isolation |
| G2 | G1 | OAuth/MCP | Kết nối xác thực, tool thử |
| G3 | G1–G2 | import/storage/registry | Ba plugin có version |
| G4 | G3 | runner/adapters/corpus | Python chạy thật |
| G5 | G3–G4 | workflow/project/host profiles | Lưu và tiếp tục công việc |
| G6 | G2–G5 | UI/kết nối | Khầy dùng không cần CLI |
| G7 | G2–G6 | integration/QA | Chứng cứ từng nền tảng |
| G8 | G0–G7 | deploy/DNS/backup/runbook | MVP production |

Mặc định giao tuần tự. Nếu Khầy giao nhiều agent, chỉ song song phần độc lập sau khi API/schema chung được chốt; mỗi agent có phạm vi sở hữu rõ.

### G0 — Khảo sát, benchmark và chốt hợp đồng

- Inventory/hash ba gói, dependency, tool và tham chiếu; không thực thi pickle/code chưa review.
- Chạy code đã duyệt trong image local dự kiến: calculator, refs, search và build index. Đo peak RSS, CPU, thời gian cold/warm/build và đĩa; lưu lệnh tái hiện.
- PoC SDK Python v2 qua HTTP thật và OAuth dựa Authlib: login → PKCE authorize → token → tool. Xác định rõ adapter ASGI cần viết, không giả định thư viện có sẵn tất cả.
- Chốt contract API/job/adapter/storage/tenant, lock dependency và ADR cấu hình GOLD 8. Xác minh giá/điều kiện nhà bán, chưa mua máy.
- **Nghiệm thu:** ít nhất một máy tính và một query corpus chạy được; có số đo RAM; wire/auth PoC có chứng cứ; chỉ rõ khả năng chạy 8 GB và build offline nếu cần.
- **Prompt giao:** “Thực hiện G0 trong Docs/PLAN.md, chỉ PoC/benchmark local; giữ nguyên plugin_example, không đổi Python sang JS/FTS; bàn giao Docs/reports/G0.md và contract cho G1.”

### G1 — Nền ứng dụng và dữ liệu

- Tạo layout, Compose, migrations, health, config mẫu, lockfiles và scripts verify.
- User/workspace/membership, bảng nền plugin/project/job/auth; transaction context/RLS, filesystem namespace.
- Bootstrap owner local bằng script; tạo hai tenant test; credential chỉ từ secret/environment.
- **Nghiệm thu:** checkout sạch dựng được; restart không mất dữ liệu; migrations đạt; A không đọc/ghi DB/file B; pool không giữ tenant cũ.
- **Prompt giao:** “Thực hiện G1, sở hữu core/DB/infra local, dùng contract G0; không deploy cloud; chạy verify G1 và ghi báo cáo.”

### G2 — Xác thực và MCP tối thiểu

- Hoàn thiện OAuth/grant/scope/revoke, MCP handlers và tool thử có quyền đọc; conformance client.
- Kiểm tra modern pin 2026-07-28 qua HTTP, discovery, invalid schema/header/version; legacy test riêng khi có nhu cầu thật.
- Thử một host cloud trên endpoint thử được giới hạn quyền nếu khả dụng; thiếu tài khoản ghi blocker, không thay bằng pass local.
- **Nghiệm thu:** token thiếu/hết hạn/sai audience/workspace bị chặn; PKCE sai, code replay, redirect sai, refresh replay bị từ chối; không bypass qua route khác.
- **Prompt giao:** “Thực hiện G2 với phạm vi OAuth/MCP; không mở rộng runtime nghiệp vụ; bàn giao cấu hình kết nối, wire tests và G2.md.”

### G3 — Kho plugin

- Chunk upload/resume, vùng chờ, validator ba định dạng, resources, version/install/disable/export.
- Nhập đủ ba mẫu nguyên bản; thêm fixture plugin thứ tư nhỏ chỉ có skill để chứng minh core không hard-code.
- **Nghiệm thu:** đủ 3 plugin/16 vai trò; hash file/ZIP khớp; bản mới lỗi không hỏng bản hoạt động; chặn ZIP path traversal/bomb; không import module lúc scan; không truy cập chéo workspace.
- **Prompt giao:** “Thực hiện G3, sở hữu importer/registry/storage và test; dùng API G1/G2, chưa viết lại công cụ Python; bàn giao G3.md.”

### G4 — Công cụ Python và corpus

- Image Finance–Tax, tool schemas, adapters, worker/job/poll/cancel và resource limits.
- Bọc hàm/CLI gốc; MCP liệt kê, tìm từ khóa literal và đọc tài liệu theo quyền; AI agent tự điều phối. Không xây/benchmark TF-IDF trong MVP.
- Ít nhất 30 test công cụ: CIT qua các mốc miễn/giảm và lỗ, payroll biên, FCT hai chiều, tariff/địa điểm/refs; kiểm tra JSON, exit code và rounding với baseline gốc.
- Kiểm thử từ khóa/cụm từ, Unicode, all/any, phân trang/toàn văn, nguồn/hash, PDF chưa trích text, quarantine và tenant; không yêu cầu recall@5 hoặc semantic QA cho lookup literal.
- **Nghiệm thu:** wrapper khớp baseline; công cụ đọc tài liệu còn đáp ứng khi hai job Python chạy; timeout/cancel/crash có trạng thái thật; runner không đọc secret/tenant khác hoặc ra mạng trái quyền; đo tài nguyên toàn Compose và thời gian lookup/call Python local.
- **Prompt giao:** “Thực hiện G4, sở hữu runners/adapters, giữ Python; bàn giao parity tests, benchmark và G4.md; không thêm model API.”

### G5 — Workflow và dữ liệu dự án

- Project/artifact/decision/assumption/stage commit có revision/idempotency; giữ logical paths OPC.
- Brief vai trò, tuần tự/native delegation theo host; requested/reported model ghi trung thực.
- **Nghiệm thu:** chat khác tiếp tục đúng bước/version; draft không chuyển bước; xung đột không mất lịch sử; thiếu subagent không giả kết quả; output ghim đúng plugin version.
- **Prompt giao:** “Thực hiện G5 theo hợp đồng OPC và tenant core; không gọi LLM API; kiểm tra resume/conflict và bàn giao G5.md.”

### G6 — User Portal và Admin Dashboard

- **Trạng thái 31/10/2026:** G6 local đạt: build, 46 UI tests, 1 live React→Python/revoke, 45 kiểm tra backend và HTTP/MCP 26/26 ở hai phiên độc lập; đã đóng lỗi runtime/revoke. Xem [G6.md](reports/G6.md), không suy thành production readiness.
- Đặc tả trước triển khai: [G6-UI.md](design/G6-UI.md); frontend React/TypeScript/Vite trong apps/web, dùng chung backend và OAuth G2; giữ nguyên API, schema và nghiệp vụ G1–G5.
- **User Portal:** trang chủ theo UI-mock/GoodMCP_landing_page.png, hiệu ứng stackedlol/ascii-sharks có giấy phép MIT, danh mục private chỉ sau xác thực, mô tả dễ hiểu, hướng dẫn từng nền tảng, URL MCP có nút sao chép và nhãn placeholder trước deploy. Không đăng ký công khai, billing, marketplace hoặc công khai plugin riêng.
- **Admin:** đúng 5 nhóm Tổng quan; MCP & Plugin; Dự án; Người dùng & Kết nối; Hệ thống. Thao tác thường dùng ở danh sách; versions/rollback, tài liệu và Python nằm trong chi tiết.
- Upload ZIP chunk 8 MiB/resume theo trạng thái server, preview rồi bật; version/revision chống ghi đè; tài liệu plain text; form theo input_schema gọi Python, theo dõi/hủy job theo ID; tải ZIP gốc. Dự án đọc/resume, tạo và lưu draft qua G5.
- Chỉ xây hành động có API thật. G2 hỗ trợ đăng nhập/consent và revoke grant hiện tại; chưa có API liệt kê/quản trị người dùng, toàn bộ kết nối, logs, số liệu tài nguyên, backup hoặc export toàn bộ project. Các mục này hiển thị lý do chưa hỗ trợ, không tạo dữ liệu giả/nút thành công giả. File project đọc/tải từng trang, không gọi đó là export toàn bộ.
- **Nghiệm thu:** nhập/bật plugin và chạy tool bằng form; không sửa JSON/lệnh tay cho schema hỗ trợ; UI tests trạng thái loading/empty/error/success, auth/role/quota/conflict, upload retry/resume, XSS, bàn phím và responsive. Báo cáo tách test fixture, API local thật và kiểm tra trình duyệt; không suy thành G7 hay production.
- **Bàn giao:** Docs/reports/G6.md, evidence kiểm thử, chức năng hoàn thành và giới hạn API. Không gọi LLM, nhân đôi công thức Python, sửa plugin_example hoặc triển khai G7–G8.
- **Prompt giao:** “Thực hiện G6 theo Docs/design/G6-UI.md; sở hữu apps/web và UI tests; kiểm API thật trước mỗi chức năng, giữ G1–G5; bàn giao G6.md với giới hạn và chứng cứ local.”

### G7 — Nghiệm thu chéo nền tảng

- Thử ChatGPT/Claude/Gemini/Grok theo tài khoản có thật; tách web/desktop/CLI/API và model.
- Kịch bản chung: login, list/open plugin, đọc skill, search, tính toán, poll job, lưu/mở lại project và revoke.
- Đọc lại tài liệu hãng; chỉ chạy model API khi Khầy cấp khóa/ngân sách riêng. Validate cấu hình không phải inference test.
- Ghi verified_live/protocol_only/blocked_by_host/unsupported, ngày, tài khoản/host/model, protocol, bước tái hiện và log đã bỏ secret.
- **Nghiệm thu:** ít nhất một host cloud chính của Khầy đạt end-to-end; cả bốn có báo cáo, blocker không tính pass. Chỉ công bố hỗ trợ cả bốn khi từng đường công bố có live pass. Sửa lỗi quyền/mất dữ liệu/tính sai/giả kết quả trước G8.
- **Prompt giao:** “Thực hiện G7 bằng chứng thực tế; không hạ tiêu chuẩn để có bốn dấu xanh; báo cáo từng host và tổng hợp G7.md.”

### G8 — Production và bàn giao vận hành

- Khi được giao triển khai: kiểm tra tài nguyên/giá cuối, chuẩn bị production Compose, SSH/firewall/TLS/secrets/migrations và image có version. Mua VPS/kích hoạt R2 theo chỉ định/ngân sách Khầy, không phát sinh từ nhiệm vụ sửa tài liệu.
- Kiểm kê lại trước đổi DNS. Ảnh chụp khảo sát trước: web ở Vercel project ai, mcp.goodmcp.si ở Tunnel goodmcp-blender; promptchien và AutoCAD không liên quan. Không xem ảnh chụp cũ là trạng thái chắc chắn lúc deploy.
- Deploy endpoint thử, smoke OAuth/Python/tools; chuyển hostname sang VPS, Full (strict), upload chunk, timeout phù hợp, không cache/challenge MCP.
- Sau kiểm kê, gỡ binding goodmcp khỏi Vercel/Tunnel cũ; chỉ xóa project rác nếu không có nội dung ngoài phạm vi. Không backup rác; không xóa promptchien/AutoCAD/email.
- R2 backup mã hóa, restore vào DB/volume sạch; runbook update/rollback/migration, queue lỗi và hết đĩa. Không rollback bằng schema downgrade làm mất dữ liệu.
- **Nghiệm thu:** production end-to-end, restart/restore đạt, RAM/latency trong giới hạn đã chốt, backup ngoài VPS xác minh được; agent khác vận hành được từ source/config mẫu/runbook.
- **Prompt giao:** “Thực hiện G8 sau khi đọc các báo cáo; chỉ deploy tài nguyên/ngân sách được giao, kiểm kê trước dọn; bàn giao URL thật, production/restore evidence và G8.md.”

## 8. Điều kiện bàn giao và nguồn

MVP hoàn thành khi Khầy quản lý ba plugin trên web, một host cloud đã thử gọi được Python/tài liệu/workflow, dữ liệu khôi phục được và kiến trúc vượt kiểm thử hai workspace. Nhập một plugin không đồng nghĩa mọi host có tất cả công cụ chuyên môn mà plugin nhắc tới.

Bàn giao: source runnable, image/lockfile, migrations, dữ liệu nhập/checksum, scripts verify, test fixtures, G0–G8 reports, cấu hình từng host, runbook backup/restore/update, bảng capability/giới hạn và lộ trình G9–G11. Build pass hoặc tài liệu đơn thuần chưa chứng minh sản phẩm chạy thật.

Nguồn giá/kỹ thuật cần kiểm tra lại lúc triển khai:

- [VPS GOLD](https://vpssieutoc.vn/store/vps-gold).
- [R2 object storage](https://developers.cloudflare.com/r2/) và [giá R2](https://developers.cloudflare.com/r2/pricing/).
- [Containers pricing](https://developers.cloudflare.com/containers/platform/pricing/).
- [Python Workers/Pyodide](https://developers.cloudflare.com/workers/languages/python/how-python-workers-work/).
- [SDK MCP Python v2](https://py.sdk.modelcontextprotocol.io/) và [authorization](https://py.sdk.modelcontextprotocol.io/run/authorization/).
- [MCP authorization 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization).
- [Authlib](https://docs.authlib.org/) và [PostgreSQL Row-Level Security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).
- [ChatGPT custom MCP](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt), [Claude remote connector](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp), [Claude API MCP](https://platform.claude.com/docs/en/agents-and-tools/mcp-connector).
- [Gemini custom apps](https://support.google.com/gemini/answer/17209137?hl=en-45), [Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling), [Grok connectors](https://docs.x.ai/grok/connectors).
