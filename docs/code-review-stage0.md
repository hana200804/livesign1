# Rà soát công cụ khảo sát

Áp dụng `engineering-code-review`, `data-validate-data`, `mle-workflow` và `verification-loop` cho phần khảo sát, đối chiếu và duyệt ảnh.
Đây là tự rà soát mã và kiểm chứng bằng test; không thay người gán nhãn độc lập.

## Phát hiện đã xử lý

| Phần | Tình huống | Cách xử lý | Bằng chứng |
|---|---|---|---|
| Trang duyệt | Ảnh mới lỗi nhưng canvas có thể còn ảnh cũ | Xóa canvas ngay khi chuyển; khóa xác nhận đến khi tải đúng kích thước | Kiểm trình duyệt trên fixture riêng: ảnh 1 tải được, ảnh 2 cố ý thiếu; nút xác nhận và checkbox bị khóa, canvas đã xóa |
| Nguồn nhãn | Mẫu khóa bị đổi hoặc bảng chất lượng mất/trùng ID | Dừng dựng trang và nhập annotation | Test hash mẫu, thiếu ảnh, ID trùng và template khác mẫu khóa |
| Chấm điểm | Một dự đoán khớp nhiều biển hoặc greedily mất cặp hợp lệ | Matching một–một có số cặp tối đa, cùng lớp và IoU đạt ngưỡng | Test tình huống greedy mất cặp, class khác, IoU đúng biên và dự đoán trùng |
| Mẫu số | Thiếu dự đoán bị coi là 0 bbox; ảnh chưa duyệt bị coi ảnh âm | Thiếu dự đoán gây lỗi; chỉ chấm ảnh đã duyệt | Test thiếu dự đoán, pending/unclear, GT rỗng xác nhận rõ |
| Kết quả cũ | Chấm lại lỗi nhưng metrics trước còn được coi hợp lệ | Ghi manifest không hợp lệ trước khi kiểm đầu vào | Test chạy thành công rồi đổi hash hoặc xóa nhãn: trạng thái mới không công nhận CSV cũ |
| Đối chiếu lớp | Đếm trùng hàng nhãn/split hoặc suy lớp đã đủ từ feature | Chặn khóa trùng; cột đã xác nhận giữ rỗng | Test năm có số 0, thiếu năm, khóa trùng và trường confirmed rỗng |
| Đọc tile | Field protobuf sai kiểu có thể gây lỗi thuộc tính hoặc giải mã nhầm | Kiểm bytes/số nguyên trước khi giải mã | 12 ca kiểm field value/layer sai kiểu |
| Kiểu dữ liệu | Pyright phát hiện 23 lỗi, gồm biến có thể chưa khởi tạo và kiểu tensor chưa thu hẹp | Khởi tạo rõ ràng, kiểm tensor thực, kiểm client và stream UTF-8 | Pyright 1.1.414: 17 tệp, 0 lỗi, 0 cảnh báo |

## Kiểm chứng bổ sung

106 test đạt trong môi trường CI thuần pytest/PyYAML; Ruff và compileall đạt.
Coverage 7.17.0 đo độ phủ câu lệnh của toàn bộ `survey`, gồm cả CLI, mạng và PoC; xem số chính xác trong `reports/stage0/review-verification.json`.
Độ phủ khoảng 61%, chưa đạt mục tiêu 80% của skill verification-loop. Các đường chạy tải mạng và thư viện AI chưa được bao phủ đầy đủ bằng unit test.

Đã vẽ hai bbox trên ảnh giả lập 100 × 100 px bằng thao tác chuột thật:
khung ở zoom 100% xuất `[10,10,80,80]`; khung kéo ngược ở zoom 200% xuất `[20,30,50,70]`.
Đã lưu, tải lại trang thấy khung còn nguyên, tải JSON thật và đưa từng record qua bộ kiểm annotation.
Ảnh thử bị thiếu vẫn ở trạng thái pending, khóa nút duyệt. Đây là bài thử riêng, không nhập thành ground truth khảo sát.

Chạy kiểm kiểu tĩnh trong môi trường đã cài `requirements-dev.txt` và `requirements-poc.txt`:

```powershell
.\.venv\Scripts\python.exe -m pyright --pythonpath .venv/Scripts/python.exe survey scripts
.\.venv\Scripts\python.exe -m coverage run --data-file=data/cache/.coverage --source=survey -m pytest
.\.venv\Scripts\python.exe -m coverage report --data-file=data/cache/.coverage
```

## Giới hạn còn lại

Chưa có bbox người duyệt được nhập. Nhận xét ảnh của trợ lý không được đánh dấu thành ground truth.
Ánh xạ nhãn detector còn cần duyệt; các nhãn lẫn không thể tự bỏ để làm đẹp recall.
Chưa kiểm mọi trình duyệt hoặc thiết bị cảm ứng. Không coi số test đạt là chứng minh mọi lỗi đã hết.
Pipeline thu thập mạng, tải ZIP và ảnh lớn chưa được stress test. Toàn bộ ảnh/dataset/trọng số vẫn ở ngoài Git.
Chưa có backend, core Java hoặc Android trong phạm vi thay đổi này. Giai đoạn 0 vẫn chưa qua cổng.
