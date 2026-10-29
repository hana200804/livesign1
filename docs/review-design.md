# Giao diện duyệt ảnh khảo sát

Áp dụng skill frontend-design cho công cụ duyệt cục bộ, chưa phải web admin của MVP.

## Lựa chọn thiết kế

- Xanh chỉ dẫn `#174878` cho thao tác chính; nền xem ảnh `#eef3f8`; mực `#182d42`.
- Vàng `#ffcf48` cho phần cần chú ý; đỏ `#d33c4a` cho bbox; trắng `#ffffff` cho vùng điều khiển.
- Bahnschrift cho tên công cụ, Segoe UI cho tiếng Việt và hướng dẫn.
- Ba vùng: danh sách ảnh theo năm, ảnh gốc có cuộn/zoom, khung gán nhãn và quyết định.
- Trên màn hình hẹp, các vùng xếp dọc. Có focus bàn phím và thông báo trạng thái đọc được.

## Điều chỉnh theo bài toán

Ảnh gốc chiếm vùng làm việc chính. Không có thẻ số liệu lớn hay hình trang trí.
Các khung bbox dùng đúng tọa độ px của ảnh gốc sau khi quy đổi từ kích thước hiển thị.
Ảnh của detector không xuất hiện mặc định để hạn chế ảnh hưởng việc gán độc lập.
Trạng thái chưa duyệt, đã duyệt và chưa rõ được ghi bằng chữ; không chỉ phân biệt bằng màu.

## Đã kiểm

Trang thật đã mở trong trình duyệt. Đọc đủ 108 ảnh trong danh sách và mở được ảnh 2.048 × 1.536 px.
Đã kiểm bộ lọc Phố Huế – Hàng Bài + 2023: có đúng 12 ảnh, ảnh đầu tải được ở kích thước 2.048 × 1.024 px.
Thử lưu ảnh chưa có bbox, chưa xác nhận rỗng: giao diện chặn và count đã duyệt vẫn 0.
Chưa tự gán ground truth trên ảnh thật. Export file và thao tác vẽ cần được kiểm tiếp với dữ liệu thử riêng.
