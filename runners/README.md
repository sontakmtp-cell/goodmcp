# G4 local Python runtime

`finance/` có entrypoint cho một calculator job/container, loader kiểm SHA và
Dockerfile CPython 3.12 với root lockfile. Lớp bọc ở
`packages/plugin-adapters/finance/adapter.py` gọi các hàm Python gốc; không chép công thức.

Chuẩn bị: `python scripts/prepare-g4.py`. Lệnh in đường dẫn `release.json`.
Sau `python scripts/local.py up`, bật release bằng
`python scripts/local.py runtime --release PATH_TO_RELEASE_JSON`.

Chỉ dispatcher nội bộ có Docker socket. Container calculator: non-root, rootfs
read-only, no network, no secrets/DB/socket/mount từ client; 1 CPU/256 MiB/30 giây.
Job directory là tmpfs riêng và bị xóa khi job kết thúc. Tối đa hai job đồng thời.

Theo thay đổi phạm vi của Khầy, MVP không có TF-IDF builder, index nóng, matrix,
pickle hoặc model API. Công cụ tài liệu nằm ở `goodmcp.documents`, readonly qua MCP;
AI bên client tự chọn từ khóa và đọc nguồn.
