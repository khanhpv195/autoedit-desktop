---
name: reference-edits
description: Video mẫu - edits the shop owner approved as "đúng ý". Copy their pattern when the clips have the same shape (one silent clip of the product on the model + one clip of the model talking).
---

# Video mẫu (reference edits the customer approved)

These are real edits the shop owner said are what they want. When the new clips have the same shape, follow
the same pattern unless the customer asks for something else. Never copy their words, prices or facts into a
different product: copy the **structure**.

## Mẫu 1: "Clip-chuan" — 1 clip không lời + 1 clip người mẫu nói (thời trang, 60 s)

Input:
- Clip 1 (0–44.2 s): no speech. The model stands, turns, shows the back and poses in the product (legging).
- Clip 2 (44.2–112.2 s): the same model talks about the product, speech 44.4–111.6 s (~67 s).
- Customer said: "clip 1 tắt tiếng gốc, lồng tiếng của clip 2, nối clip 2 vào, cắt 2 clip ở những chỗ cho phù
  hợp, để có 60s". Output: 60.1 s.

The formula:

| | What was done |
|---|---|
| Base picture | Clip 2 (the talking model), lip-synced to its own sound, from start to end |
| Sound | Clip 2 only; clip 1 muted (`"mute": [1]`), music off (the speech carries it) |
| Hook | The strongest buyer-problem line, moved to the very front: "chân vòng kiềng, đùi ếch" (69.9–71.9 s) |
| Hook text | "Chân vòng kiềng vẫn đẹp" (≤5 words, faithful), `position: "middle"`, never on the face |
| Order | After the hook: the speech in the speaker's own order from her first line (44.3 s) |
| Cuts | Only filler / side lines: "Mỗi một bản mỗi một dáng" (53.5 s), "Nếu chị yêu nào chưa mua đồ… vào trang cá nhân" (~100 s) |
| Kept | Every product fact: product name (quần Legging quốc dân), the body worry, 3 colours, size S M L XL, 2 lengths 90/100, free ship, "Ấn luôn vào nút mua", "Giá tiền ngon bổ rẻ hợp lý", closing "Em mời cả nhà" |
| Clip 1 | Used as video cutaways over clip 2's speech (picture only): 6 cutaways of 2.5–3.5 s, one every ~8–10 s, first one ~1 s after the hook, the last one near the closing line. Back view / full-body pose when she talks about legs, fit, colour, size |
| Captions | Fixed misheard words: "Linh góc trán" → "link góc trái", "kèm mắt" → "kèm mã", "Tùy tục" → "Tùy thuộc"; emphasis on "Legging" and "free" |
| End | Her last spoken line, CTA "BẤM GIỎ HÀNG 👇" over the last 3.5 s |

The EDL (timeline seconds):

```json
{
  "keep": [
    {"start": 69.9, "end": 71.913, "reason": "hook: chân vòng kiềng, đùi ếch"},
    {"start": 44.3, "end": 53.2},
    {"start": 57.667, "end": 69.9},
    {"start": 71.913, "end": 98.053},
    {"start": 101.6, "end": 111.7}
  ],
  "hook": {"text": "Chân vòng kiềng vẫn đẹp", "position": "middle"},
  "broll": [
    {"shot": 26.5, "at": 44.787, "dur": 3.5},
    {"shot": 12.0, "at": 64.3, "dur": 2.5},
    {"shot": 20.0, "at": 87.3, "dur": 2.5},
    {"shot": 36.0, "at": 92.5, "dur": 2.5},
    {"shot": 5.0, "at": 104.0, "dur": 3.0},
    {"shot": 40.0, "at": 108.2, "dur": 2.5}
  ],
  "caption_fixes": [
    {"at": 92.29, "wrong": "Linh góc trán", "right": "link góc trái"},
    {"at": 93.09, "wrong": "kèm mắt", "right": "kèm mã"},
    {"at": 84.95, "wrong": "Tùy tục", "right": "Tùy thuộc"}
  ],
  "emphasis": [{"at": 59.49, "word": "Legging"}, {"at": 93.77, "word": "free"}],
  "mute": [1],
  "music": {"use": false},
  "cta_text": "BẤM GIỎ HÀNG 👇"
}
```

Why it works: the face and voice stay in sync (trust), the first 2 s name the buyer's worry, the silent clip
shows the product on the body exactly while she talks about it, and nothing a buyer needs (colours, sizes,
price, free ship, how to buy) is cut.

### How to apply it to new clips of the same shape

1. Base = the talking clip, its picture in `keep` ranges at the same seconds as its words (lip sync).
2. Hook = the strongest buyer problem or benefit said anywhere (body worry, price, free ship), moved to the
   front (first `keep` range or `hook.move_to_front`); then the speaker's order.
3. Cut only filler, repeats and side remarks ("vào trang cá nhân", "mỗi bản mỗi dáng"); keep every fact,
   the price and the spoken CTA. Fit the target length by cutting more filler, never facts.
4. Silent clip = `broll` cutaways (`shot` = where the shot starts, `at` = the words it covers), 2.5–3.5 s,
   every ~8–10 s, not in the first 2.5 s, picked from clear steady shots (back view, full body, turn).
5. `mute` the silent clip; end on the last spoken line; CTA over the last 3.5 s.
