import { Gem, Package, Shirt, Sparkles, UtensilsCrossed, type LucideIcon } from "lucide-react";

export type Niche = { id: string; label: string; emoji: string; hint: string; Icon: LucideIcon; tint: [string, string] };
export const NICHES: Niche[] = [
  { id: "thoi-trang", label: "Thời trang", emoji: "👗", hint: "Quần áo, phối đồ, lên outfit", Icon: Shirt, tint: ["#fff0f3", "#e11d48"] },
  { id: "my-pham", label: "Mỹ phẩm", emoji: "💄", hint: "Son, kem, skincare, trang điểm", Icon: Sparkles, tint: ["#faf5ff", "#9333ea"] },
  { id: "do-an", label: "Đồ ăn", emoji: "🍜", hint: "Món ăn, đồ uống, review quán", Icon: UtensilsCrossed, tint: ["#fff7ed", "#ea580c"] },
  { id: "phu-kien", label: "Phụ kiện", emoji: "👜", hint: "Túi, trang sức, đồng hồ", Icon: Gem, tint: ["#ecfeff", "#0891b2"] },
  { id: "chung", label: "Khác", emoji: "✨", hint: "Sản phẩm khác, không thuộc nhóm trên", Icon: Package, tint: ["#f4f4f5", "#52525b"] },
];
