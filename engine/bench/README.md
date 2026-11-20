# Bộ clip chuẩn (M1)

10 clip thật, 2 clip mỗi ngành, đặt trong `engine/bench/clips/<niche>-<n>/clip.mp4` (không commit).
Phải có đủ các trường hợp sau trong cả bộ:

| Trường hợp | Ít nhất |
|---|---|
| Nói vấp / lặp câu | 3 clip |
| Ồn nền (chợ, quán) | 2 clip |
| iPhone HDR | 2 clip |
| Quay ngang | 1 clip |
| Không có lời | 1 clip |
| Có logo + nhạc | 2 clip |

Chạy: `cd engine && uv run python bench/run_bench.py` → mở `engine/bench/out/report.html`.
Chạy lại cả bộ mỗi khi sửa `agent/` hoặc engine. Tốn lượt subscription: khoảng 10 lần dựng mỗi lượt chạy.

## Kết quả

Chưa chạy — chờ bộ clip.
