# GoodMCP — Kế hoạch triển khai G9, G10 và G11

> Trạng thái 02/11/2026: G9 đã triển khai production cho nhóm ba Google, có bốn
> workspace/bốn vai trò, mời/nhận qua link, hạ quyền và thu hồi thật. Chưa đóng
> toàn bộ nghiệm thu vì SMTP chưa có (Khầy đã xác nhận), ChatGPT web còn kết quả
> chưa xác minh. Responsive 320 px đã đạt trên browser local fixture. Chi tiết [báo cáo G9](reports/G9.md).
> G10/G11 chưa thực hiện; signup công khai vẫn tắt.

## 1. Mục tiêu và các quyết định đã chốt

Nâng GoodMCP thành dịch vụ nhiều người dùng, đăng nhập Google, dữ liệu tách theo workspace, frontend hoàn chỉnh và marketplace nhiều tác giả.

| Nội dung | Phương án triển khai |
|---|---|
| Đăng ký | Mọi người được đăng ký bằng Google |
| Người mới | Tự có một workspace cá nhân và gói miễn phí giới hạn |
| Dữ liệu nhóm | Thành viên xem chung plugin, dự án trong workspace; chưa phân quyền riêng từng dự án |
| Giao diện | Hoàn thiện React/TypeScript hiện có, giữ phong cách thiết kế |
| Doanh thu | Gói workspace và thuê từng plugin theo tháng |
| Quyền thuê plugin | Gắn với workspace; thành viên sử dụng theo vai trò |
| Thanh toán | SePay, VND, khách chủ động thanh toán/gia hạn bằng QR |
| Tác giả | Có thể đăng plugin miễn phí hoặc thu phí, phải qua xét duyệt |
| Python | Chỉ chạy mã và môi trường đã được quản trị nền tảng duyệt |
| Trả tác giả | Bản đầu đối soát và chuyển khoản thủ công; tự động chi tiền để sau |
| Quy mô nghiệm thu | Khoảng 100 tài khoản, 20 người dùng đồng thời |
| Chính sách thương mại | Giá, hạn mức, hoa hồng, hoàn tiền và kỳ chi cấu hình trước mở bán |

**Nền tảng giữ lại:** Python/FastAPI, PostgreSQL, React/Vite, công cụ Python và OAuth MCP hiện có. Giữ các địa chỉ `https://goodmcp.si/`, `/admin`, `/auth`, `/mcp`.

Theo báo cáo G8, hệ thống đã triển khai trên VPS nhưng còn thiếu backup ngoài VPS tự động và một số bằng chứng cloud. Kế hoạch phải kế thừa dữ liệu hiện có; không dựng lại tài khoản, plugin hoặc dự án từ đầu.

Triển khai tuần tự **G9 → G10 → G11**, mỗi giai đoạn gồm backend, frontend và kiểm thử tương ứng.

## 2. G9 — Google, nhiều người dùng và quyền workspace

**Kết quả:** người dùng đăng nhập, chọn workspace và làm việc đúng quyền; Khầy có khu quản trị toàn hệ thống riêng.

### G9.1 — Danh tính và phiên đăng nhập

- Tích hợp Google trực tiếp bằng OpenID Connect, chỉ xin thông tin đăng nhập cơ bản. Google xác minh người dùng; GoodMCP tiếp tục cấp quyền kết nối MCP.
- Thêm bảng danh tính liên kết, định danh bằng cặp nhà cung cấp và `sub`; không dùng email làm khóa danh tính và không tự nhập hai tài khoản chỉ vì trùng email. Kiểm chữ ký, issuer, audience, thời hạn, state và nonce theo [tài liệu Google](https://developers.google.com/identity/openid-connect/openid-connect).
- Liên kết Google với tài khoản chủ hiện tại qua phiên chủ đã xác thực. Giữ đường khôi phục quản trị hiện có trong thời gian chuyển đổi.
- Tạo tài khoản và workspace cá nhân trong một giao dịch; callback hoặc yêu cầu lặp không tạo bản sao.
- Web dùng phiên phía server với cookie `Secure`, `HttpOnly`, chống giả mạo yêu cầu ghi. Reload vẫn giữ đăng nhập; không lưu token trong localStorage.
- API xác minh phiên web qua dịch vụ auth nội bộ. MCP tiếp tục dùng bearer token; không chấp nhận cookie web để thay quyền MCP.
- Có đăng xuất phiên hiện tại, đăng xuất mọi thiết bị và khóa tài khoản. Khóa tài khoản phải vô hiệu hóa cả phiên web lẫn kết nối AI.

### G9.2 — Workspace và phân quyền

Thêm tạo/đổi tên/chuyển workspace, mời theo email, nhận lời mời, đổi vai trò, loại thành viên, rời workspace và chuyển chủ sở hữu.

| Vai trò | Quyền |
|---|---|
| Owner | Toàn quyền workspace; quản lý admin, chuyển quyền sở hữu, mua/gia hạn và lưu trữ workspace |
| Admin | Quản lý plugin, dự án, job; mời/quản lý member và viewer; xem sử dụng và nhật ký workspace |
| Member | Đọc tài liệu, chạy công cụ được phép, tạo và cập nhật dự án, quản lý kết nối của mình |
| Viewer | Chỉ đọc plugin và dự án được phép; không chạy Python hoặc ghi dữ liệu |

- Mỗi workspace có một owner; chuyển chủ phải nguyên tử, không để workspace mất chủ.
- Quyền quản trị toàn GoodMCP tách khỏi vai trò owner/admin workspace. Chủ workspace không được duyệt runtime, quản lý người dùng toàn hệ thống hoặc thay chính sách thương mại.
- Quyền truy cập được kiểm ở backend và PostgreSQL, không dựa vào nút ẩn trên UI.
- Lời mời dùng một lần, hết hạn sau 7 ngày, có thể thu hồi; gửi qua hàng đợi email SMTP. Nhận lời mời cần đúng email và bằng chứng kiểm soát địa chỉ email đó.
- Hạ quyền hoặc loại thành viên thu hồi các grant liên quan; kiểm lại quyền khi nhận yêu cầu, trước chạy job và trước công bố kết quả. Job chờ bị hủy nếu mất quyền.
- Chuyển workspace trên web không đổi workspace của kết nối MCP đã cấp. Muốn AI vào workspace khác phải cấp kết nối tương ứng.

### G9.3 — Frontend sử dụng và quản trị

- Thêm đăng nhập Google, chào mừng người mới, bộ chọn workspace, nhận lời mời, trang thành viên và tài khoản.
- Tạo khu làm việc `/app` cho cả member/viewer, sử dụng lại màn hình plugin, dự án và công cụ hiện có.
- Giữ `/admin` cho quản trị workspace với năm nhóm hiện tại; bổ sung `/platform` cho quản trị toàn hệ thống.
- Hoàn thiện danh sách kết nối AI: ứng dụng, workspace, người cấp, quyền, trạng thái và thu hồi. Người dùng quản lý kết nối của mình; owner/admin được thu hồi kết nối trong workspace.
- Thêm API thật cho các phần đang thiếu; không giữ nút báo thành công giả hoặc số liệu minh họa.
- API bổ sung theo nhóm: phiên/tài khoản, workspace, membership, invitation, connection và audit. Giữ các API nghiệp vụ trong `/api/v1/workspaces/{workspace_id}`.
- Danh sách workspace đầy đủ chỉ dành cho phiên web đã xác thực; token MCP vẫn bị giới hạn vào workspace được cấp.

**Nghiệm thu G9:** ít nhất ba tài khoản, hai workspace, đủ bốn vai trò; Google thật, mời/nhận, chuyển workspace, hạ quyền và thu hồi kết nối đều đạt. G9 thử với nhóm kiểm chứng; bật đăng ký công khai sau cổng vận hành G10.

## 3. G10 — Lưu trữ, hạn mức và vận hành beta công khai

**Kết quả:** hệ thống chịu được quy mô beta, có backup phục hồi được và không để một workspace chiếm hết tài nguyên.

### G10.1 — R2 và phục hồi dữ liệu

- Tách phần lưu file khỏi nghiệp vụ thành hai backend: filesystem và R2. Giữ hợp đồng đọc/ghi/xóa/stream của ArtifactStore.
- Dùng bucket private; mọi truy cập dữ liệu riêng qua kiểm quyền backend. Giữ upload chia phần và khả năng tiếp tục khi gián đoạn.
- Migration chạy lại được: sao chép → kiểm số byte và SHA-256 → đổi vị trí lưu trong database. Không coi ETag là SHA-256. Đối chiếu thao tác được hỗ trợ theo [R2 S3 API](https://developers.cloudflare.com/r2/api/s3/api/).
- Giữ bản filesystem trong cửa sổ rollback 14 ngày; chỉ dọn khi dữ liệu mới và backup đã được kiểm chứng.
- Backup mã hóa tự động ngoài VPS, tách bucket/quyền truy cập khỏi kho file đang phục vụ.
- Diễn tập phục hồi database, file, cấu hình và đăng nhập trên môi trường mới. Mục tiêu RPO 24 giờ, RTO 4 giờ chỉ ghi đạt khi có số đo.

### G10.2 — Hạn mức và công việc nền

- Đưa giới hạn đang viết cứng thành chính sách gói: dung lượng, thành viên, plugin, lượt chạy Python, số job chờ và số job đồng thời.
- Kiểm hạn mức bằng giao dịch database, có giữ chỗ trước upload/job để yêu cầu đồng thời không vượt giới hạn.
- Ghi mức sử dụng theo workspace và người thực hiện; retry cùng thao tác không tính hai lần.
- Xếp hàng công bằng giữa workspace. Ban đầu giữ tối đa hai job Python toàn hệ thống và một job đang chạy mỗi workspace.
- Không tự xóa dữ liệu khi hạ gói. Nếu vượt hạn mức, chặn thao tác làm tăng sử dụng và hướng dẫn dọn/nâng gói; vẫn cho đọc, xuất dữ liệu dự án của người dùng.
- Thêm giới hạn đăng ký, lời mời, upload và gọi API; có công tắc tạm dừng đăng ký mới khi hệ thống quá tải.

### G10.3 — Hoàn thiện màn hình vận hành

- Workspace: dung lượng, hạn mức, danh sách job, upload, nhật ký thành viên và lỗi cần xử lý.
- Quản trị nền tảng: tài khoản/workspace, khóa/mở, hàng đợi, tài nguyên, trạng thái backup và cảnh báo.
- Tài nguyên máy chủ và nhật ký toàn hệ thống chỉ hiện cho quản trị nền tảng.
- Cảnh báo khi backup quá 24 giờ, dung lượng đĩa vượt 80%, RAM vượt 75% hoặc hàng đợi chờ trên 30 giây kéo dài.
- Lập dự toán VPS, R2, email và máy chạy Python; chỉ kích hoạt dịch vụ sau khi Khầy chốt chi phí cụ thể.

**Nghiệm thu G10:** 20 phiên hoạt động trong 30 phút, mỗi phiên trung bình một yêu cầu/5 giây, kèm hai job Python/phút. Mục tiêu p95 API đọc ≤1 giây, ghi thông thường ≤2 giây, lỗi ngoài dự kiến <1%; upload/import/job đo riêng. Không OOM, không rò dữ liệu, backup/restore đạt. Sau đó mở beta đăng ký Google công khai.

## 4. G11 — Marketplace, thuê plugin và thanh toán

**Kết quả:** tác giả gửi plugin; Khầy duyệt; khách thuê theo workspace; hệ thống ghi nhận tiền và quyền sử dụng chính xác.

### G11.1 — Nhà phát hành và xét duyệt

- Người dùng đăng ký hồ sơ tác giả; quản trị duyệt trước khi được bán.
- Luồng phát hành: nháp → gửi duyệt → yêu cầu sửa/từ chối → duyệt → công khai → ngừng bán hoặc đình chỉ.
- Mỗi phiên bản giữ nguyên nội dung, hash, giấy phép, nguồn, kết quả kiểm tra và người duyệt. Thay nội dung hoặc dependency phải duyệt lại.
- Tách danh mục công khai khỏi bảng plugin riêng của workspace. Chỉ metadata và nội dung giới thiệu đã duyệt được công khai.
- Khi cài, tạo installation và dữ liệu thuộc workspace đích; không cấp quyền đọc workspace của tác giả.
- Không tự đưa ba plugin mẫu lên bán. Quyền phân phối từng gói phải được ghi nhận trước khi công khai.
- Phân biệt ngừng bán và đình chỉ: ngừng bán chặn khách mới nhưng giữ quyền đã trả; đình chỉ vì vấn đề an toàn chặn sử dụng và mở xử lý hoàn tiền.

### G11.2 — Python có xét duyệt

- Chỉ quản trị nền tảng được duyệt adapter, dependency, image và quyền mạng.
- Build mã bên ngoài trong môi trường riêng, không có secret production.
- Chạy plugin Python trên máy runner tách khỏi API/database, dùng Docker với gVisor `runsc`, giới hạn CPU/RAM/thời gian và tắt mạng mặc định. Kiểm tương thích Python thực tế theo [hướng dẫn gVisor](https://gvisor.dev/docs/user_guide/quick_start/docker/).
- Runner nhận công việc qua kênh nội bộ đã xác thực; chỉ nhận dữ liệu của job, không nhận credential database hoặc quyền toàn bucket.
- Bản phát hành có manifest ký bằng khóa của GoodMCP, bao gồm hash gói, image và quyền đã duyệt; dispatcher xác minh trước khi chạy.
- Không có cơ chế tự chuyển sang chạy container thường khi sandbox lỗi.

### G11.3 — Gói dịch vụ và thuê plugin

- Hai loại thuê độc lập: gói workspace và thuê plugin; mỗi thuê bao gắn một workspace.
- Gói miễn phí vẫn được thuê plugin nếu còn đủ hạn mức tài nguyên.
- Chu kỳ là tháng lịch; ngày cuối kỳ được điều chỉnh về ngày cuối tháng khi cần. Gia hạn sớm nối tiếp kỳ hiện tại; gia hạn sau hết hạn bắt đầu khi thanh toán được xác nhận.
- Giá và điều kiện được chụp lại vào đơn hàng. Thay giá chỉ áp dụng cho đơn mới; không sửa giao dịch đã thanh toán.
- Hết hạn plugin: chặn đọc nội dung plugin và chạy công cụ, giữ dự án/kết quả người dùng đã tạo. Cấp quyền lại sau gia hạn.
- Quyền thuê bao phải được kiểm trong REST, MCP, job và đường đọc file, kể cả khi token cũ còn hạn.
- Người thuê không được tải ZIP nguồn trả phí theo quyền admin workspace; xuất mã nguồn chỉ dành cho tác giả hoặc giấy phép cho phép rõ ràng.

### G11.4 — SePay, hoàn tiền và đối soát tác giả

- Tích hợp VietQR, webhook có chữ ký và API v2 để đối soát. Có môi trường test tách biệt theo [SePay API v2](https://developer.sepay.vn/vi/sepay-api/v2/bat-dau-nhanh).
- Chỉ ghi nhận thanh toán từ thông báo đã xác minh hoặc kết quả đối soát server; trang chuyển về sau thanh toán không tự cấp quyền.
- Kiểm chữ ký trên nội dung gốc, thời gian, tài khoản nhận, chiều tiền vào, mã đơn, số tiền và loại tiền theo [hướng dẫn webhook SePay](https://developer.sepay.vn/vi/sepay-webhooks/xac-thuc).
- Một giao dịch ngân hàng chỉ được ghi nhận một lần. Webhook trùng hoặc đến sai thứ tự không kéo dài thuê bao, cộng doanh thu hoặc hoàn tiền hai lần.
- Tiền thiếu/thừa, không khớp đơn hoặc đến sau khi đơn hết hạn được đưa vào danh sách đối soát; không tự cấp quyền.
- Có sổ giao dịch bất biến cho tiền nhận, phần GoodMCP, phần tác giả, hoàn tiền và khoản đã trả. Điều chỉnh bằng bút toán mới, không sửa lịch sử.
- Hoàn tiền bản đầu do quản trị xử lý chuyển khoản và ghi chứng từ; quyền sử dụng và doanh thu cập nhật theo phần được hoàn.
- Tác giả xem doanh thu, khoản giữ lại, đủ điều kiện nhận và đã trả. Khầy lập kỳ đối soát, duyệt, chuyển khoản và xác nhận chứng từ; hệ thống chống ghi chi trùng.
- Nếu hoàn tiền sau khi đã trả tác giả, ghi khoản cần thu hồi/bù trừ; không âm thầm sửa kỳ đã chốt.
- Giá, hoa hồng, thời gian giữ tiền, ngưỡng chi và chính sách hoàn tiền là cấu hình có phiên bản. Chưa cấu hình và xác nhận thì checkout thật bị khóa.

### G11.5 — Frontend thương mại

- Khách: danh mục/tìm kiếm, chi tiết plugin, tác giả, giá, phiên bản, thuê/cài và lịch sử thanh toán.
- Workspace: gói hiện tại, thuê bao plugin, ngày hết hạn, QR gia hạn và trạng thái thanh toán.
- Tác giả: hồ sơ, gửi phiên bản, phản hồi xét duyệt, giá, doanh thu và lịch sử nhận tiền.
- Quản trị nền tảng: duyệt tác giả/plugin/runtime, đình chỉ, chính sách giá, đối soát, hoàn tiền và kỳ chi.
- Bổ sung API theo nhóm `marketplace`, `publisher`, `billing`, `platform` và webhook SePay. Không cho MCP thực hiện mua hàng hoặc chuyển tiền trong bản này.

**Nghiệm thu G11:** hai tác giả, hai workspace mua hàng; có plugin miễn phí, plugin thuê tháng và Python đã duyệt. Hoàn tất thuê → thanh toán → cài → dùng qua web/MCP → hết hạn → gia hạn → hoàn tiền → đối soát tác giả.

## 5. Kiểm thử, phát hành và bàn giao

- **Quyền:** truy cập chéo workspace qua ID, file, tìm kiếm, job, cache và token cũ; hạ quyền giữa tác vụ; tranh chấp chuyển owner; lời mời trùng/hết hạn.
- **Danh tính:** Google hủy đăng nhập, callback lặp, sai state/nonce, email trùng và liên kết owner cũ; không tạo nhầm tài khoản hoặc workspace.
- **Tiền:** webhook giả/trùng/chậm, sai số tiền, mất thông báo, đối soát lại, gia hạn đồng thời, hoàn tiền sau đối soát và ghi chi hai lần.
- **Lưu trữ/runtime:** migration gián đoạn, hash sai, R2 lỗi, runner chết, hết lease, vượt quota và plugin cố đọc dữ liệu ngoài job.
- **Frontend:** đầy đủ loading/empty/error/success; responsive từ 320px, bàn phím, quyền bị đổi khi đang mở trang, lỗi mạng và phiên hết hạn. Kiểm trình duyệt giao cho subagent **GPT-6.1 Terra medium** theo AGENTS.md.
- **Hồi quy:** giữ kết quả Python, workflow, phiên bản ghim và OAuth MCP G1–G8; thử lại luồng ChatGPT trên endpoint thật. Tách bằng chứng giả lập, local và production.
- **Phát hành:** migration bổ sung, không sửa migration đã phát hành; thử trên bản sao dữ liệu. Tách công tắc Google/signup, marketplace, thanh toán thật và Python bên ngoài. Rollback ứng dụng phải giữ dữ liệu mới.
- **Bàn giao:** cập nhật [PLAN.md](H:/AI/goodmcp/Docs/PLAN.md), đặc tả UI/API/quyền, migration, cấu hình mẫu, hướng dẫn vận hành và báo cáo G9/G10/G11. Mỗi báo cáo ghi lệnh kiểm tra, bằng chứng, số đo, giới hạn và trạng thái thật.
- Mở rộng `verify.ps1` và `verify.sh` cho G9–G11; chỉ ghi `passed` khi đạt các tiêu chí tương ứng. Thiếu tài khoản Google/SePay, SMTP hoặc ngân sách hạ tầng được ghi thành điều kiện triển khai, không thay bằng kết quả giả lập.
