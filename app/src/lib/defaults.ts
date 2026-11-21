import type { VideoLength } from "./types";

export const DEFAULT_CTA = "BẤM GIỎ HÀNG 👇";
export const DEFAULT_LENGTH: VideoLength = "medium";
export const LENGTHS: [VideoLength, string][] = [["short", "Ngắn 15–20s"], ["medium", "Vừa 20–35s"], ["long", "Dài 35–60s"]];
export const MAX_PRODUCT_INFO = 500;

/** 1–30 characters after trimming, counted like Rust `chars()` (an emoji is one). */
export const ctaValid = (s: string) => {
  const n = [...s.trim()].length;
  return n >= 1 && n <= 30;
};
