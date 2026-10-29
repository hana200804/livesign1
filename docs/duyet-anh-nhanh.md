# Duyệt 12 ảnh đầu

Mở http://127.0.0.1:8766/review/routes/index.html. Chọn tuyến **Phố Huế – Hàng Bài**, năm **2023**.
Danh sách còn 12 ảnh. Chưa cần duyệt cả 108 ảnh trong một lần.

1. Chọn ảnh, đợi tải xong. Dùng thu phóng 100%, 200% hoặc 300%; cuộn vùng ảnh để xem các góc, nhất là ảnh panorama.
2. Nếu nhận rõ mã biển, nhập mã QCVN có dấu chấm, ví dụ `P.102`, rồi kéo khung sát mặt biển. Mỗi biển có một khung; đổi mã trước khi vẽ biển khác.
3. Vẽ đủ các biển nhìn rõ. Nếu có biển mờ, bị che hoặc chưa xác định được mã, chọn **Chưa rõ / cần xem lại** cho ảnh đó. Không đoán mã hoặc coi ảnh là rỗng.
4. Nếu đã xem toàn ảnh và thật sự không có biển, tích xác nhận không có biển. Khi có bbox thì bỏ tích này.
5. Bấm **Lưu đã duyệt**, rồi **Tiếp**. Khung mới hoặc xóa khung làm ảnh về chưa duyệt; cần lưu lại sau khi sửa.
6. Bấm **Xuất kết quả duyệt**. Gửi đường dẫn tệp JSON vừa tải xuống trong chat. Tệp xuất vẫn có đủ ID của 108 ảnh; ảnh chưa làm giữ pending là đúng.

Các khung lưu trong trình duyệt đang dùng. Xuất JSON sau mỗi đợt để giữ bản sao.
Không xóa dữ liệu trình duyệt hoặc đổi trình duyệt trước khi xuất. Nếu ảnh tải lỗi, công cụ khóa nút duyệt.

Đối chiếu mã với [QCVN 41:2024/BGTVT bản chính thức](https://datafiles.chinhphu.vn/cpp/files/vbpq/2024/11/51-bgtvt-kem.pdf).
Không dùng nhãn gợi ý Mapillary hoặc dự đoán detector làm đáp án.
Đợt này chỉ phục vụ khảo sát và chấm PoC, chưa thay tập kiểm tra độc lập của model cuối hoặc bài thử B3.
