# Hướng dẫn cài AutoEdit

## 1. Máy cần có

- Mac chip Apple (M1 trở lên), macOS 12 trở lên, còn trống ít nhất 5GB.
- Hoặc Windows 10/11 64-bit, còn trống ít nhất 5GB.
- Tài khoản Claude Pro hoặc Max.

## 2. Cài app

**Mac:** mở file `.dmg`, kéo AutoEdit vào thư mục Applications.

**Windows:** chạy `AutoEdit-setup.exe`.

Nếu bản này chưa được ký, máy sẽ báo không rõ nhà phát triển. Cách mở:

- Mac: chuột phải vào AutoEdit, chọn Mở, rồi chọn Mở lần nữa.
- Windows: ở màn hình SmartScreen, bấm "Thông tin khác", rồi "Vẫn chạy".

## 3. Lần mở đầu tiên

App sẽ làm lần lượt:

1. Tải Claude, khoảng 160MB. Đợi vài phút.
2. Mở trình duyệt để bạn đăng nhập Claude. Nếu app hỏi mã, dán mã từ trình duyệt vào.
3. Tải model giọng nói, khoảng 1.5GB. Nút "Bắt đầu" chỉ sáng lên khi tải xong, nên đợi bước này. Nếu mạng đứt, bấm thử lại trên màn hình, app tải tiếp phần còn lại.

## 4. Dựng một video

1. Chọn ngành hàng.
2. Thả clip vào khung.
3. Chọn một trong ba kịch bản gợi ý, hoặc tự gõ mô tả.
4. Bấm "Dựng video" và đợi.
5. Xem video. Bấm "Mở thư mục" để lấy file. Chưa ưng thì gõ yêu cầu rồi bấm "Dựng lại".

## 5. Video nằm ở đâu

- Mac: `~/Movies/AutoEdit/`
- Windows: `Videos\AutoEdit\`

Mỗi video có một thư mục riêng, tên bắt đầu bằng ngày dựng. File kết quả là `final.mp4`.

## 6. Gặp lỗi

| Thông báo | Cách xử lý |
|---|---|
| Đã hết lượt Claude | Đợi đến giờ ghi trên màn hình, rồi thử lại. |
| Chưa đăng nhập Claude | Vào Cài đặt, chọn AI dựng, bấm Đổi tài khoản. |
| Cần tải lại Claude | Bấm nút "Tải lại Claude" ngay trong thông báo lỗi. Cần có mạng. |
| Clip quá dài | Cắt clip còn dưới 3 phút rồi thả lại. |

## 7. Cập nhật

Khi có bản mới, app hiện dải "Có bản mới" ở đầu cửa sổ. Bấm Cập nhật, app tự khởi động lại.
