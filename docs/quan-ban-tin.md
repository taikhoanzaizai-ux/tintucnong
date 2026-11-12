# Kết nối Tin Nóng và Quân Bản Tin

Tin Nóng Windows 2.4.0 chuyển tiêu đề và lời đọc sang Quân Bản Tin Desktop 1.13.0 bằng tệp dự án JSON.

1. Trong Tin Nóng, mở **Tạo bản tin**, tạo hoặc chỉnh bản nháp.
2. Bấm **Xuất sang Quân Bản Tin**. Chọn nơi lưu tệp JSON. Tin Nóng sao chép đường dẫn.
3. Trong Quân Bản Tin, chọn **Mở dự án**, dán đường dẫn và mở tệp.
4. Thêm tư liệu trong **Ảnh & video**.

## Định dạng trao đổi

Hàm `script_project` trong `TinNong.py` tạo dự án JSON phiên bản 10. Tệp dùng UTF-8, có `title`, `script`, `pictures: []` và `scenes: []`. Quân Bản Tin nhập tệp bằng trình mở dự án hiện có.

GitHub quản lý mã và phiên bản. Tệp dự án được chuyển cục bộ giữa hai ứng dụng trên Windows. Chỉ chọn **Mở dự án** sau khi đã lưu công việc đang chỉnh.

Khi thay đổi định dạng, kiểm tra lại việc xuất từ Tin Nóng và mở dự án trong Quân Bản Tin với một kịch bản tiếng Việt có dấu. Tài liệu này mô tả luồng nhập tệp thủ công hiện có.
