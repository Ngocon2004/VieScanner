# Trang quản trị (Admin Dashboard)

Trang `/admin` cho quản trị viên theo dõi chất lượng OCR, tình trạng hệ thống và quản lý người dùng.
Chỉ tài khoản `role = "admin"` vào được; người dùng thường thấy "Không có quyền truy cập", và mục
"Quản trị" trên thanh điều hướng chỉ hiện với admin.

## Cấp quyền admin

Không có đường đăng ký admin qua web. Dùng script ở backend:

```bash
cd backend
venv\Scripts\python.exe scripts\create_admin.py admin@example.com           # nâng quyền tài khoản đã đăng ký
venv\Scripts\python.exe scripts\create_admin.py admin@example.com --create  # tạo mới, hỏi mật khẩu
```

Sau khi có admin đầu tiên, admin có thể cấp/thu quyền và khóa/mở khóa tài khoản khác ngay trên trang.
Admin không thể tự hạ quyền hoặc tự khóa mình, nên hệ thống không bao giờ mất admin cuối cùng.

## Bố cục

```text
┌ Tiêu đề ─────────────────────────────── [7 ngày | 30 ngày | 90 ngày] [Làm mới] ┐
│ Lượt quét │ Tỉ lệ thành công │ Thời gian xử lý (trung vị, p90) │ Lượt quét đã xuất │
│ Người dùng │ Job đang chạy                                                       │
├ Lượt quét theo ngày (cột chồng) ─────────────────┬ Lý do thất bại (thanh ngang) ─┤
├ Chất lượng đọc từng trường (bảng) ───────────────┬ Hệ thống ──────────────────────┤
├ Người dùng: tìm kiếm, đổi vai trò, khóa/mở khóa ──────────────────────────────────┤
└ Lượt quét gần đây: lọc Tất cả / Thành công / Thất bại ────────────────────────────┘
```

Bộ lọc thời gian nằm một hàng phía trên và áp cho toàn bộ số liệu tổng quan. Kỳ "N ngày" là N ngày lịch theo giờ Việt Nam tính cả hôm nay, nên tổng ở ô số liệu luôn bằng tổng các cột của biểu đồ. Tải số liệu lỗi thì hiện thông báo kèm nút "Thử lại". Trên điện thoại các khối
xếp thành một cột; biểu đồ và bảng cuộn ngang bên trong khung, cả trang không cuộn ngang.

## Ý nghĩa từng khối

| Khối | Số liệu | Dùng để |
|---|---|---|
| Ô số liệu | Tổng lượt quét, thành công/thất bại, thời gian xử lý trung vị và p90, số lượt quét đã xuất Excel, số ô người dùng phải sửa, người dùng mới, job đang chạy | Nhìn nhanh sức khỏe hệ thống trong kỳ |
| Lượt quét theo ngày | Cột chồng thành công (xanh) / thất bại (cam), giờ Việt Nam; rê chuột xem số liệu từng ngày; có chế độ xem dạng bảng | Phát hiện ngày có tỉ lệ lỗi tăng bất thường |
| Lý do thất bại | Đếm theo mã lỗi (ảnh kém chất lượng, không thấy 4 góc thẻ...) | Biết nên cải thiện bước nào hoặc hướng dẫn người dùng chụp lại thế nào |
| Chất lượng từng trường | 5 trường của danh sách xuất Excel: tỉ lệ đọc được, số ô độ tin cậy thấp, số lần người dùng phải sửa khi xuất | **Đo độ chính xác thực tế**: "bị sửa khi xuất" chính là lỗi OCR mà người dùng phát hiện |
| Hệ thống | Engine OCR và trạng thái nạp model, hàng đợi, QR, cache, chính sách lưu giữ, phiên bản pipeline, job theo trạng thái | Kiểm tra cấu hình đang chạy khi có sự cố |
| Người dùng | Email, vai trò, trạng thái, số lượt quét, số lượt quét đã xuất, lần quét gần nhất (hiện 200 người mới nhất; dùng tìm kiếm cho người khác) | Quản lý tài khoản |
| Lượt quét gần đây | Thời gian, người dùng, kết quả, số CCCD đã che, số trường đọc được/cần xem, thời gian xử lý, nguồn (Job/API) | Tra cứu nhanh lượt quét lỗi |

## Quyền riêng tư

Trang quản trị **không hiển thị dữ liệu CCCD**: không có họ tên, ngày sinh hay địa chỉ của người được
quét. Số CCCD luôn ở dạng đã che (`001******123`). API trả số đếm và tỉ lệ, không trả `raw_data`.

## API (tất cả yêu cầu admin)

| Method | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/api/admin/overview?days=30` | Tổng quan, theo ngày, lý do lỗi, chất lượng từng trường, job theo trạng thái |
| GET | `/api/admin/system` | Cấu hình và trạng thái đang chạy |
| GET | `/api/admin/users?q=&limit=&offset=` | Danh sách người dùng kèm số lượt quét/hồ sơ |
| PATCH | `/api/admin/users/{id}` | `{role?, is_active?}`; tự hạ quyền/tự khóa trả 409 |
| GET | `/api/admin/scans?status=&limit=&offset=` | Lượt quét gần đây (đã che số CCCD) |

Tỉ lệ "bị sửa khi xuất" lấy mẫu số là các lượt quét có `scans.exported_at` (migration `0003`), được
đánh dấu mỗi khi lượt quét đó được xuất Excel. Bản sửa của lượt quét xuất trước khi có migration không
được tính, để tỉ lệ không vượt 100%.

## Biểu đồ

Vẽ bằng SVG tự viết, không thêm thư viện. Màu theo bảng categorical đã kiểm tra mù màu trên nền trắng
(xanh `#2a78d6`, cam `#eb6834`); chữ luôn dùng màu chữ, không dùng màu chuỗi; lưới mảnh, đầu cột bo 4px,
khe 2px giữa 2 phần của cột chồng; luôn có chú thích và chế độ xem dạng bảng.

## Thời gian

Mọi thời gian API trả về đều kèm múi giờ (`...Z`), trình duyệt tự đổi sang giờ địa phương. SQLite lưu
thời gian UTC nhưng trả về không kèm múi giờ; kiểu `UTCDateTime` (`backend/app/models/common.py`) gắn lại
UTC cho mọi response, nên không còn lệch 7 tiếng ở trang quản trị, Lịch sử và Bản ghi.
