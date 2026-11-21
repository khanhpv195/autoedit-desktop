---
name: visual-first
description: Dựng theo hình - editing clips with no usable speech (fashion, product on a model, b-roll). Use when the transcript has no speech, the speech is weak, or voiceover is on.
---

# Dựng theo hình (visual-first)

Dùng khi clip không có lời thoại, lời thoại không dùng được, hoặc bật lồng tiếng AI (tiếng gốc bị tắt). Áp dụng cùng các quy tắc trong CLAUDE.md.

Nguyên tắc chung: khi không có lời, "câu chuyện" là SẢN PHẨM trên người mẫu. Mỗi đoạn giữ lại phải trả lời được: đoạn này cho người xem thấy điều gì mới về món đồ (dáng tổng thể, phom, chi tiết, chất liệu khi chuyển động, cách phối)? Không trả lời được thì bỏ.

Trước khi viết EDL: dùng 6 keyframe có sẵn, ghi nhãn từng vùng thời gian: `[toàn thân chính diện / nửa người / cận chi tiết / quay lưng / xoay người / đi về phía máy / đi xa máy / cảnh trống / rung-mờ]`. Chỉ gọi `view_frames` (tối đa 12 khung mỗi phiên) quanh các điểm định cắt và vùng ứng viên hook, không xin rải đều lần nữa.

Thứ tự đoạn trong `keep` là thứ tự phát, và mọi thứ tự đều được: đặt cảnh mạnh nhất lên đầu, nhảy qua lại giữa các clip. Các đoạn không được chồng lên nhau (mỗi khúc hình chỉ dùng một lần).

## (1) Mở đầu 0–3s

- Hook = 1 đoạn 1,5–3s thấy RÕ sản phẩm ngay từ khung đầu: ưu tiên toàn thân chính diện hoặc 3/4, mẫu đang chuyển động (vuốt tóc, xoay người, bước tới máy). Khung đầu tiên đã phải đẹp: không bắt đầu ở khung mờ, đang lia, hay mẫu đang bước vào khung.
- Thứ tự ưu tiên: (a) khoảnh khắc chuyển động thể hiện phom đồ (xoay người làm quần ống rộng bay, vuốt tóc lộ vai lệch) > (b) chính diện đứng yên tạo dáng > (c) đi về phía máy. Tránh: quay lưng, cảnh xa thấy đồ nhỏ, cảnh trống.
- Đưa đoạn hook lên đầu bằng cách đặt nó đầu tiên trong `keep`; hook text chỉ cần `{"text": "..."}`, không cần `move_to_front`. Nếu đầu timeline đã đạt thì để nguyên (giữ mạch).
- Không lấy cảnh đắt nhất làm hook rồi lặp lại phía sau: mỗi khúc hình chỉ dùng một lần.
- Ví dụ: clip 1 cảnh chính diện vuốt tóc = hook (thấy cả áo lệch vai lẫn quần). Đừng mở bằng đoạn đi lưng về phía máy.

## (2) Độ dài đoạn và nhịp cắt

- Mỗi đoạn 1,2–3s. Toàn thân/chuyển động đẹp được tới ~3,5s; cận chi tiết 1–2s. Không đoạn nào >4s khi không có lời (người xem lướt đi). Đoạn <0,4s bộ dựng bỏ, nên đặt tối thiểu 0,8s cho an toàn.
- Nhịp: nhanh ở 0–8s (đoạn 1–2s), chậm lại giữa video (2–3s) để thấy phom, rồi nhanh lại trước CTA.
- Cắt theo hành động, không theo đồng hồ: cắt KHI chuyển động đã xong (xoay xong, bước chân chạm đất, tay rời tóc), không cắt giữa động tác.
- Hai đoạn liền nhau phải khác cỡ cảnh hoặc góc (toàn → nửa người → toàn, hoặc clip 1 → clip 2). Hai đoạn gần giống nhau đặt sát nhau = jump cut lỗi; gộp lại hoặc bỏ bớt 1.
- Tổng độ dài theo `Target length` trong yêu cầu; nguyên liệu ít thì ngắn gọn còn hơn kéo dài lặp lại.
- Bộ dựng không khớp beat nhạc, nên không hứa khớp beat; chỉ giữ độ dài đoạn đều tay để cảm giác có nhịp.

## (3) Giữ / bỏ cảnh nào

- BỎ: rung mạnh/lia nhanh, mất nét, cháy sáng/quá tối, mẫu bị che (người qua đường, cột), mẫu bị cắt đầu/chân vô lý, cảnh trống (chưa có mẫu, mẫu đã ra khỏi khung), khoảng chuẩn bị (chỉnh đồ, nhìn điện thoại, chờ hiệu lệnh), đoạn lặp động tác y hệt.
- Cắt đuôi: bỏ 0,3–0,5s đầu/cuối mỗi đoạn nếu có giật máy khi bắt đầu/dừng quay.
- QUAY LƯNG: giữ được 1 đoạn ngắn (1–2s) NẾU cho thấy thông tin mới về món đồ (dáng lưng áo, phom quần nhìn sau, độ rủ). Không đặt ở hook, không đặt ở cuối, không quá 1 đoạn liên tiếp. Đi xa khỏi máy >2s là bỏ.
- Cảnh rộng có bối cảnh (thang cuốn, TTTM): giữ 1 đoạn để tạo không khí "mặc đi chơi" nhưng mẫu phải chiếm đủ khung sau crop 9:16.
- Không dùng đoạn hình bị đứng (khung đứng yên): bản xem nhanh sẽ báo "khung đứng" nếu có.
- Nếu loại xong còn ít nguyên liệu tốt: kéo các đoạn tốt nhất lên ~3,5s, thêm b-roll, và làm video ngắn thay vì giữ cảnh lỗi.

## (4) B-roll ảnh sản phẩm khi không có lời

- Không có lời thì b-roll đóng vai "lời": chèn sau khi người xem đã thấy món đồ trên người mẫu, để xác nhận chi tiết.
- Vị trí tốt: ngay sau một cảnh toàn thân (mặc → cận ảnh sản phẩm), hoặc phủ lên đoạn yếu/hơi rung mà bạn vẫn cần thời lượng. Không phủ lên khoảnh khắc chuyển động đẹp nhất.
- Mỗi ảnh 1,5–2,5s (giới hạn của bộ dựng: 1,5–4s, tối đa 1 ảnh mỗi 3s, không trong 2,5s đầu). Giãn đều: video 20s với 3 ảnh → khoảng 4–6s, 10–12s, 15–17s. Không đặt 2 ảnh liền nhau; giữa hai ảnh phải có ít nhất 1 đoạn video thật.
- Không đặt ảnh trong 2s cuối (vùng CTA) để CTA nằm trên hình mẫu mặc đồ.
- Ảnh bị crop 9:16 mất sản phẩm (ảnh ngang, sản phẩm nằm mép) thì không dùng.
- Thứ tự ảnh nên đi theo cảnh: ảnh áo gần cảnh nửa người, ảnh quần gần cảnh toàn thân/đi lại.

## (5) Hook text ≤5 từ khi không có lời

- Chỉ viết điều nhìn thấy được trong hình hoặc có trong thông tin sản phẩm khách nhập. Không chất liệu, giá, size, form chuẩn, "bán chạy", "giảm giá", "chống nhăn"... trừ khi khách đưa thông tin đó.
- Các kiểu an toàn:
  - Gọi tên món/phối đồ đang thấy: "Áo lệch vai + quần ống rộng", "Set đen xám đi mall".
  - Theo dịp/không khí: "Outfit đi TTTM cuối tuần", "Đi chơi mặc gì?".
  - Câu hỏi/gợi tò mò: "Phối vậy được không?", "Lên đồ 30 giây".
  - Nhấn chi tiết thấy rõ: "Vai lệch siêu xinh", "Ống rộng bay bay".
- Đếm từ trước khi gửi; emoji không tính từ nhưng tối đa 1 cái. Không dùng dấu "!!!".
- Tính từ chủ quan ("xinh", "sang") chấp nhận được; khẳng định sự thật ("vải lụa", "co giãn 4 chiều", "giá 199k") thì KHÔNG nếu không có nguồn.
- Hook text phải khớp hình mở đầu (đừng ghi "Ống rộng bay bay" lên cảnh nửa người không thấy quần).

## (6) Kết video

- 2s cuối là vùng CTA: đặt đoạn toàn thân chính diện rõ đồ nhất (hoặc mẫu tạo dáng/dừng lại nhìn máy) để CTA nằm trên hình đẹp. Không kết bằng quay lưng, đi xa, cảnh trống hay mẫu bước ra khỏi khung.
- Đoạn cuối nên dài ≥2,5s để CTA không bị cắt ngang lúc đổi cảnh.
- CTA ngắn, không hứa: dùng `CTA text` trong yêu cầu. Không "Hết hàng ngay", "Chỉ hôm nay" nếu khách không nói.
- Kết dứt khoát ngay sau khoảnh khắc đẹp, không để mẫu đứng chờ.

## Tự kiểm bằng bản xem nhanh 540p (tối đa 3 lần)

- Lần 1: xem khung đầu: có thấy rõ sản phẩm? hook text khớp hình? Có jump cut / đoạn lặp? Crop 9:16 có cắt mất mẫu? Đọc dòng "Kiểm tra:" (khung đứng, tiếng bụp) nếu có và sửa.
- Lần 2: sửa xong kiểm nhịp tổng và vị trí b-roll/CTA. Lần 3 để dành cho lỗi phát sinh.
- Viết 1 dòng lý do cho mỗi đoạn keep (`reason`: "toàn thân xoay, thấy phom quần") — giúp loại đoạn thừa.

## Ví dụ áp dụng

2 clip, áo đen lệch vai + quần ống rộng xám, 3 ảnh — một EDL mẫu ~18–20s:

- Đoạn đầu trong `keep`: clip 1 vuốt tóc chính diện, `hook: {"text": "Set đen xám đi mall"}`.
- Clip 1 đi lưng: chỉ giữ 1–1,5s nếu thấy rõ phom quần nhìn sau, bỏ phần đi xa.
- Ảnh áo ~1,5–2s sau cảnh nửa người; clip 2 cạnh thang cuốn 2–3s (toàn thân, bối cảnh); ảnh quần ~2s; thêm 1–2 đoạn clip 2 tạo dáng khác góc.
- Đoạn cuối 2,5–3s: clip 2 toàn thân chính diện rõ nhất, CTA hiện trên đó. Ảnh thứ 3 chỉ dùng nếu còn chỗ mà không đặt ảnh trong 2s cuối và không đặt 2 ảnh liền nhau.
