# Duyệt ảnh bằng CVAT online

Dùng https://app.cvat.ai. Trang duyệt riêng vẫn có thể dùng với phần đã làm trước đó.
Không cần tiếp tục gán nhãn ở cả hai công cụ.

## Gói đầu tiên

Đã chuẩn bị 12 ảnh Phố Huế – Hàng Bài năm 2023, giữ nguyên JPEG từ mẫu khóa.
Thư mục trên máy: `D:\livesign\data\private\cvat\5f8f2c60e31ae0a2`.
Trong thư mục có `images.zip`, `labels.json`, `manifest.json` và `HUONG-DAN.md`.
Ảnh và ZIP chỉ nằm trên máy; không đưa lên GitHub. © Mapillary contributors.

Lệnh tạo lại hoặc chuẩn bị tuyến/năm khác:

```powershell
.\.venv\Scripts\python.exe -m survey export-cvat --route hang_bai --year 2023
```

Bỏ bộ lọc để đóng gói cả 108 ảnh. Mỗi gói có fingerprint riêng; không sửa ảnh, tên tệp hoặc manifest.
Danh sách mã trong `labels.json` là ứng viên khảo sát, chưa chốt danh mục lớp train.

## Tạo task

1. Đăng nhập CVAT online, chọn tạo task mới, đặt tên `LiveSign-HangBai-2023-khao-sat`.
2. Trong Labels → Raw, dán toàn bộ nội dung `labels.json`, bấm Done.
3. Upload `images.zip` ở phần tệp từ máy. Không đổi tên hoặc thu nhỏ ảnh trước khi upload.
4. Mở job và gán rectangle đúng mã. Đối với mã khác danh sách, dùng `QCVN_OTHER` rồi điền mã vào thuộc tính `qcvn`, ví dụ `P.103b`.

Đã duyệt ảnh nào thì gắn đúng **một tag** cho ảnh đó:

| Tag | Ý nghĩa |
|---|---|
| `LS_REVIEWED` | Đã xem toàn ảnh và gán đủ bbox biển nhận rõ; phải có ít nhất một bbox |
| `LS_EMPTY_CONFIRMED` | Đã xem toàn ảnh, thực sự không có biển; phải không có bbox |
| `LS_UNCLEAR` | Có biển mờ, bị che hoặc chưa chắc mã; ảnh không tham gia chấm ground truth |

Không có tag nghĩa là chưa duyệt, dù đã vẽ vài khung. Đánh dấu job hoàn thành không thay tag của từng ảnh.
Không dùng Auto annotation để tạo đáp án cho tập gán độc lập này.

## Xuất và nhập về LiveSign

Save trong CVAT. Xuất annotations định dạng **CVAT for images 1.1**. Không cần xuất kèm ảnh.
Gửi đường dẫn XML/ZIP tải xuống trong chat. Bộ nhập nhận cả hai dạng:

```powershell
.\.venv\Scripts\python.exe -m survey import-cvat --file "C:\Users\Han\Downloads\annotations.zip" --package "D:\livesign\data\private\cvat\5f8f2c60e31ae0a2"
```

Đường dẫn tệp tải xuống là ví dụ; dùng tên thực tế CVAT xuất ra.
Bộ nhập kiểm tên ảnh, kích thước, hash ảnh tại máy, gói nguồn, bbox và trạng thái.
Không dựa vào số frame CVAT để nhận diện ảnh. Không tự đổi bbox dự đoán thành ground truth.
XML không kèm ảnh không chứng minh được byte ảnh đã upload trên CVAT; vì vậy phải dùng đúng `images.zip` của gói.

Nhập 12 ảnh không xóa kết quả của các tuyến/năm đã nhập trước. File pending không hạ một nhãn cũ đã duyệt xuống pending.
Trước khi cập nhật, giữ bản sao nhãn cũ theo SHA-256 trong `data/private/cvat/imports`.
Chưa có nhãn CVAT thật được nhập thì PoC vẫn `not_run`, và bằng chứng âm vẫn tắt.

Tham khảo chính thức: [tạo task và Labels Raw](https://docs.cvat.ai/docs/workspace/tasks-page/),
[CVAT XML ảnh 1.1, bbox và tags](https://docs.cvat.ai/docs/dataset_management/formats/format-cvat/).
