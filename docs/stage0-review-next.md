# Đối chiếu tuyến và lớp trước khi chốt

## Đã làm

Đã đối chiếu 18 mã ứng viên với annotation gốc và nhãn Mapillary gợi ý trên ba tuyến.
Mỗi mã có đủ dòng 2023/2024/2025, kể cả năm không có gợi ý. Không thay năm thiếu bằng năm gần nhất.
Xem [bảng đầy đủ](../reports/stage0/route-class-review.md) và [CSV từng tuyến/lớp/năm](../reports/stage0/route-class-candidates.csv).

| Tuyến | Độ dài | Mã có train gốc và gợi ý qua ba năm | Mã đã xác nhận đủ điều kiện |
|---|---:|---:|---|
| Phố Huế – Hàng Bài | 1.485,8 m | 14 | cần duyệt |
| Trần Quang Khải | 1.495,3 m | 13 | cần duyệt |
| Tràng Thi – Hai Bà Trưng | 1.537,0 m | 12 | cần duyệt |

Ưu tiên **kiểm ảnh** Phố Huế – Hàng Bài trước. Đây chưa phải quyết định chọn tuyến demo.
14 mã sơ bộ của tuyến này gồm I.407a, P.102, P.103a, P.123a, P.123b, P.127, P.128, P.130, P.131a, R.302a, W.209, W.225, W.227 và W.233.
Các mã P.123a/P.123b, I.407a và W.225 có vấn đề cần đối chiếu nhãn gốc. Số lượng sau duyệt có thể giảm dưới 10 mã.
Không lấy số gợi ý để kết luận đã đáp ứng cổng 10–15 mã.

## Kiểm ảnh nguyên bản

Đã xem trực tiếp ba ảnh Hàng Bài, mỗi năm một ảnh, không dùng overlay detector để quyết định nhãn.
Đây là nhận xét của trợ lý để định hướng duyệt, không phải ground truth của người gán độc lập.

| ID ảnh Mapillary | Năm | Nhận xét |
|---|---:|---|
| 1339843463577089 | 2023 | Ảnh panorama có méo hình; có mặt biển nhỏ gần mép đường. Cần phóng to và phân biệt biểu tượng ô tô. |
| 1000068565194742 | 2024 | Ảnh chụp qua xe có nhòe; không tự xác nhận rỗng khi chưa xem các vùng nhỏ. |
| 1098706578746584 | 2025 | Có bảng tròn mang biểu trưng trước công trình; cần phân biệt với biển cấm dừng/đỗ. Chưa gán mã. |

Các ID truy được tại `https://www.mapillary.com/app/?pKey=<ID>`.
Ảnh và bản xem trước giữ ở máy, không đưa lên Git. Nguồn ảnh: © Mapillary contributors.

## Duyệt và chấm

Xem [hướng dẫn duyệt 12 ảnh đầu](duyet-anh-nhanh.md) để thao tác và gửi lại tệp JSON.

Mở trang duyệt, chọn **Phố Huế – Hàng Bài**, rồi lần lượt 2023/2024/2025. Mỗi năm có 12 ảnh.
Vẽ bbox của biển nhận ra đúng mã; chọn **Chưa rõ** nếu không chắc. Không lấy dự đoán model làm nhãn.
Xuất JSON rồi nhập bằng `python -m survey import-review --file <đường-dẫn-json>`.

Bộ chấm `python -m survey evaluate-poc` chỉ chạy khi có bbox đã duyệt và quyết định ánh xạ nhãn đầu ra detector.
Mỗi quyết định trong `config/survey-class-candidates.yaml` có dạng sau; chỉ điền sau khi người duyệt kiểm bằng chứng:

```yaml
poc_mapping_decisions:
  - original_label: P-102
    action: map
    qcvn: P.102
    review_status: human_confirmed
    evidence_note: Ghi tệp crop hoặc ảnh đã đối chiếu thực tế.
```

Nhãn chắc chắn ngoài phạm vi chấm dùng `action: exclude` với bằng chứng. Nhãn lẫn chưa rõ không được tự exclude.
Phải có quyết định cho toàn bộ nhãn đầu ra; phạm vi chấm là các mã được map.
Đây là ánh xạ cho PoC, chưa thay danh mục lớp chính thức hoặc quyết định cuối về dataset train.

Kết quả xuất precision/recall theo lớp, năm và recall theo cạnh ngắn bbox gán tay: <32 px, 32–<96 px và ≥96 px.
Khớp một–một theo cùng lớp và IoU ≥0,50. Đây là phép chấm PoC đã định nghĩa, không phải mAP COCO.
Ảnh chưa rõ không tham gia mẫu số; báo rõ số ảnh đã duyệt so với toàn mẫu.
Ảnh thiếu dự đoán là lỗi dữ liệu, không tự coi detector trả 0 bbox.

Nếu thiếu nhãn, `poc-evaluation.json` ghi `not_run`, `metrics_valid: false`, recall rỗng và không công nhận CSV cũ.
Không dùng kết quả PoC này để bật B3 hoặc bằng chứng âm.

## Trạng thái cổng

Chưa có bbox người duyệt được nhập. Chưa chốt tuyến/lớp, chưa bắt đầu Giai đoạn 1 và chưa train.
Phần còn cần người dùng là duyệt nhãn độc lập và duyệt bảng tuyến/lớp sau khi có bằng chứng đủ.
