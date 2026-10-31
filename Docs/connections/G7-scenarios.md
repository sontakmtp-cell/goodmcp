# G7 — Kịch bản nghiệm thu host thật

Ngày 31/10/2026, Asia/Saigon. Đây là quy trình tái hiện, không phải bằng chứng đã
kết nối. Trạng thái lần thực hiện nằm ở [G7.md](../reports/G7.md).

**Cập nhật G8:** endpoint production đã xác minh là **https://goodmcp.si/mcp**,
issuer **https://goodmcp.si/auth**; đăng nhập Cloudflare SSO. Kịch bản/bước nghiệm
thu bên dưới giữ nguyên. Endpoint local và lịch sử thử được phân biệt như sau.

Endpoint local đã xác minh: MCP `http://127.0.0.1:18080/mcp`, OAuth issuer
`http://127.0.0.1:18080/auth`, login `/auth/login`. `goodmcp.si` là URL Khầy cung cấp
nhầm trong lần thử trước. Địa chỉ loopback này dùng local; trước phép thử cloud
phải có đường kết nối tới Hub được xác minh. `/auth` không phải URL MCP.

## Điều kiện trước khi chạy

Endpoint MCP phải trả giao thức MCP và discovery phải trả JSON đúng issuer/resource,
không trả trang HTML dù status 200. Dùng OAuth hiện có, không tắt quyền, đổi scope
hoặc hạ protocol để vượt lỗi. Server local hiện pin `2026-07-28`; revision mà từng
host thực sự gửi chỉ được ghi sau khi quan sát request. Không suy từ tên hãng.

Chỉ nhập mật khẩu owner vào trang issuer của Hub đã xác minh. Tạo kết nối thử có
nhãn G7, không sửa kết nối có sẵn. Không gọi API model tính phí trong nhiệm vụ này.
Một host cloud hoàn tất các bước dưới mới đạt tiêu chí tối thiểu của PLAN.

## Các bước và bằng chứng bắt buộc

| Bước | Thao tác | Bằng chứng cần giữ, đã bỏ secret |
|---|---|---|
| 1 | Trong host, thêm URL MCP, discovery OAuth | URL, product/surface, protocol quan sát được, lỗi nguyên văn nếu có |
| 2 | Đăng nhập và consent vào đúng workspace | Client/issuer/resource/scope, thời điểm, không lưu code/token/cookie/password |
| 3 | List/open ba plugin | Tên/version/installation handle thực từ tool, source hash; không chỉ lời model kể |
| 4 | Đọc skill OPC và hồ sơ chuyên gia khi cần | Tool/arguments/result/source handle; đọc tài liệu không chứng minh spawn agent |
| 5 | Search Finance bằng từ khóa, đọc trang tìm thấy | Literal terms, resource_id, source_sha256, offset/next_offset; giữ warning PDF |
| 6 | CIT với revenue=1000, cost=600, rate=20 | Job ID; input thật; kết quả Python gốc 80 VND; image/release digest |
| 7 | Poll job tới terminal | queued/running/succeeded hoặc lỗi thật, result artifact; không đổi lỗi thành success |
| 8 | Tạo project thử, lưu output dạng draft | Project pin/revision, file handle và SHA-256; không tự complete stage OPC |
| 9 | Mở chat mới, tìm và đọc lại project/file | Cùng project/version/revision/hash/nội dung/resume stage; không dán lại kết quả cũ làm bằng chứng |
| 10 | Thu hồi đúng grant thử rồi thử lại | Token/grant hoạt động ngay trước revoke; request mới bằng grant đó bị 401 sau revoke; phân biệt host tự reauth |

Ghi `requested_model`, `reported_model`, nguồn/thời điểm. Nhãn selector là một
trường riêng; không chứng minh model thực hiện tool. Unknown giữ unknown. Ghi
khả năng file/tool/subagent/model selection riêng; brief hoặc nhiều vai trò trong
văn bản không phải bằng chứng nhiều agent chạy thật.

## Điểm vào từng sản phẩm đã quan sát

- ChatGPT web: Plugin → thêm server MCP tùy chỉnh → URL, OAuth. Lần này advanced
  OAuth discovery tại `https://goodmcp.si/mcp` thất bại.
- Claude web: Tùy chỉnh → Trình kết nối → Thêm. Lần này nút thêm connector tùy
  chỉnh bị khóa; nguyên nhân chưa biết, không suy thành toàn bộ gói Free không hỗ trợ.
- Gemini web: Tùy chỉnh → Trình kết nối → Tạo ứng dụng tùy chỉnh. Next tới màn
  consent không chứng minh discovery hoặc login Hub thành công.
- Grok web: Plugin → Trình kết nối mới → Tùy chỉnh. Lần này chỉ quan sát form,
  không submit URL sai. Connector Blender cũ không phải Hub mới.

Desktop/CLI/API là các đường kiểm tra riêng. Cài được CLI, đọc cấu hình hay
validate JSON không phải inference hoặc nghiệm thu web/cloud.

## Các lệnh bổ trợ local đã chạy

Chạy tại repo root, dùng môi trường `.venv` hiện có:

```powershell
.venv/Scripts/python.exe scripts/probe-g7.py
.venv/Scripts/python.exe tests/wire_g7.py --local
.venv/Scripts/python.exe scripts/verify.py --stage G5 --evidence-dir Docs/reports/evidence/G7/regression
```

Hai lệnh đầu ghi đè evidence cùng tên khi chạy lại; lưu bản cũ nếu cần đối chiếu.
Local wire giữ một project/output có nhãn, job và audit trong workspace, thu hồi
hai grant thử trong finally. Không thay installation/plugin/pin cũ. Môi trường
regression dùng Compose/database/volume riêng và dọn sau pass.

`scripts/verify.ps1 -Stage G7` chưa được triển khai; không dùng lệnh đó để tuyên bố
G7 đạt. Các lệnh bổ trợ trên không tự thực hiện kịch bản cloud qua host.

## Tài liệu hãng đã đọc lại

Xem [sources.json](../reports/evidence/G7/sources.json). Tài liệu xác lập đường thử;
quyền tài khoản và kết quả thực tế vẫn cần bằng chứng UI/MCP tương ứng.
