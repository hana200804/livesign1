# Khảo sát dữ liệu

## Phương pháp

1. Dùng ba bbox ghi rõ trong `config/survey.yaml`. Chúng là vùng mẫu Hoàn Kiếm, Cầu Giấy và Hà Đông; không thay cho toàn quận.
2. Lấy metadata ảnh từ vector tile Mapillary mức 14. Khử trùng bằng ID ảnh. Dùng `creator_id` để đếm người chụp.
3. Chỉ giữ ảnh có năm UTC từ `captured_at` thuộc 2023/2024/2025. Không lấy năm của feature để suy năm ảnh.
4. Lấy đường OSM qua API chính thức, chia bbox nhỏ để không vượt 50.000 nút/yêu cầu. Gộp cùng node/way ID.
5. Chỉ tính cạnh đường chạy xe theo bộ lọc trong `survey/osm.py`; cắt cạnh tại biên bbox và khử cạnh trùng theo cặp node ID.
6. Chia mỗi cạnh thành đoạn ≤10 m. Lấy trung điểm với trọng số là chiều dài đoạn. Một điểm được phủ khi có ảnh cách ≤30 m.
7. Báo % chiều dài có ảnh ở ít nhất hai năm khác nhau. Đây là xấp xỉ lấy mẫu trên cạnh OSM, không phải phép hợp buffer hình học chính xác.
8. Tải thêm ảnh trong vành đệm 30 m quanh vùng để hạn chế mất ảnh ở biên. Count vùng chỉ tính ảnh trong bbox; mẫu số đường cũng chỉ ở bbox.
9. Tìm đường nối các điểm neo trên đồ thị OSM có hướng. Cắt gần 1.500 m tại node OSM thật. Không nối tâm ô.
10. Lấy feature biển báo trong 30 m của tuyến làm nhãn gợi ý. Với từng feature, đếm mọi ảnh đi qua trong 30 m cho từng năm, gồm cả năm có số đếm 0.

Đường một chiều cơ bản và access được xét khi tạo tuyến. Hạn chế rẽ theo relation, thời gian và từng loại xe chưa kiểm trong công cụ khảo sát.
Đường hai chiều có các way tách biệt được tính theo cạnh OSM riêng. Kết quả không phải chiều dài các tên phố đã gộp.

## Độc lập và năm

100 sequence từ một người trong một năm vẫn là 1 cặp người–năm.
Thiếu ID người chụp được báo riêng, không thay ID bằng sequence để tăng số nguồn độc lập.
Ảnh đi qua gần một feature không có nghĩa biển xuất hiện trong ảnh, quay về camera hoặc không bị che.
Count feature Mapillary không phải count biển vật lý độc lập. Các bản dựng trùng vẫn có thể tồn tại.

## Chất lượng ảnh

Mẫu khóa gồm 12 ảnh/tuyến/năm, chọn bằng hash cố định từ ảnh đi qua. Có 108 ID ảnh khác nhau.
Khóa danh sách trước PoC. Tải metadata từng ID và tải thumbnail thật, đo width/height từ tệp ảnh.
Phân biệt URL có tên 2048 với tệp thực sự rộng ≥2.048 px.
`route-quality.csv` là metadata của toàn bộ ảnh gần tuyến, có trường chưa biết để trống.
`sample-route-quality.csv` là số đo trên mẫu. Không lấy tỷ lệ của mẫu ghi như tỷ lệ đã đo toàn corpus.
Phân bố bbox thật cần gán tay. Cỡ bbox của dự đoán chỉ mô tả detector, không thay ground truth.

## Dataset

Lưu URL phiên bản chính xác, giấy phép khai báo, hash archive và hash inventory.
Kiểm từng annotation gốc. Nhãn lẫn nhiều mã phải xem crop và xử lý trước train.
Kiểm SHA-256 ở khảo sát; pHash sau EXIF và chia nhóm chạy trong Giai đoạn 2.
Kaggle/Zalo chưa xác nhận được quyền sử dụng thì chỉ ghi metadata và lý do chưa tải, không đưa vào tập train.

## Tệp đầu ra

| Tệp trong reports/stage0 | Nội dung |
|---|---|
| region-coverage.csv | Count vùng/năm và độ phủ đường ≥2 năm |
| routes/candidates.csv | Độ dài thực và độ lệch điểm neo của ba tuyến |
| routes/*.geojson | Tọa độ, node/way OSM và nguồn hình học |
| route-quality.csv | Count người/sequence/ảnh và metadata camera theo tuyến/năm |
| route-feature-years.csv | Từng feature gợi ý × năm, gồm count 0 |
| route-hint-summary.csv | Tổng hợp nhãn gợi ý, số feature có ảnh và ≥2 người đi qua |
| sample-quality.csv | Kích thước, hash và camera của ảnh mẫu đã tải |
| sample-route-quality.csv | Tỷ lệ chất lượng trên mẫu, có mẫu số rõ |
| datasets/*/label-counts.csv | Object thật theo nhãn gốc/split |
| datasets/*/crop-review.csv | Crop được chọn và trạng thái duyệt |
| poc-frames.csv | Số bbox dự đoán và thời gian CPU từng ảnh |
| *manifest.json | Nguồn, hash, cấu hình và trạng thái chưa kiểm |

## Duyệt cổng

Gán bbox trên ảnh gốc, độc lập với overlay của detector. Đánh dấu ảnh chưa rõ; không đoán biển từ nhãn AI.
Đối chiếu crop và mã QCVN. Sau đó mới lập bảng 10–15 mã có đủ mẫu train và bằng chứng ảnh thật qua cả ba năm.
Người dùng duyệt bảng tuyến/lớp trước khi tạo danh mục chính thức và chuyển sang hợp đồng.
Chưa có ngưỡng tối thiểu mẫu mỗi lớp được duyệt; không gọi một lớp là “đủ” chỉ vì có 1 feature gợi ý.
