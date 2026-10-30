---
name: opc-niche-positioning
description: "Find and compare business niches using market shifts, leverage and founder resources. Use when selecting a target segment or positioning."
---

# Chọn thị trường ngách

Đọc [quy tắc chung](../opc-orchestrator/references/runtime-contract.md), [chính sách mô hình](../opc-orchestrator/references/model-routing.md)
và [vai trò](references/role-profile.md) trước khi thực hiện. Chỉ đọc lại khi chưa có
trong ngữ cảnh hoặc phiên bản thay đổi. Vai trò: `opc-niche-strategist`.
Đọc [hợp đồng lưu trạng thái](../opc-orchestrator/references/file-contract.md) khi cần lưu hoặc tiếp tục phiên.
Nếu bộ đọc chỉ truy cập được một skill, nạp `opc-orchestrator` bằng bộ đọc skill
để đọc tài liệu chung; chỉ đọc quy tắc, không khởi động lại quy trình kinh doanh.


## Đầu vào

Đọc `opc-doc/outputs/01-resource-audit/inventory.md`, `inputs/market-notes.md`,
`inputs/raw-ideas.md` nếu có. Dùng nguồn lực đã xác nhận trong hội thoại nếu file
chưa có; thiếu căn cứ quan trọng thì hỏi bổ sung hoặc ghi rõ bước bị bỏ qua.

## Ba vòng tìm cơ hội

1. **Biên thị trường thay đổi:** khảo sát công nghệ, đường truyền thông, hành vi
   khách hàng, chính sách và quy tắc nền tảng. Tìm việc trước đây khó làm nhưng
   hiện có thể thực hiện. Hỏi vì sao doanh nghiệp hiện hữu chưa đáp ứng: xung đột
   với khách cũ, biên lợi nhuận thấp hay chi phí chuyển đổi. Không mặc định họ
   không thể cạnh tranh; tìm phản chứng và nguồn hiện tại.
2. **Đòn bẩy:** tìm phần có thể nhân rộng bằng phần mềm hoặc truyền thông;
   AI giúp tạo các đòn bẩy đó. Phân biệt tăng tốc một thao tác với tự động hóa
   cả quy trình. Kiểm tra chi phí biến đổi, kiểm soát chất lượng và phần cần con
   người; không hứa chi phí bằng không hoặc tự động hóa 100% khi chưa đo.
3. **Nguồn lực riêng:** ghép kinh nghiệm, quan hệ, kênh và tài sản của người sáng
   lập vào hai vòng trên. Không thu thập lại nguồn lực đã có.

## So sánh và lựa chọn

Tạo tối đa ba ngách có căn cứ, không bịa ngách thứ ba cho đủ số. Mỗi ngách ghi:
khách là ai và đang ở hoàn cảnh nào; vấn đề; vòng được kích hoạt; lý do đúng thời
điểm; đối thủ và khả năng phản ứng; rủi ro; bằng chứng và điều chưa biết.

Chấm sáu chiều theo [thang điểm](references/niche-evaluation.md): `pain`,
`leverage`, `window`, `resource_fit`, `standardization`, `cashflow`.
Điểm đã chấm là số nguyên 1–5; chưa rõ dùng `null`, không dùng 0.
`total` chỉ bằng tổng sáu điểm khi tất cả đã biết, còn lại là `null`.
Đây là đánh giá định tính, không phải xác suất thành công. Nêu căn cứ từng điểm;
không xếp hạng như chắc chắn nếu khoảng thiếu dữ liệu có thể đảo kết quả.

Đề xuất một phương án có căn cứ cùng đánh đổi; người dùng có thể chọn, trộn, sửa
hoặc đưa ngách khác. Dùng [kiểm tra thị trường](references/market-scan-checklist.md)
và [câu định vị](references/positioning-formula.md) khi cần.
Chỉ chốt ai, đau gì, vì sao có cơ hội và vì sao phù hợp; kế hoạch thử và nội dung
thực tế thuộc 05/06. Nếu người dùng yêu cầu chuyển bước, chuyển theo quy tắc chung.

## Đầu ra và hoàn thành

Sau xác nhận, chuẩn bị trong `opc-doc/outputs/02-niche-positioning/`:

- `three-ring-analysis.md`: ba vòng, nguồn và phản chứng.
- `candidates.md`: phương án thực tế, điểm sáu chiều, đánh đổi và điều chưa biết.
- `target-segment.json`: `segment`, `core_pain`, `timing`, `rings_activated`,
  `opportunity_score` với sáu khóa trên và `total`, `why_viable`,
  `why_big_players_wont`, `evidence`, `unknowns`. Nhãn đối thủ là giả thuyết nếu chưa kiểm chứng.
- `positioning-statement.md`: giúp ai, việc gì, bằng ưu thế nào, vì sao bây giờ.

Hoàn thành khi có phân tích ba vòng, so sánh sáu chiều và ngách/định vị đã xác nhận.
Gửi đề xuất chuyển `02-niche-positioning` → `03-value-proposition` cho trưởng nhóm.
Khi là chuyên gia được giao việc, không ghi trực tiếp trạng thái chung. Không có ngách đủ tốt thì nêu điều còn thiếu
và đề xuất thu bằng chứng hoặc mở rộng phạm vi, không ép chọn.
