---
name: video-use
description: Cut craft for talking and sales clips - choosing takes, where to cut, pacing, self-checking a preview. Use before writing any EDL.
---

Adapted from browser-use/video-use (MIT, see LICENSE). Rewritten for an agent that edits through
the `set_edl` / `render_preview` tools instead of running ffmpeg.

## Principles

1. Audio is primary, visuals follow. Cut candidates come from speech boundaries and silence gaps.
   Look at frames only at decision points (opening, product shots, ambiguous takes).
2. Reason from the raw transcript. Do not tag every filler up front; decide while cutting.
3. Verify your own output before finishing. If you would not ship it, fix it.

## Cut craft

- Cut in silences. Gaps of 0.3 s or more between words are safe cut points.
- Remove: long pauses, false starts, fillers (ừm, à, ờ, kiểu là), repeated sentences, off-topic asides.
- Retakes: when a line is said twice, keep the last complete, fluent take.
- Two neighbouring lines with no gap between them are one range. Do not split them.
- Prefer fewer, longer ranges over many tiny ones. Every range under 0.4 s is dropped anyway.
- Never cut inside a word. The tool snaps and pads edges, but choose edges in gaps anyway.

## Pacing for short vertical video

- First 3 seconds decide everything: open on the strongest line or visual (the hook).
- Remove dead air aggressively, but keep a breath before the price and before the CTA.
- End on the CTA line ("giỏ hàng", "đặt ngay", "inbox"). Nothing after it.

## Self-check on preview frames

- The first frame shows the product or the speaker clearly.
- No frame looks like a flash cut or a mid-gesture jump that breaks the sentence.
- The hook text fits the moment it covers.
- The last line is the CTA.
