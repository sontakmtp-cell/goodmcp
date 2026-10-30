---
name: opc-dashboard-review
description: "Diagnose operating results and recommend one next priority. Use when business stalls, conversion falls or a periodic review is needed."
---

# Chẩn đoán vận hành

Đọc [quy tắc chung](../opc-orchestrator/references/runtime-contract.md), [chính sách mô hình](../opc-orchestrator/references/model-routing.md)
và [vai trò](references/role-profile.md) trước khi thực hiện. Chỉ đọc lại khi chưa có
trong ngữ cảnh hoặc phiên bản thay đổi. Vai trò: `opc-dashboard-reviewer`.
Đọc [hợp đồng lưu trạng thái](../opc-orchestrator/references/file-contract.md) khi cần lưu hoặc tiếp tục phiên.
Nếu bộ đọc chỉ truy cập được một skill, nạp `opc-orchestrator` bằng bộ đọc skill
để đọc tài liệu chung; chỉ đọc quy tắc, không khởi động lại quy trình kinh doanh.


## Điều kiện và đầu vào

Cần trải nghiệm vận hành thực tế, dù dữ liệu ít. Đọc đầu ra đã được cho phép,
`opc-doc/reviews/dashboard.json`, lịch sử 08 và số liệu người dùng cung cấp.
Nếu chưa chạy thử, hỗ trợ 05/06 bắt đầu thay vì làm báo cáo vận hành giả.

## Quy trình

1. Chốt kỳ báo cáo, múi giờ, nguồn, đơn vị và phạm vi. Đọc
   [định nghĩa chỉ số](references/review-metrics.md); kiểm tra mẫu số, khách trùng,
   cửa sổ thời gian và dữ liệu thiếu trước khi tính tỷ lệ.
2. Tách vấn đề nhu cầu, tiếp cận, tiếp nhận, chốt đơn, giao hàng, dòng tiền,
   công suất và khả năng dùng lại tài sản. Đối chiếu kế hoạch với số thực tế.
3. Nêu tối đa ba giả thuyết điểm nghẽn có bằng chứng, phản chứng và phần chưa rõ.
   Nếu chỉ có hai giả thuyết thì trình bày hai. Không biến tương quan thành nguyên nhân.
4. Đọc [điều kiện dừng](references/stop-loss-rules.md). Đề xuất **một** ưu tiên kỳ
   tới có căn cứ, phép đo tiếp theo và ngưỡng xem lại; người dùng quyết định áp dụng.
5. Nếu thiếu dữ liệu quan trọng, ưu tiên thu đúng dữ liệu và kết luận `inconclusive`,
   không tự tạo số hoặc đòi làm lại toàn bộ các bước chiến lược.

## Đầu ra và hoàn thành

Theo [mẫu tuần](references/weekly-review-template.md), chuẩn bị:

- `opc-doc/outputs/08-dashboard-review/review-[YYYYMMDD-HHmmss].md`:
  số liệu, điểm nghẽn, độ chắc chắn, một ưu tiên, chủ trách nhiệm, hạn và điều kiện xem lại.
- Đề xuất mục dữ liệu mới cho `opc-doc/reviews/dashboard.json`; trưởng nhóm đọc,
  gộp và ghi JSON hợp lệ, không nối thô hai tài liệu JSON và không mất lịch sử.

Hoàn thành khi trạng thái kinh doanh, điểm nghẽn/thiếu đo lường và ưu tiên kỳ tới
được người dùng xác nhận. Gửi đề xuất `08-dashboard-review` → `execution` hoặc
ID bước thật sự cần quay lại; chuyên gia được giao việc không tự ghi trạng thái chung. Ngày giờ theo múi giờ
người dùng; thêm bộ đếm nếu trùng, giữ lịch sử cũ.
