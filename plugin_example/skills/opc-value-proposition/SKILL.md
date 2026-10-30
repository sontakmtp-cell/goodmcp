---
name: opc-value-proposition
description: "Map customer jobs, pains and gains to an offer. Use when clarifying why customers buy or comparing value propositions."
---

# Thiết kế giá trị

Đọc [quy tắc chung](../opc-orchestrator/references/runtime-contract.md), [chính sách mô hình](../opc-orchestrator/references/model-routing.md)
và [vai trò](references/role-profile.md) trước khi thực hiện. Chỉ đọc lại khi chưa có
trong ngữ cảnh hoặc phiên bản thay đổi. Vai trò: `opc-value-designer`.
Đọc [hợp đồng lưu trạng thái](../opc-orchestrator/references/file-contract.md) khi cần lưu hoặc tiếp tục phiên.
Nếu bộ đọc chỉ truy cập được một skill, nạp `opc-orchestrator` bằng bộ đọc skill
để đọc tài liệu chung; chỉ đọc quy tắc, không khởi động lại quy trình kinh doanh.


## Đầu vào và quy trình

Đọc `opc-doc/outputs/02-niche-positioning/candidates.md`, `target-segment.json`,
`positioning-statement.md` hoặc kết luận đã xác nhận trong hội thoại.

1. Xác nhận nhóm khách đang xét. Mỗi nhóm có một bản giá trị riêng.
2. Làm rõ **Jobs** (việc khách muốn làm), **Pains** (trở ngại) và **Gains**
   (kết quả mong muốn); phân biệt lời khách nói với suy đoán của người sáng lập.
3. Ghép sản phẩm/dịch vụ với phần giảm đau và phần tạo lợi ích. Chỉ ra khoảng
   không khớp, nhu cầu chưa có bằng chứng và lời hứa chưa chứng minh được.
4. So sánh tối đa ba hướng như tiết kiệm công sức, kết quả hoặc giảm rủi ro.
   Nêu ai phù hợp, lợi ích, chi phí/đánh đổi; đề xuất hướng có căn cứ, để người
   dùng chọn hoặc sửa. Không tự tạo lời chứng thực hay đảm bảo kết quả.

Đọc [canvas](references/vpc-lite.md) và [mẫu thông điệp](references/messaging-template.md)
khi lập bản đầu ra. Ở bước này xác định logic giá trị; chiến lược giá thuộc 04,
thử nghiệm thuộc 05 và nội dung tiếp cận đầu tiên thuộc 05/06.

## Đầu ra và hoàn thành

Chuẩn bị trong `opc-doc/outputs/03-value-proposition/`:

- `value-proposition-canvas.md`: Jobs/Pains/Gains, sản phẩm/dịch vụ, giảm đau, tạo lợi ích.
- `segment-vp-matrix.md`: nhóm khách × giá trị × bằng chứng × khoảng chưa rõ.
- `messaging.md`: giá trị chủ đạo đã xác nhận và cách diễn đạt trung thực.

Hoàn thành khi canvas đủ các phần và người dùng xác nhận hướng chủ đạo.
Gửi thay đổi quyết định cùng đề xuất `03-value-proposition` → `04-business-model`
cho trưởng nhóm; chuyên gia được giao việc không tự cập nhật `state/`.
