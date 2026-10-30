---
name: opc-mvp-designer
description: "Design a measurable minimum experiment and launch materials. Use when testing a business hypothesis or preparing the first MVP run."
---

# Thiết kế thử nghiệm MVP

Đọc [quy tắc chung](../opc-orchestrator/references/runtime-contract.md), [chính sách mô hình](../opc-orchestrator/references/model-routing.md)
và [vai trò](references/role-profile.md) trước khi thực hiện. Chỉ đọc lại khi chưa có
trong ngữ cảnh hoặc phiên bản thay đổi. Vai trò: `opc-mvp-designer`.
Đọc [hợp đồng lưu trạng thái](../opc-orchestrator/references/file-contract.md) khi cần lưu hoặc tiếp tục phiên.
Nếu bộ đọc chỉ truy cập được một skill, nạp `opc-orchestrator` bằng bộ đọc skill
để đọc tài liệu chung; chỉ đọc quy tắc, không khởi động lại quy trình kinh doanh.


## Đầu vào và phạm vi

Đọc `opc-doc/outputs/04-business-model/risky-assumptions.md` và mô hình đã xác nhận.
MVP là phép thử nhỏ nhất đủ tạo bằng chứng, không phải sản phẩm nhiều tính năng.
Thiếu giả thuyết ưu tiên thì hỏi bổ sung hoặc ghi bước bỏ qua đã được cho phép.

## Thiết kế phép thử có thể thực hiện

1. Chọn một giả thuyết chính, người tham gia, tín hiệu cần đo và kết quả nào có
   thể bác bỏ giả thuyết. Tách lượt thích, lời khen khỏi bằng chứng sẵn sàng trả tiền.
2. So sánh tối đa ba hình thức phù hợp: dịch vụ làm tay, nội dung/đặt trước,
   trang chào hàng hoặc nguyên mẫu một chức năng. Đọc [hình thức MVP](references/mvp-patterns.md).
3. Dùng [mẫu thử nghiệm](references/experiment-template.md) để đặt thời hạn,
   quy mô/mẫu số, ngân sách tiền và giờ, thành công, thất bại, chưa đủ bằng chứng,
   và điều kiện dừng. Ngưỡng là thỏa thuận trước thử nghiệm, không là chuẩn thị trường.
4. Viết các bước chạy đầu tiên và phân công người/AI. Khi cần hoặc được yêu cầu,
   tạo ngay bài tiếp cận thử, câu hỏi phỏng vấn, cấu trúc trang chào hàng, checklist
   giao dịch/giao hàng tối thiểu. **Không yêu cầu có tài sản lặp lại hoặc hoàn tất 07.**
5. Tránh xây tính năng, SOP hoặc chiến dịch vượt quá điều cần để thử. Lưu bản nháp
   nội dung; gửi tin, xuất bản, thu tiền hoặc thao tác bên ngoài theo quyền đã được cấp.
   Việc soạn bản nháp không đồng nghĩa đã gửi hay đã chạy phép thử.

## Đầu ra và hoàn thành

Chuẩn bị trong `opc-doc/outputs/05-mvp-design/`:

- `mvp-spec.md`: giả thuyết, khách, hình thức, giới hạn trong/ngoài phạm vi.
- `experiment-plan.md`: số đo, mẫu số, ngưỡng, thời hạn, giới hạn chi phí, bước chạy,
  nguồn ghi dữ liệu và hành động sau từng kết quả.
- `human-ai-split.md`: người phụ trách, việc AI soạn, điểm cần người kiểm tra.
- `launch-kit.md` khi cần: nội dung/checklist cụ thể đủ bắt đầu phép thử.

Hoàn thành bước thiết kế khi người dùng xác nhận kế hoạch đủ khả thi và đo được.
Gửi đề xuất `05-mvp-design` → `06-conversion-loop` cho trưởng nhóm.
Giả thuyết vẫn `unverified`; chỉ sau khi phép thử thực sự diễn ra mới đề xuất
`supported`/`rejected`/`inconclusive` kèm dữ liệu. Không coi “đồng ý kế hoạch” là xác thực.
Chuyên gia được giao việc không tự ghi `state/`. Không hứa đã có khách hàng.
