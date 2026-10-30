---
name: opc-asset-ops
description: "Systematize repeated operating outputs into reusable assets. Use when organizing templates, content, processes, data or knowledge."
---

# Tổ chức tài sản tái sử dụng

Đọc [quy tắc chung](../opc-orchestrator/references/runtime-contract.md), [chính sách mô hình](../opc-orchestrator/references/model-routing.md)
và [vai trò](references/role-profile.md) trước khi thực hiện. Chỉ đọc lại khi chưa có
trong ngữ cảnh hoặc phiên bản thay đổi. Vai trò: `opc-asset-strategist`.
Đọc [hợp đồng lưu trạng thái](../opc-orchestrator/references/file-contract.md) khi cần lưu hoặc tiếp tục phiên.
Nếu bộ đọc chỉ truy cập được một skill, nạp `opc-orchestrator` bằng bộ đọc skill
để đọc tài liệu chung; chỉ đọc quy tắc, không khởi động lại quy trình kinh doanh.


## Điều kiện và đầu vào

Đọc kết quả 05/06, lịch sử `opc-doc/outputs/07-asset-ops/` và mô tả công việc
đã làm. Tìm thứ đã lặp lại hoặc có khả năng tái sử dụng dựa trên trải nghiệm thật.
Nếu chỉ cần nội dung cho lần chạy đầu, chuyển 05/06 hoặc hỗ trợ bản nháp theo
yêu cầu; **không bắt tạo tài sản tái sử dụng trước khi có thể bắt đầu vận hành.**

## Quy trình

1. Kiểm kê kết quả đang có: nội dung, phương pháp, mẫu, công cụ, kênh, dữ liệu,
   bằng chứng uy tín; ghi tần suất dùng, người dùng lại và tình trạng chất lượng.
2. Phân loại theo [loại tài sản](references/asset-taxonomy.md). Ước lượng giờ tạo,
   giờ bảo trì và giờ tiết kiệm; không mặc định mọi thứ đều đáng hệ thống hóa.
3. So sánh ưu tiên bằng tần suất × công sức tiết kiệm, trừ chi phí tạo/bảo trì,
   cùng yếu tố chất lượng và rủi ro. Gắn nhãn các số là ước tính khi chưa đo.
4. Đề xuất một ưu tiên có căn cứ. Người dùng có thể chọn khác. Dùng
   [cấu trúc tri thức](references/knowledge-structure.md) để định nơi lưu, tên,
   chủ sở hữu, phiên bản, cách tìm và điều kiện cập nhật.
5. Khi được yêu cầu, tạo mẫu hoặc nội dung tài sản cụ thể từ nguồn đã có;
   không chỉ đưa khung nếu yêu cầu là làm ra sản phẩm hoàn chỉnh.

## Đầu ra và hoàn thành

Trong `opc-doc/outputs/07-asset-ops/`, chuẩn bị:

- `asset-inventory-[YYYYMMDD-HHmmss].md`: tài sản, nguồn, bằng chứng lặp lại, lợi ích/chi phí.
- `action-plan-[YYYYMMDD-HHmmss].md`: ưu tiên đã xác nhận, bước làm, phụ trách, tiêu chí dùng lại.

Dùng múi giờ người dùng; nếu trùng tên, thêm bộ đếm. Không ghi đè lịch sử.
Hoàn thành khi có tài sản thật, thứ tự ưu tiên và kế hoạch được xác nhận.
Gửi quyết định và đề xuất `07-asset-ops` → `execution` hoặc bước cần sửa cho
trưởng nhóm; chuyên gia được giao việc không tự ghi trạng thái chung. Không tự ép chuyển sang 08.
