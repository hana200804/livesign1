# Bảng tuyến và lớp để duyệt

Đây là bảng ưu tiên kiểm ảnh. Chưa có lớp nào được xác nhận đủ điều kiện.
Số trong cột tuyến là số feature gợi ý có ảnh đi qua theo từng năm,
lấy giá trị nhỏ nhất của ba năm. Đây không phải số biển đã thấy đúng mã.

| Mã ứng viên | Object train gốc | Hàng Bài | Trần Quang Khải | Tràng Thi | Ánh xạ |
|---|---:|---:|---:|---:|---|
| P.102 | 593 | 47 | 47 | 16 | pending |
| P.103a | 118 | 38 | 12 | 11 | pending |
| P.106a | 194 | 0 | 0 | 2 | pending |
| P.117 | 346 | 0 | 14 | 0 | pending |
| P.123a | 28 | 48 | 12 | 34 | mixed_sample |
| P.123b | 211 | 34 | 14 | 22 | needs_disambiguation |
| P.124a | 151 | 0 | 1 | 1 | pending |
| P.127 | 2717 | 2 | 2 | 1 | pending |
| P.128 | 7 | 2 | 0 | 0 | pending |
| P.130 | 1833 | 7 | 15 | 5 | pending |
| P.131a | 1504 | 217 | 111 | 201 | pending |
| R.302a | 545 | 7 | 18 | 0 | pending |
| R.303 | 109 | 0 | 1 | 0 | pending |
| I.407a | 138 | 115 | 21 | 20 | prefix_correction_candidate |
| W.209 | 39 | 1 | 0 | 0 | pending |
| W.225 | 143 | 2 | 0 | 2 | mixed_sample |
| W.227 | 46 | 1 | 1 | 1 | pending |
| W.233 | 58 | 2 | 0 | 0 | pending |

Mỗi mã vẫn cần duyệt crop và bbox ảnh tuyến cho 2023/2024/2025.
Số train chưa khử trùng; không lấy số này làm lượng mẫu hợp lệ cuối.
Danh sách hiện có 18 mã để so sánh; chưa phải danh mục 10–15 mã đã chọn.
Không tự thay dấu gạch ngang trong nhãn nguồn bằng dấu chấm rồi coi đó là mã đúng.
