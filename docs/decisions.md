# Quyết định

## 2026-10-29 — Cách vận hành

Theo cập nhật trực tiếp của người dùng, xây sản phẩm cho một người vận hành thay cho kế hoạch nhóm 3 người.
Người dùng đã chỉ định repo [hana200804/livesign1](https://github.com/hana200804/livesign1).
Repo đích đang public khi kết nối. Chỉ đưa mã nguồn, cấu hình mẫu và metadata nhỏ lên repo; giữ bí mật, ảnh, dataset và trọng số ở máy.
Repo cục bộ dùng nhánh `data/khao-sat-ban-dau`. Không tự merge, không force push và không bỏ kiểm tra.

## 2026-10-29 — Cổng dữ liệu

Giữ cổng khảo sát, duyệt tuyến/lớp và bật bằng chứng âm từ yêu cầu gốc.
Chưa chốt lớp bằng tên nhãn dataset. Chưa ghi lớp chính thức vào `ai/configs/classes.yaml`.
Các trường cần gán tay hoặc chưa đo phải có trạng thái rõ. Không lấy nhãn AI Mapillary làm ground truth.

## 2026-10-29 — Truy cập Mapillary

Thử truy vấn ảnh theo bbox đã gặp HTTP 500, mã dịch vụ 1, kể cả khi chỉ lấy ID.
Vector tile chính thức đọc được `creator_id`, `sequence_id`, `captured_at` và ID ảnh.
Dùng tile mức 14 để khảo sát; metadata camera và thumbnail lấy riêng theo ID ảnh, đường này đã chạy được.
Cache tile và metadata raw giữ ngoài Git. Không ghi URL có token vào log hay manifest.

## 2026-10-29 — Nguồn OSM

Các kết nối Overpass đã thử không hoàn tất trên môi trường này.
API OSM chính thức báo vượt 50.000 nút khi tải cả vùng Hoàn Kiếm một lần.
Chia bbox 0,005° để đọc map API, rồi gộp node/way theo ID, giữ hình học thật và cắt tại biên khảo sát.

## 2026-10-29 — Thử detector

Dùng ONNX có sẵn, có revision và SHA-256 cố định, để chạy PoC CPU trên 108 ảnh đã khóa.
Đây không phải model đã train cho LiveSign. Bbox dự đoán và tỷ lệ ảnh có dự đoán không phải recall.
PoC không quyết định bật B3. Bằng chứng âm giữ `false`.
Khi đến train, chuẩn bị Colab và hướng dẫn người dùng theo yêu cầu; không chạy train trước cổng dữ liệu.

## 2026-10-29 — Tách phụ thuộc

CI thuần chỉ cài pytest và PyYAML cùng phụ thuộc bắc cầu của pytest.
Pillow, NumPy, ONNX Runtime chỉ import bên trong lệnh crop/PoC. Không cần torch để chạy khảo sát thuần.
Core sản phẩm vẫn là Java thuần. Công cụ Python hiện tại không thay thế core.

## 2026-10-29 — Duyệt thủ công

Trang gán bbox mặc định hiển thị ảnh gốc và trạng thái chưa duyệt, không overlay dự đoán.
Ảnh rỗng cần xác nhận rõ. Ảnh chưa rõ bị loại khỏi ground truth.
Kết quả xuất có hash mẫu và ảnh; bộ nhập kiểm mã, bbox, kích thước và ID trùng.
Xác nhận ảnh rỗng ở công cụ này không tạo observation `not_seen`.

## 2026-10-29 — Đối chiếu tuyến/lớp và chấm PoC

Lập bảng 18 mã để so sánh, tách khỏi danh mục lớp chính thức. Không chốt 10–15 mã bằng số feature gợi ý.
Ưu tiên kiểm ảnh Hàng Bài vì có 14 mã trong giao sơ bộ giữa annotation gốc và gợi ý qua ba năm.
Không gọi số này là số lớp đã xác nhận; nhãn lẫn có thể làm số lớp hợp lệ giảm.
PoC dùng matching một–một có số cặp nhiều nhất trong các cặp cùng lớp, IoU ≥0,50.
Không gọi phép chấm này là mAP COCO. Bucket dùng cạnh ngắn bbox thật, có đơn vị px.
Ảnh thiếu dự đoán gây lỗi; ảnh chưa rõ không coi là ảnh âm. Thiếu nhãn hoặc ánh xạ đã duyệt thì kết quả not_run.
Nhận xét ảnh của trợ lý giữ riêng, không đánh dấu thành gán tay độc lập.
