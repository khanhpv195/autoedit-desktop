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

## 8. Đăng bài tự động (bundle.social)

Phần này không bắt buộc. Không bật thì app vẫn dựng video bình thường.

**Bật tính năng:**
1. Vào trang bundle.social, tạo tài khoản và lấy "API key".
2. Mở app, vào Cài đặt, chọn tab "Kết nối & MCP".
3. Dán key vào ô "Dán API key bundle.social", rồi bấm "Kiểm tra". Khi hiện "✓ Đã kết nối" là xong.

**Nối kênh (TikTok, Instagram, YouTube Shorts, Facebook Reels):** trong cùng mục đó, bấm "＋ Thêm / quản lý kênh". Trang bundle.social sẽ mở ra, bạn đăng nhập từng kênh ở đó. Quay lại app, bấm "↻ Làm mới" để thấy kênh vừa nối.

**Đăng một video:** ở màn Kết quả, tìm thẻ "Đăng bài".
1. Chọn kênh muốn đăng.
2. Xem caption AI viết sẵn, sửa tùy ý (bấm "↻ Viết lại" nếu muốn caption khác).
3. Chọn một trong ba cách:
   - **Đăng ngay**: đăng liền.
   - **Chọn giờ**: tự chọn ngày giờ.
   - **Vào hàng đợi**: app xếp vào giờ routine còn trống kế tiếp, nếu chưa có routine thì xếp vào 19:30 ngày mai.
4. Bấm "Đăng". Video lớn sẽ mất một lúc để tải lên, cứ để app mở.

**Tab "Lịch đăng":** xem các bài đã lên lịch theo "Lưới tuần" hoặc "Danh sách". Bấm vào một bài để xem chi tiết, mở lại project, hoặc bấm "Thử lại" nếu bài bị lỗi.

**Routine tự động:** bấm "＋ Thêm routine", chọn giờ và kênh. Mỗi ngày app sẽ đăng video mới nhất mà bạn chưa đăng. Có nút "Chạy ngay" để lên lịch cho các ngày tới liền. Lưu ý:
- Routine chỉ chạy khi app đang mở. Mỗi lần mở app, nó lên lịch sẵn các bài cho 7 ngày tới.
- Bài đã được lên lịch thì nằm trên bundle.social, nên vẫn đăng đúng giờ kể cả khi tắt máy.

App không bao giờ xóa bài hay ngắt kênh của bạn. Muốn xóa, làm trên bundle.social.

## 9. Thêm MCP server

MCP server là công cụ bổ sung cho AI dựng video, ví dụ lấy thông tin sản phẩm hay thương hiệu của shop. Bạn không cần thêm nếu không có nhu cầu.

**Chỉ thêm server bạn tin tưởng.** MCP server chạy chương trình ngay trên máy bạn, nên một server lạ có thể làm hại máy.

**Cách thêm:** Cài đặt, tab "Kết nối & MCP", bấm "＋ Thêm MCP server". Đặt tên (chữ thường không dấu, số, dấu gạch ngang, ví dụ `kho-anh`), rồi chọn kiểu:
- **Lệnh (stdio)**: server là một chương trình chạy trên máy. Điền "Lệnh" (ví dụ `npx`) và "Tham số". Nếu server cần mật khẩu hay khóa, thêm vào mục "Biến môi trường".
- **URL (HTTP)**: server nằm trên mạng. Điền địa chỉ bắt đầu bằng http:// hoặc https://. Nếu cần khóa, thêm vào mục "Header".

Bấm "Lưu". Các khóa và mật khẩu được cất trong Keychain của máy (sau khi lưu chỉ hiện "•••• đã lưu"), không nằm trong file cấu hình.

**Kiểm tra:** bấm "Kiểm tra" cạnh server để xem server có những công cụ nào. Nếu báo lỗi, xem lại lệnh hoặc URL. Dùng công tắc để bật hoặc tắt server, "Sửa" để đổi, "Xóa" để bỏ. Tối đa 10 server.
