export type Niche = { id: string; label: string; emoji: string; hint: string };
export const NICHES: Niche[] = [
  { id: "thoi-trang", label: "Thời trang", emoji: "👗", hint: "Quần áo, phối đồ, lên outfit" },
  { id: "my-pham", label: "Mỹ phẩm", emoji: "💄", hint: "Son, kem, skincare, trang điểm" },
  { id: "do-an", label: "Đồ ăn", emoji: "🍜", hint: "Món ăn, đồ uống, review quán" },
  { id: "phu-kien", label: "Phụ kiện", emoji: "👜", hint: "Túi, trang sức, đồng hồ" },
  { id: "chung", label: "Khác", emoji: "✨", hint: "Sản phẩm khác, không thuộc nhóm trên" },
];
