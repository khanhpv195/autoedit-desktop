import type { FeedItem } from "../lib/types";

const ICON: Record<string, string> = { set_edl: "✂️", render_preview: "👁", finish: "✅" };
export const iconFor = (tool: string | null) => (tool && ICON[tool]) || "💬";

export default function AgentFeed({ items }: { items: FeedItem[] }) {
  if (items.length === 0) return null;
  return (
    <div className="feed">
      {items.map((it, i) => (
        <div key={i} className="ev">
          <span className="i">{iconFor(it.tool)}</span>
          <div className="t">{it.text}</div>
        </div>
      ))}
    </div>
  );
}
