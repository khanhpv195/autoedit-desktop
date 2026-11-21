export const CLIP_EXT = ["mp4", "mov", "m4v"];
export const IMAGE_EXT = ["png", "jpg", "jpeg", "webp"];
export const MAX_CLIPS = 10;
export const MAX_IMAGES = 20;

const ext = (p: string) => p.split(".").pop()?.toLowerCase() ?? "";

export type Classified = { clips: string[]; images: string[]; ignored: string[] };

/** Sort paths into clips and images by extension, keeping order; anything else is ignored. */
export function classify(paths: string[]): Classified {
  const out: Classified = { clips: [], images: [], ignored: [] };
  for (const p of paths) {
    const e = ext(p);
    if (CLIP_EXT.includes(e)) out.clips.push(p);
    else if (IMAGE_EXT.includes(e)) out.images.push(p);
    else out.ignored.push(p);
  }
  return out;
}
