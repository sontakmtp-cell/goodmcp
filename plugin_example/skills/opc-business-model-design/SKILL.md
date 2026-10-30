---
name: opc-business-model-design
description: "Build Lean Canvas and a light BMC. Use when defining revenue, pricing, costs, capacity and risky business assumptions."
---

# Thiết kế mô hình kinh doanh

Đọc [quy tắc chung](../opc-orchestrator/references/runtime-contract.md), [chính sách mô hình](../opc-orchestrator/references/model-routing.md)
và [vai trò](references/role-profile.md) trước khi thực hiện. Chỉ đọc lại khi chưa có
trong ngữ cảnh hoặc phiên bản thay đổi. Vai trò: `opc-model-architect`.
Đọc [hợp đồng lưu trạng thái](../opc-orchestrator/references/file-contract.md) khi cần lưu hoặc tiếp tục phiên.
Nếu bộ đọc chỉ truy cập được một skill, nạp `opc-orchestrator` bằng bộ đọc skill
để đọc tài liệu chung; chỉ đọc quy tắc, không khởi động lại quy trình kinh doanh.


## Đầu vào và quy trình

Đọc kết luận 02 và 03 từ `opc-doc/outputs/` hoặc hội thoại đã xác nhận.

1. Đi từng phần Lean Canvas, tái dùng thông tin cũ: Problem, Customer Segments,
   Unique Value Proposition, Solution, Channels, Revenue Streams, Cost Structure,
   Key Metrics, Unfair Advantage. Không đưa bảng câu hỏi lớn khi chỉ thiếu một mục.
2. So sánh cách thu tiền, kênh hoặc cấu trúc chi phí khi có quyết định thực sự.
   Đề xuất có căn cứ; người dùng quyết định. Đọc [Lean Canvas](references/lean-canvas-lite.md),
   [BMC rút gọn](references/bmc-lite.md) và [giá](references/pricing-checklist.md) theo nhu cầu.
3. Kiểm tra BMC: ai tạo giá trị, nguồn lực/hoạt động/đối tác then chốt, cách phân
   phối và giữ khách, chi phí và dòng thu có khớp không.
4. Tách khoản thu, chi phí biến đổi và cố định, thời gian giao hàng, sức chứa.
   Ghi giả định về giá, tiền tệ và đơn vị; không mô tả giả định là số thị trường đã đo.
5. Chọn tối đa ba giả thuyết rủi ro nhất: hậu quả nếu sai, bằng chứng hiện có,
   phần thiếu, cách kiểm chứng và độ ưu tiên. Đầu ra này chuyển sang MVP.

Không tự thiết kế sản phẩm đầy đủ hoặc triển khai chiến dịch ở bước mô hình.
Nếu người dùng muốn chạy thử, dùng giả thuyết đã có để chuyển 05 thay vì trì hoãn.

## Đầu ra và hoàn thành

Chuẩn bị trong `opc-doc/outputs/04-business-model/`:

- `lean-canvas.md`: chín mục và trạng thái bằng chứng từng mục.
- `business-model-canvas-lite.md`: kiểm tra sự khớp giữa tạo, truyền và thu giá trị.
- `pricing-notes.md`: mô hình thu, giả định giá/chi phí/thời gian, giới hạn sức chứa.
- `risky-assumptions.md`: giả thuyết ưu tiên, căn cứ, phép thử dự kiến.

Hoàn thành khi các phần canvas đã rõ hoặc được chấp nhận là chưa biết,
giả thuyết rủi ro được ưu tiên và mô hình được người dùng xác nhận.
Gửi quyết định, giả thuyết `unverified` và đề xuất `04-business-model` →
`05-mvp-design` cho trưởng nhóm. Khi là chuyên gia được giao việc, không ghi trực tiếp trạng thái chung.
