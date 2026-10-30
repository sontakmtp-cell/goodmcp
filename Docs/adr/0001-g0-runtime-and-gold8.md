# ADR-0001 — CPython/Linux, TF-IDF giữ nóng, GOLD 8 có điều kiện

- Ngày: 30/10/2026, Asia/Saigon.
- Trạng thái: accepted cho triển khai local G1; **chưa duyệt mua/deploy**.
- Phạm vi quyết định: runtime, resource budget, cách build và điều kiện mua VPS.

## Bối cảnh và quyết định

Finance–Tax cần NumPy/SciPy/scikit-learn/BeautifulSoup. Chọn CPython 3.12 trong
container Linux, pin dependency bằng `poc/g0/uv.lock`; không port Python sang JS,
không thay TF-IDF bằng FTS. API MCP dùng package chính thức `mcp==2.3.0`, đã thử
wire `2026-07-28`; Authlib 1.9.1 cần adapter ASGI + issuer riêng. Source plugin
không thay đổi. G1 tiếp tục PostgreSQL 18 theo PLAN, chưa được benchmark ở G0.

Giữ cấu hình mục tiêu **GOLD 8: 4 vCPU / 8 GB / 80 GB**, Ubuntu 24.04 LTS, trả
theo tháng. Search một process giữ nóng theo phiên bản; query nặng tuần tự.
Build index mặc định offline trong cùng locked image, rồi chuyển artifact có
provenance/checksum từ pipeline tin cậy. Không cộng builder 5 GiB với search
3 GiB và toàn stack lên máy 8 GB. Dữ liệu đầy đủ ở [G0.md](../reports/G0.md).

Số đo local cho thấy Python khả thi trong 8 GB với giới hạn tải của contract;
không suy ra hiệu năng CPU chia sẻ hay tổng RAM production. G4 phải đo cả Compose;
ngưỡng scale/check lại khi peak vượt 75% hoặc queue chờ >30s kéo dài theo PLAN.
Không hạ xuống GOLD 4 chỉ dựa peak riêng lẻ 2 GB.

## Xác minh nhà bán (nguồn công khai, 30/10/2026)

| Hạng mục | Kết quả và giới hạn chứng cứ |
|---|---|
| Gói / giá | GOLD 8 niêm yết 320.000đ/tháng, 4 CPU, 8 GB RAM, 80 GB SSD; không dùng mã giảm giá để tính ngân sách. [Bảng giá](https://vpssieutoc.vn/store/vps-gold). |
| Root / Docker / OS / nâng cấp | Trang GOLD công bố full root, có Ubuntu/Docker và nâng CPU/RAM/đĩa. Chưa xác nhận image Ubuntu **24.04** cụ thể, downtime/chi phí upgrade hoặc shrinking đĩa. [Trang GOLD](https://vpssieutoc.vn/vps-gold). |
| VAT | Điều khoản ghi giá chưa VAT; checkout rỗng hiển thị VAT 10%. Ước tính 320.000 × 1,10 = **352.000đ/tháng**, tăng 32.000đ so với giá gốc; cần checkout thực xác nhận. [Điều khoản](https://vpssieutoc.vn/legal/dieu-khoan-dich-vu), [trang checkout công khai](https://vpssieutoc.vn/cart.php?a=checkout). |
| Backup | Điều khoản VPS nói bản sao hệ thống không cung cấp theo yêu cầu thông thường; không dùng thay backup Hub. Giá dịch vụ backup tự phục hồi nếu mua thêm chưa rõ, không thêm vào ngân sách mặc định. [Điều khoản VPS](https://vpssieutoc.vn/legal/dieu-khoan-su-dung-vps). |
| Thử/hoàn tiền | Không chứng minh có trial miễn phí. Policy ghi yêu cầu trong 1 ngày, chỉ một lần với VPS đầu tiên, có loại trừ nâng cấp/khuyến mãi/số dư/crypto. Điều khoản dùng mốc kích hoạt còn policy dùng mốc thanh toán; xác nhận mốc sớm hơn trước trả tiền. [Chính sách hoàn tiền](https://vpssieutoc.vn/legal/chinh-sach-hoan-tien). |
| AI cloud / mạng | Chưa có VPS/IP nên chưa thử kết nối cloud tới máy nhà bán. HTTP loopback G0 không thay smoke TLS/Cloudflare/host ở G2/G7/G8. |

352.000đ nằm trong 15 USD chỉ khi tỷ giá thanh toán sau phí ít nhất khoảng
23.466,67 VND/USD; đây là phép chia ngân sách, **không phải tỷ giá đã xác minh**.
Không có checkout gói đã mua, không tạo order/ticket, không đổi ngân sách.
Các giá upgrade/backup, Ubuntu 24.04, outbound/inbound tới AI cloud và hóa đơn
cuối là gate **trước mua/G8**, không chặn nền local G1.

## Hệ quả

Budget service ban đầu và contract API/tenant/job/adapter/storage được chốt ở
[G1-contract.md](../contracts/G1-contract.md). Bản build mới có full chunk mapping,
giữ 39 PDF nhưng không OCR/index chúng; không dùng supplied pickle. Local PoC
không xử lý code thù địch, OAuth nhiều người hoặc backup/restore production.
