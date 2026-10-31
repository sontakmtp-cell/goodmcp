# GoodMCP Web — G6

React + TypeScript + Vite. Hai bề mặt riêng: User Portal `/` và Admin Dashboard
`/admin`, dùng chung backend/OAuth G2 hiện có. Không có mock data trong ứng dụng.

## Chạy local

Backend G1–G5 phải đang chạy và `/health/ready` trả ready tại
`http://127.0.0.1:18080`. Từ repo có thể kiểm tra bằng `python scripts/local.py status`.
Frontend không tự dựng lại backend, cấp runtime mới hoặc thay dữ liệu đang có.

```powershell
cd H:\AI\goodmcp\apps\web
npm ci
npm run dev
```

Mở `http://127.0.0.1:4173/` hoặc `/admin`. Đăng nhập qua form G2 với tài khoản
local đã cấp; không tạo tài khoản công khai. Không chép password/token vào frontend.
Trang đăng nhập/consent/logout do G2 phục vụ; callback web dùng PKCE S256 + state + issuer.

User Portal chỉ xin quyền đọc. Owner/admin mở Quản trị sẽ xin lại các quyền ghi
cần thiết qua consent G2. Token chỉ ở RAM; tải lại trang cần đăng nhập/consent lại.
Client ID công khai được cache trong localStorage để tránh đăng ký client mỗi lần.
Upload resume chỉ lưu ID/key/tên/hash/kích thước theo workspace; phải chọn lại ZIP.

URL hiển thị mặc định `https://mcp.example.invalid/mcp`, có nhãn URL mẫu chưa triển khai.
Không dùng localhost làm URL connector cloud. `VITE_MCP_URL` chỉ được đặt thành URL
thật sau deployment/kiểm chứng của giai đoạn sau.

Vite proxy cố định đến backend loopback, chuẩn hóa Host/Origin phía server proxy
cho hợp đồng G2. Khi đổi backend local, đặt biến môi trường PowerShell
`$env:GOODMCP_API_ORIGIN` và `VITE_OAUTH_ISSUER` nhất quán. Không tự thêm CORS/bypass auth.
Không phơi dev server ra LAN/Internet. `dist/` là build tĩnh; production routing/TLS
không được triển khai trong G6.

## Kiểm tra

```powershell
npm test
npm run build
```

UI tests mặc định dùng fixture chỉ trong `src/test`, không ship trong bundle.
`src/test/live.test.tsx` mặc định skip; bật GOODMCP_LIVE=1 để kiểm React DOM với
OAuth/API/Python thật (đọc owner credential local trong RAM, không in/lưu token). Axe chạy trên
DOM, không đo layout/contrast trong jsdom. Browser evidence/responsive/keyboard
và kiểm tra API thật được tách trong `Docs/reports/G6.md`.

Từ repo: `.venv\Scripts\python.exe tests/wire_g6.py` chạy HTTP thật qua proxy local,
tạo plugin/project thử có nhãn, giữ nguồn private và tắt installation thử khi xong.
Không xóa dữ liệu cũ. Script trả exit 1 khi bất kỳ kiểm tra end-to-end chưa qua;
đừng đổi failure thành success để đóng gate. Runtime/revoke đã qua kiểm tra local; xem báo cáo cho bằng chứng và giới hạn API.

## Giới hạn có chủ ý

- Logs, tài nguyên, backup, quản lý người dùng/toàn bộ kết nối chưa có API quản trị.
- Job theo ID; chưa có API list toàn bộ job/upload. Resume dùng ID lưu trên thiết bị.
- Project: list/create/read, pin/revision, đọc/tải từng trang và lưu draft. Không UI
  commit/skip/rollback stage, host-profile editor hay export toàn bộ project.
- Form hỗ trợ scalar, enum và array enum đang dùng trong schema Python G4; schema
  phức tạp chưa hỗ trợ sẽ chặn chạy, không yêu cầu nhập JSON tùy ý.
- Phiên bản runtime mới vẫn phải do operator duyệt ngoài UI. Không tự thực thi mã ZIP.
- Revoke chỉ grant web hiện tại và phải kiểm chứng protected API trả 401.

Thiết kế: `Docs/design/G6-UI.md`. Bàn giao: `Docs/reports/G6.md`.

## Nguồn và giấy phép

ASCII sharks được vendored từ stackedlol/ascii-sharks, commit
`a0074c16a106f0abc665fe9712ca445f8f98ad8e` (MIT). Sáu file `.ts` nguồn giữ nguyên;
`Sharks.tsx` sở hữu vòng đời pause/visibility, CSS phối màu. Không dùng video làm
nền thay cho hiệu ứng thật. Xem `THIRD_PARTY_NOTICES.md`.
