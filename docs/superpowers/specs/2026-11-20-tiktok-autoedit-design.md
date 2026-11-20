# tiktok-autoedit — Thiết kế

Ngày: 2026-11-20 · Trạng thái: chờ duyệt

## 1. Sản phẩm

Web app **tự động dựng clip bán hàng TikTok** cho shop **thời trang và mỹ phẩm** Việt Nam.

- Shop tạo **preset** một lần (phong cách dựng của shop), upload **nhiều clip ngắn quay bằng điện thoại**, AI dựng hàng loạt theo preset.
- Mỗi clip trả về 3 file: `final.mp4` (đăng được ngay), `clean.mp4` (đã cắt + chỉnh màu, chưa có chữ/logo/CTA), `captions.srt`.
- **Không có trình sửa trên web.** Muốn chỉnh thêm, khách dùng CapCut với bản sạch + SRT. Web chỉ có nút "Làm lại" kèm ghi chú cho AI.
- Khách mục tiêu đã biết dựng; sản phẩm bán **thời gian**: bỏ phần thao tác lặp lại (cắt, phụ đề, màu, logo, CTA).

Bối cảnh: chưa có khách; một người phát triển bán thời gian cùng Claude Code. Dự án độc lập, không dùng lại code AIEV (chỉ dùng lại kinh nghiệm từ skill `edit-video`/video-use).

### Ngoài phạm vi bản đầu (v1)

Thanh toán · nhiều người dùng chung một shop · đăng thẳng lên TikTok · tách livestream thành clip · đọc preset từ clip mẫu · xuất project CapCut · trình sửa trên web · GPU cloud.

## 2. Kiến trúc

```
Web (Next.js, cloud) ──ghi job──▶ Postgres (Supabase) ◀──kéo job── Worker (Python)
        │                                                           │
        └──link upload/tải trực tiếp──▶ Kho file (Cloudflare R2) ◀──┘
```

| Khối | Trách nhiệm | Không làm |
|---|---|---|
| **Engine** (thư viện Python + CLI) | clip + preset → 3 file + `edit.json` | Không biết web, DB, kho file |
| **Worker** (Python) | Kéo job, tải clip, gọi engine, upload kết quả, cập nhật trạng thái | Không chứa logic dựng |
| **Web** (Next.js + TypeScript) | Đăng nhập, preset, upload, theo dõi, xem, tải | Không xử lý video |

Công nghệ: Python 3.12, ffmpeg (libass), mlx-whisper (Mac) / faster-whisper (Linux GPU) sau một interface chung, Anthropic SDK (structured output); Next.js; Supabase (Postgres + Auth + Realtime); Cloudflare R2.

**Triển khai v1:** web + DB + kho file trên cloud; **worker chạy trên Mac của chủ dự án**, kéo job ra ngoài (không cần mở cổng). Thêm worker GPU cloud sau mà không sửa code.

Cấu trúc repo:
```
tiktok-autoedit/
├── engine/      # package Python: autoedit_engine + CLI `autoedit`
├── worker/      # package Python: vòng lặp kéo job
├── web/         # Next.js
├── schema/      # preset.schema.json, edit.schema.json — dùng chung cho web & engine
└── testdata/    # bộ clip chuẩn (không commit video, chỉ manifest + script tải)
```

## 3. Engine

CLI: `autoedit run <clip> --preset <preset.json> [--note "<ghi chú>"] --out <dir>`
`autoedit preview --preset <preset.json> --out frame.png` (khung xem trước preset).

### Các bước

| # | Bước | Thực hiện bằng | Ghi chú |
|---|---|---|---|
| 1 | Chuẩn hóa | ffmpeg | Xoay theo metadata; HDR/HLG → SDR bt709 (zscale+tonemap); fps biến thiên → 30 CFR; ngang → 9:16 (cắt giữa, nền mờ trên/dưới). Không upscale. |
| 2 | Nhận dạng giọng | Whisper large-v3-turbo | Transcript từng từ; lọc câu bịa (chuỗi từ độ dài 0, câu kết kiểu "Cảm ơn các bạn đã theo dõi"); cache theo hash file. |
| 3 | Ra quyết định | Claude, 1 lượt | Vào: transcript gom cụm (ngắt khi lặng ≥0.5s) + preset + ghi chú. Ra: JSON theo `edit.schema.json`. |
| 4 | Kiểm tra quyết định | code | Bám mọi mốc về ranh giới từ; đệm 50ms trước / 80ms sau (tùy nhịp cắt); bỏ đoạn <0.4s; tổng giữ lại phải ≥30% thời lượng có lời. |
| 5 | Bản sạch | ffmpeg | Mỗi đoạn: cắt + look + afade 30ms hai đầu → nối `-c copy`. libx264 CRF 16. |
| 6 | Bản hoàn chỉnh | ffmpeg | Overlay theo thứ tự: chữ hook → logo → CTA cuối → **phụ đề cuối cùng**; nhạc (nếu có) hạ khi có lời (sidechain); loudnorm -14 LUFS, true peak -1 dB. CRF 20. SRT tính theo mốc giờ đầu ra. |
| 7 | QC tự động | ffprobe/ffmpeg | Độ dài khớp EDL ±0.1s; loudness -14±1 LUFS; không khung đen >0.5s; phụ đề nằm trong vùng an toàn. |

### Đầu ra của Claude (`edit.schema.json`)

```json
{
  "keep":   [{"start": 4.12, "end": 9.80, "reason": "take 2 tốt hơn take 1"}],
  "hook":   {"move_to_front": [12.4, 15.1], "text": "CHÂN NGẮN? XEM NGAY"},
  "caption_fixes": [{"at": 18.2, "wrong": "tuyết mưu", "right": "tuyết mưa"}],
  "emphasis": [{"at": 21.0, "word": "189K"}],
  "cta_text": "BẤM GIỎ HÀNG 👇",
  "summary": ["Bỏ 14s khoảng lặng, 2 câu vấp", "Dùng take 2 phần giá"]
}
```
`hook` có thể `null`. `summary` hiện ở màn kết quả. Chữ hook tối đa 5 từ. Prompt cấm hứa hẹn quá đà (giảm cân, cao thêm X cm, trị mụn…).

`edit.json` = đầu ra Claude **sau khi** bước 4 chỉnh + preset đã chụp + phiên bản engine + chi phí (token, giây từng bước).

### Look theo ngành

| | Thời trang | Mỹ phẩm |
|---|---|---|
| Làm sáng (chỉ kênh luma) | nhẹ/vừa | nhẹ/vừa |
| Giữ màu sản phẩm | có | có, nghiêm ngặt (không đổi hue/saturation) |
| Kéo chân 0–8% | tùy chọn | không có |
| Mịn da | tùy chọn | **không có** (tránh thổi phồng hiệu quả sản phẩm) |

### Làm lại

Dùng lại transcript cache, chạy lại từ bước 3 với ghi chú mới.

### Trường hợp khó

| Tình huống | Xử lý |
|---|---|
| Không có lời | Bỏ bước 3, không phụ đề/hook; chỉ look + CTA; `summary` ghi rõ |
| >3 phút hoặc file hỏng | Web từ chối khi upload (worker kiểm tra lại) |
| JSON Claude sai schema / vô lý (vi phạm bước 4) | Hỏi lại 1 lần kèm lỗi; vẫn sai → dự phòng: chỉ cắt lặng ≥0.6s theo luật, không hook |
| QC không đạt | Chạy lại 1 lần; vẫn không đạt → trạng thái `done` + cờ `needs_review` |

## 4. Preset (`preset.schema.json`, có `version`)

| Nhóm | Trường | Mặc định |
|---|---|---|
| Ngành | `niche`: `fashion` \| `cosmetics` | bắt buộc |
| Nhịp cắt | `pace`: `tight` \| `medium` \| `natural` | `medium` |
| Hook | `hook.reorder`: bool · `hook.text`: bool | true · true |
| Phụ đề | `captions.style`: 1 trong 5 kiểu dựng sẵn · `captions.karaoke`: bool · `captions.enabled`: bool | kiểu 1 · false · true |
| Look | `look.brightness`: `light` \| `medium` · `look.skin`: bool (chỉ fashion) · `look.leg`: 0–8 (chỉ fashion) | `light` · true · 0 |
| Thương hiệu | `brand.logo`: file \| null · `brand.logo_corner` · `brand.cta_text` · `brand.cta_seconds` | null · `top-left` · "Bấm giỏ hàng 👇" · 2 |
| Nhạc | `music`: null \| file của khách | null |

- Kiểu phụ đề và font chỉ chọn từ danh sách dựng sẵn (font đã kiểm tra hiển thị đủ dấu tiếng Việt).
- Phụ đề/logo tự tránh vùng giao diện TikTok (cột nút bên phải, dải caption dưới đáy).
- Job chụp lại preset lúc tạo; sửa preset không ảnh hưởng job cũ.

## 5. Web

Ưu tiên điện thoại. 5 màn:

1. **Đăng nhập**: Google hoặc magic link email. Tài khoản mới có **10 phút video** dùng thử.
2. **Preset**: danh sách + form; nút "Xem trước" → job `preview` → ảnh do engine render.
3. **Upload**: chọn preset, chọn nhiều clip, ghi chú từng clip (tùy chọn); upload thẳng lên R2 (multipart, nối tiếp được); "Dựng tất cả" tạo job.
4. **Danh sách clip**: trạng thái trực tiếp (Supabase Realtime). Email khi cả lô xong.
5. **Kết quả**: video final, `summary`, tải 3 file, tải zip cả lô, "Làm lại" + ghi chú.

### Dữ liệu (Postgres)

- `shops(id, owner_user_id, quota_seconds_left, created_at)`
- `presets(id, shop_id, name, data jsonb, created_at, updated_at)`
- `batches(id, shop_id, created_at)`
- `jobs(id, batch_id, shop_id, kind: edit|preview, input_key, note, preset_snapshot jsonb, parent_job_id, status, step, progress, attempts, lease_owner, lease_expires_at, result_keys jsonb, edit_json jsonb, needs_review, error, cost jsonb, created_at, finished_at)`

Vòng đời: `queued → claimed → processing → done | failed`. Worker nhận job bằng `UPDATE … WHERE status='queued' … FOR UPDATE SKIP LOCKED`; gia hạn lease mỗi 30s; lease hết hạn 2 phút → job về `queued`. Tối đa 3 lần chạy, rồi `failed` với lỗi đọc được. **Chỉ trừ hạn mức khi job `edit` `done`**, theo thời lượng clip gốc; job `preview` và lần "Làm lại" không trừ. Row-level security: shop chỉ thấy dữ liệu của mình. File trên R2 tự xóa sau 7 ngày.

## 6. Kiểm thử

- **Bộ clip chuẩn** ~20 clip thật (thời trang + mỹ phẩm; ồn, HDR iPhone, quay ngang, nói vấp, không lời). Script chạy cả bộ → bảng ảnh tổng hợp + bảng QC; xem bằng mắt mỗi lần sửa engine.
- **Unit test** (pytest): bám ranh giới từ, đệm, kiểm tra quyết định bước 4, mốc giờ SRT sau khi nối, lọc câu bịa, chọn kiểu dự phòng.
- **Contract test**: các phản hồi Claude mẫu (đúng, sai schema, vô lý) qua bước 4.
- **Worker**: test lease hết hạn, thử lại, trừ hạn mức đúng một lần.
- Ghi chi phí mỗi job để định giá.

## 7. Mốc

| Mốc | Thời lượng | Nội dung | Kết quả dùng được |
|---|---|---|---|
| M1 | 2 tuần | Engine CLI bước 1, 2, 5, 6 (không AI; giữ toàn bộ clip), look, phụ đề theo preset, `preview` | Tự dựng clip mẫu |
| M2 | 2 tuần | Bước 3, 4, 7; hook, CTA, 3 đầu ra, `edit.json`; bộ clip chuẩn | Clip trước/sau để chào hàng |
| M3 | 2 tuần | Web: đăng nhập, preset, upload R2, bảng job; worker trên Mac | Tự dùng qua web |
| M4 | 1–2 tuần | Màn kết quả, làm lại, email, hạn mức, xem trước preset | Mở bản thử cho shop |
| M5 | tùy | Sửa theo phản hồi người dùng đầu tiên | |

Sau v1: dự án con 3 (thanh toán PayOS/VNPay), dự án con 4 (worker GPU cloud), livestream → clip, đọc preset từ clip mẫu.

## 8. Rủi ro

| Rủi ro | Giảm thiểu |
|---|---|
| Whisper sai tiếng Việt (tên sản phẩm, tiếng lóng) | `caption_fixes` từ Claude + ghi chú của shop làm ngữ cảnh |
| Chi phí AI/clip vượt giá bán | Ghi chi phí từng job từ M2; 1 lượt Claude/clip |
| Mac ngủ / mất mạng làm job treo | Lease 2 phút, job tự về hàng đợi |
| Khách không thấy khác CapCut auto-cut | Demo trước/sau từ M2, trước khi xây web |
