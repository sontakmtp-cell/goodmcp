# GoodMCP G6 — Design QA

final result: passed

Phạm vi: kiểm tra thiết kế G6 thích nghi từ mock theo yêu cầu bảo mật/khả năng API,
không phải clone pixel tuyệt đối. Gate runtime/revoke đã đóng bằng live React→API/Python và HTTP/MCP 26/26; xem
`Docs/reports/G6.md`. Lượt hoàn thành không sửa giao diện sản phẩm hoặc chụp lại
browser do hạn mức agent Terra; không nhận live DOM test là browser capture.

## Nguồn và bằng chứng

- Source: `UI-mock/GoodMCP_landing_page.png`, 1448×1086, cùng frame video
  `work/reference-video.png` từ `UI-mock/1-tile.mp4`.
- Implementation: `Docs/reports/assets/g6/portal-desktop.png`.
- CSS viewport 1448×1086, devicePixelRatio 1; screenshot API trả raster 1433×1075.
  Resize source theo cùng raster 1433×1075 trước khi ghép để so sánh; không khẳng định
  raster này là screenshot 1:1 CSS pixel. Mobile CSS 390×844 trả raster 375×812.
- Cùng trạng thái: desktop landing, ChatGPT selected, guide đóng, unauthenticated.
  Catalog public giả trong source được thay bằng login-gated empty state theo brief.
- Full comparison mở cùng input: `Docs/reports/assets/g6/design-comparison.png`.
- Focus comparison cùng input: `Docs/reports/assets/g6/design-comparison-focus.png`
  (hero/khung kết nối, crop theo cùng tọa độ của hai raster đã chuẩn hóa).
- Admin screenshot: `Docs/reports/assets/g6/admin-desktop.png`, `admin-mobile.png`.
  Admin không có mock riêng; kiểm theo bố cục/5 menu/token trong `Docs/design/G6-UI.md`.

## Findings và vòng sửa

Lượt 1: hero/khung kết nối thấp hơn reference khoảng 40–70px và khoảng trống trước
catalog lớn; cá mập gray khó nhận ra. Mức P2 về nhịp bố cục/độ rõ asset.
Đã giảm padding header/hero, line-height heading và margin; phối màu canvas bằng
CSS filter xanh, dùng classic shark từ source thật. Không vẽ asset thay thế.

Lượt 2: chụp lại cùng viewport/state; mở ảnh ghép full và focus ở trên. Hero/khung
kết nối cùng bố cục trung tâm, nút và nhãn đủ rõ. Chênh vị trí còn khoảng vài chục
pixel do font Việt, dòng cảnh báo placeholder và 5 lựa chọn thay 4; được chấp nhận
theo brief G6, không phát hiện mismatch P0/P1/P2 còn cần sửa cho thiết kế đã chốt.

Browser upload review: raw preview JSON mở sẵn gây rối và `{}` xuất hiện khi queued.
Mức P2 về nội dung. Đã thay bằng tên/version, số tệp/vai trò/giấy phép và giải thích
runtime; thông tin kỹ thuật nằm trong details đóng. Không hiển thị preview trước ready.
Ảnh sau sửa `Docs/reports/assets/g6/upload-preview.png` đã mở kiểm tra.

## Năm mặt kiểm tra

| Mặt | Nhận xét |
|---|---|
| Font/typography | Be Vietnam Pro local + system fallback; dấu Việt đầy đủ, heading rõ, wrapping ở 320/390px; ảnh mock không cung cấp font source |
| Spacing/layout | Hero giữa và khung 660px, mobile 1 cột; sidebar desktop/mobile nav riêng; không thấy tràn ngang các viewport đã thử |
| Màu/token | Portal tối/primary xanh, Admin sáng cùng primary; focus-visible 3px; không dùng màu làm tín hiệu trạng thái duy nhất |
| Asset/chất lượng | Dùng engine ASCII source thật + MIT, không video/screenshot nền; icon Phosphor; canvas trang trí aria-hidden/pointer-events none và nút dừng |
| Copy/content | Bỏ đăng ký, hàng trăm plugin và catalog bịa; URL mẫu được ghi rõ; dữ liệu riêng chỉ sau auth; tên Python có nhãn Việt và giới hạn được giải thích |

Khác biệt có chủ ý: không dùng logo từng nhà cung cấp từ mock khi chưa có asset
được cung cấp; dùng tên đầy đủ trên nút. Gradient chữ mock chuyển thành màu xanh
đồng nhất. Không có 4 plugin public mẫu. Không công khai số liệu hệ thống giả.

## Tương tác và accessibility

Browser đã kiểm chọn host bằng Enter, mở/đóng hướng dẫn, nút dừng chuyển động,
dialog Escape và focus return, upload/filechooser/preview/enable/export/disable,
callback OAuth, private list, schema form→job error, revoke→public. Console lượt cuối
không có error. 46 UI tests gồm axe DOM với giới hạn jsdom được ghi riêng.

Không có screen-reader/device acceptance hoặc chứng nhận WCAG. Engine gốc kiểm
prefers-reduced-motion; wrapper dừng khi tab ẩn và có pause thủ công. Chưa mô phỏng
OS reduced-motion trong browser tooling của lượt này.

## Follow-up polish

- P3: bổ sung asset logo chính thức của từng AI nếu có nguồn và nhu cầu dùng.
- P3: chạy contrast automation trên browser thật và screen reader khi công cụ sẵn sàng.
- Phần chức năng Python/revoke đã nghiệm thu riêng bằng live DOM và HTTP/MCP thật; visual pass không thay thế các kiểm tra đó.
