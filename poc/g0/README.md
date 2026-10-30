# G0 local PoC / benchmark

Chỉ chạy thử local, không phải Hub/G1 hay OAuth production. Không expose port,
không gọi model, không đổi source plugin. Báo cáo: [G0](../../Docs/reports/G0.md);
handoff: [contract](../../Docs/contracts/G1-contract.md).

## Chạy lại trên Windows hoặc Linux

Cần Python 3.12+ trên host (chỉ stdlib cho launcher), Docker Linux đang chạy,
khoảng 3 GB đĩa trống cho một lượt và đủ RAM cho container 5 GiB + các dịch vụ host.
Image build tải dependency khóa từ PyPI; các container thực thi **network none**.
Không cần cài thư viện Python vào host. Từ repo root:

```powershell
python poc/g0/run.py
python poc/source_audit_g0.py
```

Linux có thể dùng `python3` thay `python`. Lượt Windows đã chạy thật; Linux dùng
cùng launcher/image nhưng chưa chạy launcher trên Linux host riêng. G1 mới tạo
`scripts/verify.ps1 -Stage Gx` / `scripts/verify.sh Gx`; đây là launcher riêng G0.

Launcher làm lần lượt: hash inventory trước → build locked image → calculator,
refs, tariff/location smoke → rebuild TF-IDF gốc → 2 cold processes / mỗi process
6 queries → HTTP/OAuth smoke → contract schema checks → search trần 3 GiB và
calculator trần 256 MiB → inventory sau. Container non-root, read-only root và
plugin mount; cap_drop ALL, no-new-privileges, PID limit; chỉ `/work` và tmpfs ghi.
Chứng cứ nhỏ copy vào `Docs/reports/evidence/G0`; index/full chunks giữ ở
`.g0-local/<run-id>` (Git ignored, không backup mặc định). Mỗi lượt thư mục mới,
không tái sử dụng supplied pickle. Launcher xóa đúng container của lượt đó khi
đã dừng, không dọn image/container/project khác.

## Tệp

- `pyproject.toml`, `uv.lock`, `Dockerfile`: Python 3.12, pin cả base/uv image digest
  và toàn bộ phiên bản/hash dependency; không có package `fastmcp` bên thứ ba.
- `inventory.py`: AST/import/functions và SHA từng file, không import mã plugin.
- `reviewed-source.json`, `runtime.py`: allowlist 6 module đã đọc code, kiểm SHA
  trước import; không nhận đường dẫn tùy ý. Chỉ main corpus builder/search được
  chạy; semantic và `_backup_zh` không chạy.
- `benchmark.py`: gọi hàm gốc, chỉ đổi output path của builder/search ra `/work`.
  Chặn `chunk_text` để **ghi lại chính kết quả gốc**, giữ nguyên thuật toán và
  tham số TF-IDF. Full-text sidecar khớp tất cả rows/preview/char_count.
  Khóa tra sidecar là `(source_file, id)` vì ID gốc TXT/HTML có trùng nhau.
- `auth_poc.py`, `wire_smoke.py`: FastAPI/ASGI + Authlib core authorization code,
  S256 + official SDK v2. Login HTTP có CSRF, password ngẫu nhiên chỉ sống trong
  process; một owner/client pre-approved. Không lưu token/password/code/cookie
  vào evidence. Uvicorn bind loopback bên trong container không có port publish.
- `check_contract.py`: JSON Schema 2020-12 + boundary examples; không thay test
  DB/RLS/filesystem/job thực tế ở các giai đoạn sau.
- `../source_audit_g0.py`: chỉ đọc JSON và NPY headers trong ZIP/NPZ; không load
  pickle gốc; phát hiện corpus MANIFEST cũ lệch file/kích thước.

## Cách đọc số đo

Cold là Python process mới, **không xóa OS page cache**, không phải boot máy mới.
Peak RSS = Linux `ru_maxrss` của process; container memory peak/events ghi riêng.
CPU = user + system, không phải tỷ lệ CPU trung bình VPS. `process_wall_s` gồm
startup; `metrics.wall_s` tính từ khi vào phase, không gồm interpreter/import
bootstrap. Warm search giữ một matrix và đo 5 lần sau query đầu. Nạp index còn
gồm đọc/hash integrity, thời gian bind-mount Windows/WSL có thể khác SSD VPS.
Số mẫu nhỏ, không p95/p99 hay benchmark nhiều người. Code gốc in thời gian build
cuối chỉ tính phần save do reset t0; dùng đồng hồ wrapper cho tổng build.

SHA256/checksum chỉ kiểm tính toàn vẹn trong local pipeline đã kiểm soát; không
phải chứng thực an toàn của pickle người lạ. Production phải tách quyền builder/
registry/runner và bổ sung source/image/lock provenance theo contract.
