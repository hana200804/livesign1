# LiveSign

Nhận diện biển báo từ ảnh Mapillary tại Hà Nội. Dựng bản đồ theo năm và phát lại chuyến đi.
Sản phẩm dành cho một người vận hành. Hiện đang ở **Giai đoạn 0: khảo sát dữ liệu**.

Đã chạy khảo sát thật cho ba vùng mẫu và ba tuyến OSM tại Hoàn Kiếm.
Chưa chốt tuyến, chưa chốt danh mục lớp, chưa train model riêng.

- [Kết quả khảo sát và phần cần duyệt](docs/stage0-summary.md).
- [Bảng tuyến/lớp và bước duyệt tiếp theo](docs/stage0-review-next.md).
- [Cách đo và giới hạn của số liệu](docs/survey-plan.md).
- [Quyết định kỹ thuật](docs/decisions.md).
- [Phạm vi sản phẩm và các cổng kiểm](docs/product-scope.md).

## Chạy trên Windows

Cần Python 3.12 và Git. Điền key trên máy vào `.env`. Tệp này đã được Git bỏ qua.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-survey.txt
.\.venv\Scripts\python.exe -m survey doctor
.\.venv\Scripts\python.exe -m pytest -q --basetemp=data/cache/pytest-local
```

Nếu `ensurepip` lỗi trên máy Windows bị giới hạn:

```powershell
python -m venv --without-pip .venv
python -m pip --python .venv install -r requirements-survey.txt
```

## Khảo sát lại từ nguồn thật

Các lệnh tải dùng `.env`; không đưa key vào đối số dòng lệnh.
OSM lấy từ API chính thức. Mapillary dùng vector tile mức 14 để tránh lỗi HTTP 500 của truy vấn ảnh theo bbox.
Metadata camera và ảnh mẫu lấy riêng theo ID ảnh. Cache được dùng lại; không có ảnh mẫu trong Git.

```powershell
.\.venv\Scripts\python.exe -m survey fetch-osm --region all
.\.venv\Scripts\python.exe -m survey fetch-images --region all
.\.venv\Scripts\python.exe -m survey fetch-features --region all
.\.venv\Scripts\python.exe -m survey routes --region hoan_kiem
.\.venv\Scripts\python.exe -m survey report --region all
.\.venv\Scripts\python.exe -m survey collect-samples --per-year 12
```

Đây là ba vùng hình chữ nhật trong `config/survey.yaml`, không phải ranh giới hành chính.
Mọi năm lấy từ `captured_at`, theo UTC. Tệp báo cáo không dùng `first_seen_at` hay `last_seen_at` để suy năm ảnh.

## Kiểm dataset có giấy phép rõ

```powershell
.\.venv\Scripts\python.exe -m survey download-dataset --workspace giang-yp9g1 --project vietnam-traffic-sign-altsi --version 3
.\.venv\Scripts\python.exe -m survey audit-dataset --directory data/private/datasets/vietnam-traffic-sign-altsi-v3 --source data/private/datasets/vietnam-traffic-sign-altsi-v3/livesign-source.json --output reports/stage0/datasets/vietnam-traffic-sign-altsi-v3
```

Lệnh tải dừng nếu giấy phép chưa rõ. Lệnh kiểm đếm đọc cả `images/<split>` và `<split>/images`.
Khóa ảnh gồm ID nguồn và đường dẫn tương đối. Thiếu annotation hoặc bbox sai sẽ làm lệnh dừng.
Số object lấy từ từng dòng annotation; không lấy số ảnh trên trang giới thiệu làm số object.

## Xem ảnh và gán bbox thủ công

```powershell
.\.venv\Scripts\python.exe -m survey build-review
.\scripts\start-review.ps1
```

Mở [giao diện duyệt trên máy](http://127.0.0.1:8766/review/routes/index.html).
Chọn tuyến và năm, nhập mã QCVN đúng, kéo khung quanh từng biển đọc rõ, rồi bấm **Lưu đã duyệt**.
Ảnh chưa xác định được thì chọn **Chưa rõ**. Không lấy bbox của detector làm nhãn gán tay.
Giao diện lưu tạm trong trình duyệt. Bấm **Xuất kết quả duyệt** để giữ JSON trên máy.

Sau đó nhập tệp vừa xuất, thay đường dẫn theo nơi lưu của bạn:

```powershell
.\.venv\Scripts\python.exe -m survey import-review --file 'C:\duong-dan\livesign-manual-review.json'
```

Đây là mẫu phát triển để khảo sát chất lượng và detector có sẵn. Mẫu này không phải tập test Hà Nội độc lập.
Xác nhận ảnh rỗng trong giao diện không tạo observation `not_seen` và không bật bằng chứng âm.

Đối chiếu và chấm PoC:

```powershell
.\.venv\Scripts\python.exe -m survey candidate-report
.\.venv\Scripts\python.exe -m survey evaluate-poc
```

`candidate-report` chỉ lập bảng ưu tiên kiểm ảnh, chưa chọn tuyến/lớp.
`evaluate-poc` trả mã thoát 2 và trạng thái `not_run` nếu chưa có bbox hay ánh xạ nhãn được người duyệt xác nhận.
Không lấy nhận xét của trợ lý hoặc nhãn Mapillary làm ground truth.

## Crop và PoC detector

Phần này cần thư viện tùy chọn. CI chỉ cài `requirements-survey.txt`.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-poc.txt
.\.venv\Scripts\python.exe -m survey crop-sheets --directory data/private/datasets/vietnam-traffic-sign-altsi-v3 --report reports/stage0/datasets/vietnam-traffic-sign-altsi-v3 --output data/private/review/dataset-v3
.\.venv\Scripts\python.exe -m survey prepare-poc
.\.venv\Scripts\python.exe -m survey poc
```

PoC dùng detector ONNX có sẵn tại `liamxdev/vtsr`, revision và SHA-256 được ghi trong `reports/stage0/poc-manifest.json`.
Lệnh `prepare-poc` tải trọng số đã kiểm hash và `label-mapping.json` vào `data/private/poc-model/`.
Không commit trọng số. Chưa dùng kết quả PoC làm ground truth hay kết quả model cuối.

## Tệp đưa lên Git

Chỉ có mã nguồn, cấu hình, tài liệu và metadata nhỏ trong `reports/stage0/`.
Ảnh, dataset, cache, archive, trọng số, `.tflite`, `.env` đều ở ngoài Git.

```powershell
.\.venv\Scripts\python.exe scripts/check_repository.py
git diff --check
```

Nguồn ảnh: **© Mapillary contributors**, [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
Hình học đường: **© OpenStreetMap contributors**, [ODbL](https://www.openstreetmap.org/copyright).
Dataset ứng viên: [giang / Roboflow Universe v3](https://universe.roboflow.com/giang-yp9g1/vietnam-traffic-sign-altsi/dataset/3), khai báo CC BY 4.0.
