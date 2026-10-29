# Khảo sát LiveSign — 29-10-2026

**Trạng thái: chưa qua cổng.** Đã có số đo thật; còn duyệt nhãn và gán bbox độc lập để chốt tuyến/lớp.

Đã bổ sung [bảng tuyến/lớp và hướng dẫn bước duyệt](stage0-review-next.md). Có 18 mã để so sánh; chưa có danh mục chính thức.

## Độ phủ vùng mẫu

Các vùng là bbox trong cấu hình, không phải toàn quận. Độ phủ dùng trung điểm đoạn đường ≤10 m, bán kính ảnh 30 m.

| Vùng | 2023: ảnh / người | 2024: ảnh / người | 2025: ảnh / người | Đường OSM | Có ảnh ≥2 năm |
|---|---:|---:|---:|---:|---:|
| Hoàn Kiếm | 6.602 / 5 | 8.202 / 10 | 155.125 / 5 | 148,725 km | 80,313% |
| Cầu Giấy | 19.445 / 3 | 35.216 / 12 | 526.865 / 9 | 546,340 km | 65,738% |
| Hà Đông | 138.708 / 3 | 33.737 / 7 | 331.662 / 5 | 442,302 km | 57,602% |

## Tuyến ứng viên ở Hoàn Kiếm

| Tuyến | Độ dài OSM | 2023: ảnh / người | 2024: ảnh / người | 2025: ảnh / người |
|---|---:|---:|---:|---:|
| Phố Huế – Hàng Bài | 1.485,8 m | 148 / 3 | 347 / 5 | 5.747 / 4 |
| Trần Quang Khải | 1.495,3 m | 238 / 3 | 126 / 4 | 4.135 / 4 |
| Tràng Thi – Hai Bà Trưng | 1.537,0 m | 283 / 2 | 471 / 5 | 7.047 / 4 |

Đây là ảnh đi qua trong 30 m. Chưa chứng minh biển đúng lớp hiện diện hay quay về camera trong từng ảnh.
Đã xuất 4.554 dòng feature–năm và 246 dòng tổng hợp nhãn gợi ý. Feature có thể trùng biển vật lý; không dùng count này làm ground truth.

## Ảnh và detector có sẵn

Đã khóa và tải đủ 108 ảnh, gồm 12 ảnh/tuyến/năm. Có 104/108 ảnh rộng ≥2.048 px.
Cả 36 ảnh năm 2023 là panorama và không có `camera_parameters`; ảnh mẫu 2024/2025 có thông số camera.
PoC ONNX chạy đủ 108 ảnh, sinh 30 bbox trên 23 ảnh. Có dự đoán ở 5/36 ảnh năm 2023, 8/36 ảnh năm 2024 và 10/36 ảnh năm 2025.
Trung vị cạnh ngắn của bbox **dự đoán** là 56,2 px. Recall và phân bố bbox thật: **cần gán tay**.
Không dùng tỷ lệ 23/108 để kết luận bài thử B3. Bằng chứng âm đang tắt.

## Dataset và nhãn

[Roboflow vietnam-traffic-sign-altsi v3](https://universe.roboflow.com/giang-yp9g1/vietnam-traffic-sign-altsi/dataset/3) khai báo CC BY 4.0 qua project API.
Đếm annotation thực: 9.635 ảnh, 18.486 object, 56 nhãn. Có 9.535 hash ảnh duy nhất và 100 nhóm trùng tuyệt đối, chưa thấy trùng SHA-256 giữa split.
pHash sau EXIF: chưa chạy. Đã tạo 4 ảnh ghép, mỗi nhãn có tối đa 3 crop thật; chưa gọi đây là kiểm toàn bộ nhãn.

Đối chiếu sơ bộ crop với QCVN thấy `W-235` chứa hình trẻ em, `P-245a` dùng hình Đi chậm, `R-407a` có hình chỉ dẫn đường một chiều.
`P-123a` có crop mang biểu tượng ô tô; không thể tự map toàn bộ nhãn này sang biển cấm rẽ áp dụng cho mọi xe.
Các ca này được ghi trong `reports/stage0/datasets/vietnam-traffic-sign-altsi-v3/label-audit.csv`; trạng thái vẫn cần duyệt.
Kaggle `phhasian0710/za-traffic-2020` phiên bản 1 khai báo **Unknown** qua API; chưa tải hay dùng để train.
Nguồn Zalo AI 2020: chưa xác nhận được giấy phép từ nguồn chính; chưa tải hay kiểm object.

## Việc cần để mở cổng

Dùng [trang duyệt ảnh cục bộ](http://127.0.0.1:8766/review/routes/index.html) để gán bbox đúng mã QCVN trên ảnh gốc.
Đối chiếu các crop có cảnh báo. Từ bằng chứng đã duyệt mới lập bảng 10–15 mã đủ mẫu ở train và trên tuyến qua cả ba năm.
Sau đó người dùng duyệt tuyến/lớp. Chưa train; chưa chuyển sang backend hoặc Android.
