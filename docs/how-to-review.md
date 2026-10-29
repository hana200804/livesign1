# Duyệt ảnh trước khi train

Mẫu 108 ảnh dùng để đo detector có sẵn và kiểm tra dữ liệu tuyến. Đây chưa phải tập test cuối.

1. Mở [trang duyệt trên máy](http://127.0.0.1:8766/review/routes/index.html).
2. Chọn năm. Dùng phóng to 100–300% để xem từng biển ở ảnh gốc.
3. Khi nhận ra đúng mã QCVN, nhập mã rồi kéo một khung sát phần mặt biển. Mỗi biển có một khung riêng.
4. Ví dụ mã nhập có dạng `P.102`, `P.131a`, `I.407a`. Đây chỉ là ví dụ cách ghi; chưa phải danh mục lớp đã chốt.
5. Có biển nhưng không đọc rõ mã hoặc không đủ rõ để vẽ khung thì chọn **Chưa rõ / cần xem lại**. Không đoán.
6. Chỉ xác nhận ảnh rỗng khi đã xem toàn ảnh và không có biển báo. Không dùng lựa chọn này thay cho biển quá nhỏ hoặc mờ.
7. Bấm **Lưu đã duyệt**, rồi sang ảnh tiếp theo.
8. Bấm **Xuất kết quả duyệt** để lưu JSON. Giữ tệp này; trình duyệt chỉ lưu tạm theo máy và địa chỉ trang.

Đối chiếu hình và mã từ [QCVN bản nguồn](https://datafiles.chinhphu.vn/cpp/files/vbpq/2024/11/51-bgtvt-kem.pdf), phụ lục B/C/E.
Phân biệt mũi tên rẽ đơn với mũi tên có thêm biểu tượng ô tô. Không học mã trực tiếp từ nhãn dataset đã có cảnh báo.
Giữ ảnh gốc khi gán. Không lấy bbox của detector hay nhãn Mapillary làm câu trả lời mặc định.

Sau khi có tệp đã duyệt, công cụ nhập sẽ kiểm hash mẫu, hash ảnh, kích thước, mã nhãn và tọa độ bbox.
Ảnh **Chưa rõ** không tham gia ground truth. Xác nhận rỗng không tạo observation `not_seen`.
Tiếp theo mới tính recall, kiểm đủ lớp ở tuyến và train, rồi đưa bảng tuyến/lớp cho người dùng duyệt.
