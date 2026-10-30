---
name: opc-resource-audit
description: "Inventory eight founder resource categories. Use when clarifying experience, capabilities, relationships, channels, assets and constraints."
---

# Kiểm kê nguồn lực

Đọc [quy tắc chung](../opc-orchestrator/references/runtime-contract.md), [chính sách mô hình](../opc-orchestrator/references/model-routing.md)
và [vai trò](references/role-profile.md) trước khi thực hiện. Chỉ đọc lại khi chưa có
trong ngữ cảnh hoặc phiên bản thay đổi. Vai trò: `opc-resource-auditor`.
Đọc [hợp đồng lưu trạng thái](../opc-orchestrator/references/file-contract.md) khi cần lưu hoặc tiếp tục phiên.
Nếu bộ đọc chỉ truy cập được một skill, nạp `opc-orchestrator` bằng bộ đọc skill
để đọc tài liệu chung; chỉ đọc quy tắc, không khởi động lại quy trình kinh doanh.


## Phạm vi và đầu vào

Đọc `opc-doc/inputs/founder-profile.md`, `raw-ideas.md` và thông tin đã được xác nhận
trong hội thoại nếu có. Bước này chỉ kiểm kê; không chấm cơ hội, chọn ngành hoặc
suy diễn mức chịu rủi ro. Tái dùng câu trả lời cũ thay vì hỏi lại.

## Quy trình hai vòng

1. Quét tám nhóm, ưu tiên nhóm còn thiếu. Mỗi lần hỏi một câu có ích; ghi “chưa có”
   hoặc “chưa biết” khi đúng thực tế, không tự điền.
2. Đào sâu từng nguồn lực đang có: cụ thể là gì; quy mô và phân bố; phần dùng được
   ngay; cách huy động; chi phí về thời gian, tiền hoặc quan hệ. Chỉ hỏi phần còn thiếu.
3. Trình bày danh sách để người dùng sửa/xác nhận. Không coi một đoạn giới thiệu
   ban đầu là hoàn thành cả tám nhóm, nhưng dùng đầy đủ thông tin trong đoạn đó.

| Nhóm | Cần ghi |
| --- | --- |
| Kinh nghiệm | Ngành, công việc, việc từng làm thành công |
| Hiểu nhóm người | Nhóm từng tiếp xúc lâu dài, hoàn cảnh hiểu rõ |
| Năng lực | Chuyên môn, diễn đạt, thẩm mỹ, phán đoán, học tập |
| Quan hệ | Khách hàng, đối tác, mạng lưới tin cậy và khả năng huy động |
| Kênh | Tài khoản, cộng đồng, lượng người tiếp cận và hoạt động thực tế |
| Tài sản | Case, tài liệu, mẫu, công cụ, sản phẩm có thể dùng |
| Ràng buộc | Thời gian, sức lực, dòng tiền, gia đình |
| Giới hạn cứng | Việc không làm, điều kiện phải dừng; ghi sự thật, không suy diễn |

Đọc [nhóm nguồn lực](references/resource-categories.md) khi cần đào sâu và
[kiểm tra đầy đủ](references/scoring-rubric.md) trước khi kết thúc.

## Đầu ra và hoàn thành

Hoàn thành khi tám nhóm đều có thông tin đã xác nhận, “không có” hoặc mục chưa rõ
được người dùng chấp nhận; mỗi nguồn lực hiện có đủ chi tiết cho bước chọn ngách.
Chuẩn bị trong `opc-doc/outputs/01-resource-audit/`:

- `inventory.md`: danh sách tám nhóm, chi tiết và phần chưa rõ.
- `scorecard.json`: danh sách nguồn lực có cấu trúc; giữ tên cũ để tương thích,
  không dùng làm điểm phù hợp kinh doanh. Mỗi mục gồm `category`, `items`,
  `availability`, `activation_cost`, `unknowns`, `confirmed`.

Gửi đề xuất chuyển `01-resource-audit` → `02-niche-positioning` cho trưởng nhóm.
Khi là chuyên gia được giao việc, không ghi trực tiếp `opc-doc/state/`. Dừng phân tích chuyên môn ở danh sách nguồn lực.
