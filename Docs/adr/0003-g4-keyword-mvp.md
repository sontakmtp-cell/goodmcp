# ADR-0003 — G4 MVP: keyword documents, original Python calculators

Status: accepted by Khầy's scope update, 30/10/2026.

Khầy yêu cầu bỏ xây dựng/benchmark TF-IDF khỏi MVP; MCP cung cấp liệt kê, tìm
từ khóa và đọc tài liệu, AI đang chat tự điều phối; giữ công cụ Python tính thuế;
tìm kiếm nâng cao chỉ làm sau nếu thực tế cần. PLAN G4 đã cập nhật theo yêu cầu này.

MVP không chạy build_index.py/search_corpus.py, không nạp supplied pickle/NPZ,
không NumPy/SciPy/scikit-learn/model API trong calculator image. Các khảo sát G0
và contract G0 lịch sử giữ nguyên; các yêu cầu warm index/chunk handles/recall@5
của chúng được thay thế bởi quyết định này cho G4 MVP. Không dùng kết quả thử
TF-IDF trước thay đổi scope để công bố nghiệm thu MVP.

Nguồn vẫn immutable trong G3. Projection `document_texts` lưu plain text và bản
casefold, không dùng FTS/trigram/vector index. Keyword lookup dùng `strpos` với
tham số literal all/any, thứ tự UUID ổn định, có cursor; không có relevance score.
Projection được tạo khi import hoặc backfill operator, giữ source SHA-256.
HTML chỉ tách chữ qua HTMLParser, bỏ script/style/navigation; không render.
PDF, binary/mislabeled PDF hoặc encoding không hỗ trợ được ghi unavailable;
không tạo văn bản giả, không OCR. G3 quarantine và `_backup_zh` vẫn bị loại active.

Calculator adapters chỉ gọi bốn module gốc đã kiểm hash; cùng rounding và tham số,
kèm cảnh báo hạn chế của nguồn. Tác vụ chạy async trong container riêng có giới
hạn 1 CPU/256 MiB/30 giây, tối đa hai job đồng thời. Không chạy code từ ZIP.

Dispatcher là control plane đặc quyền có Docker socket và runtime DB secret,
không nhận HTTP. Image được operator duyệt theo source/version/release digest.
API/import worker và calculator container không có socket; calculator không có
network/DB/admin secrets/host mount, rootfs read-only và tmpfs job riêng. Quyền
Docker tương đương quyền quản trị host: cấu hình production/group socket cần G8
review; không coi đây là sandbox cho mã thù địch công khai.

Kiểm chứng G4 theo scope mới: ít nhất 30 parity cases (bộ fixture có 47), job
lease/fencing/idempotency/cancel/timeout/crash, tenant boundaries, keyword/full text
pagination, metadata coverage và đo Compose local. Không đặt mục tiêu recall@5.

Tham chiếu: [Docker Engine API](https://docs.docker.com/reference/api/engine/),
[MCP typed tools](https://py.sdk.modelcontextprotocol.io/servers/tools/).
