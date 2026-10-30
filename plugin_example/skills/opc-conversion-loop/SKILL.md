---
name: opc-conversion-loop
description: "Build a reach-to-purchase path and concrete first action. Use when choosing channels, capturing leads or drafting initial outreach content."
---

# Thiết kế chuyển đổi

Đọc [quy tắc chung](../opc-orchestrator/references/runtime-contract.md), [chính sách mô hình](../opc-orchestrator/references/model-routing.md)
và [vai trò](references/role-profile.md) trước khi thực hiện. Chỉ đọc lại khi chưa có
trong ngữ cảnh hoặc phiên bản thay đổi. Vai trò: `opc-conversion-designer`.
Đọc [hợp đồng lưu trạng thái](../opc-orchestrator/references/file-contract.md) khi cần lưu hoặc tiếp tục phiên.
Nếu bộ đọc chỉ truy cập được một skill, nạp `opc-orchestrator` bằng bộ đọc skill
để đọc tài liệu chung; chỉ đọc quy tắc, không khởi động lại quy trình kinh doanh.


## Đầu vào và quy trình

Đọc `opc-doc/outputs/05-mvp-design/` và thông tin khách/giá đã xác nhận.

1. Xác định khách xuất hiện ở đâu và kênh nào người sáng lập có thể vận hành.
   Ưu tiên một kênh, tối đa hai nếu có lý do; kiểm chứng quy tắc/giá nền tảng khi cần.
2. Thiết kế từng bước: tiếp cận → tiếp nhận khách tiềm năng → trao đổi/đề nghị →
   giao dịch → giao hàng/theo dõi. Mỗi bước có hành động, người phụ trách và số đo.
3. So sánh các đường đi thực tế, ví dụ nội dung → tin nhắn → tư vấn → mua,
   hoặc nội dung → biểu mẫu → chẩn đoán → mua. Không ép đủ ba đường nếu chỉ một
   đường phù hợp. Nêu điểm mất khách và cách ghi dữ liệu.
4. Chuẩn bị hành động đầu tiên có thể chạy: bài đăng, tin nhắn nháp, trường biểu
   mẫu, câu hỏi chẩn đoán, lời kêu gọi hành động hoặc checklist nhận đơn/giao hàng
   tối thiểu theo yêu cầu. **Làm ngay ở 06, không chuyển sang 07 chỉ để tạo nội dung.**
5. Phân biệt soạn nội dung với gửi/xuất bản. Không tự gửi, đăng hoặc thu tiền khi
   chưa có quyền; không tuyên bố đã triển khai từ một bản nháp.

Đọc [kênh](references/channel-playbook.md), [mẫu đường đi](references/conversion-patterns.md)
khi chọn phương án. Với số đo, dùng định nghĩa trong
[chỉ số vận hành](../opc-dashboard-review/references/review-metrics.md).

## Đầu ra và hoàn thành

Chuẩn bị trong `opc-doc/outputs/06-conversion-loop/`:

- `channel-strategy.md`: kênh, lý do, chi phí/giờ và giả định chưa kiểm chứng.
- `content-plan.md`: mục đích nội dung, lời kêu gọi và bản nháp đầu tiên nếu cần.
- `conversion-path.md`: từng bước, chủ trách nhiệm, cách đo tử số/mẫu số và điểm mất khách.
- `first-action.md`: việc cụ thể làm đầu tiên, tài liệu cần, người làm và hạn dự kiến.

Hoàn thành khi đường đi có tiếp nhận và giao dịch rõ, có bước chạy đầu tiên và
được người dùng xác nhận. Gửi quyết định và đề xuất `06-conversion-loop` →
`execution` cho trưởng nhóm; chuyên gia được giao việc không tự cập nhật trạng thái chung.
Tiếp tục hỗ trợ thực thi khi được yêu cầu. Chỉ gợi ý 07 khi đã có kết quả lặp lại,
08 khi đã có trải nghiệm/dữ liệu vận hành, không tự khởi động hai bước đó.
