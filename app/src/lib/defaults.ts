export const DEFAULT_CTA = "BẤM GIỎ HÀNG 👇";
export const MAX_NAME = 80;
export const MAX_CHAT = 2000;
export const MAX_PRODUCT_INFO = 500;

/** 1–30 characters after trimming, counted like Rust `chars()` (an emoji is one). */
export const ctaValid = (s: string) => {
  const n = [...s.trim()].length;
  return n >= 1 && n <= 30;
};
