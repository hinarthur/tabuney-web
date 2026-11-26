/**
 * Legend 自動編號與 node 內文引用。
 *
 * - 編號：legend 節點在 nodes 陣列（= Layers 面板順序）中的次序，1 起算，不落地儲存。
 * - 引用：node 文字內寫 `{{L:<legendNodeId>}}`，顯示時換成可點擊的 `[n]`。
 *   存 id 而不是數字，legend 重排／刪除時引用不會錯。
 */
import { createContext, useContext, useEffect, useMemo, type ReactNode } from "react";
import type { Node } from "@xyflow/react";
import { ReadOnlyContext } from "./ReadOnlyContext";

const REF_SOURCE = String.raw`\{\{L:([^{}]+?)\}\}`;

export type LegendNumbers = Map<string, number>;

export function legendNumberMap(nodes: Array<Pick<Node, "id" | "type">>): LegendNumbers {
  const m: LegendNumbers = new Map();
  let i = 0;
  for (const n of nodes) {
    if (n.type === "legend") m.set(n.id, ++i);
  }
  return m;
}

export function legendRefToken(id: string): string {
  return `{{L:${id}}}`;
}

/** 純文字版：標記換成 `[n]`；找不到 legend 的標記直接拿掉。 */
export function plainLabel(text: string, numbers: LegendNumbers): string {
  if (!text || text.indexOf("{{L:") < 0) return text;
  return text.replace(new RegExp(REF_SOURCE, "g"), (_m, id: string) => {
    const n = numbers.get(id.trim());
    return n ? `[${n}]` : "";
  });
}

/** 把指向不存在 legend 的標記清掉（存檔時用）。 */
export function stripDeadRefs(text: string, liveIds: Set<string>): string {
  if (!text || text.indexOf("{{L:") < 0) return text;
  return text.replace(new RegExp(REF_SOURCE, "g"), (m, id: string) => (liveIds.has(id.trim()) ? m : ""));
}

export type LegendRefCtx = {
  numbers: LegendNumbers;
  open: (legendId: string) => void;
};

export const LegendRefContext = createContext<LegendRefCtx | null>(null);

/** node.data.legend_ids：結構化的句尾引用（有序、去重）。 */
export function legendIdsOf(data: unknown): string[] {
  const raw = (data as { legend_ids?: unknown } | undefined)?.legend_ids;
  if (!Array.isArray(raw)) return [];
  return [...new Set(raw.filter((x): x is string => typeof x === "string"))];
}

/** 純文字版的句尾引用字串，例如 " [1][3]"；給量測尺寸用。 */
export function suffixText(data: unknown, numbers: LegendNumbers, inlineText = ""): string {
  const inline = new Set([...inlineText.matchAll(new RegExp(REF_SOURCE, "g"))].map((m) => m[1].trim()));
  return legendIdsOf(data)
    .filter((id) => numbers.has(id) && !inline.has(id))
    .map((id) => `[${numbers.get(id)}]`)
    .join("");
}

function RefButton({ id, n, open }: { id: string; n: number; open?: (id: string) => void }) {
  const viewing = useContext(ReadOnlyContext);
  return (
    <button
      type="button"
      className={`fc-legend-ref nodrag nopan${viewing ? " fc-legend-ref-view" : ""}`}
      title={`Legend ${n}`}
      onClick={(e) => { e.stopPropagation(); open?.(id); }}
    >[{n}]</button>
  );
}

/**
 * 渲染 node 文字：內文的 {{L:id}} 換成可點擊的上標 [n]（句中引用），
 * 再把 data.legend_ids（句尾引用）接在後面。沒有 context 時原樣回傳文字。
 */
export function RefText({ text, ids }: { text: string; ids?: unknown }) {
  const ctx = useContext(LegendRefContext);
  const tail = legendIdsOf({ legend_ids: ids });
  if ((!text || text.indexOf("{{L:") < 0) && !tail.length) return <>{text}</>;
  const parts: ReactNode[] = [];
  const inline = new Set<string>();
  const re = new RegExp(REF_SOURCE, "g");
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  while ((m = re.exec(text ?? ""))) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const id = m[1].trim();
    inline.add(id);
    const n = ctx?.numbers.get(id);
    if (n) parts.push(<RefButton key={k++} id={id} n={n} open={ctx?.open} />);
    last = m.index + m[0].length;
  }
  if (text && last < text.length) parts.push(text.slice(last));
  for (const id of tail) {
    const n = ctx?.numbers.get(id);
    if (n && !inline.has(id)) parts.push(<RefButton key={k++} id={id} n={n} open={ctx?.open} />);
  }
  return <>{parts}</>;
}

/** 放大顯示單一 legend 的彈窗（編輯器、唯讀檢視、Tour 共用）。 */
export function LegendModal({ number, title, content, onClose }: {
  number: number;
  title: string;
  content: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const heading = useMemo(() => `[${number}] ${title}`.trim(), [number, title]);
  return (
    <div className="fc-board-backdrop" onClick={onClose}>
      <div className="fc-board-modal fc-legend-modal" role="dialog" aria-modal="true" aria-label={heading}
           onClick={(e) => e.stopPropagation()}>
        <button type="button" className="fc-board-close" aria-label="Close" onClick={onClose}>×</button>
        <div className="fc-board-title">{heading}</div>
        <div className="fc-board-scroll fc-legend-modal-text">{content}</div>
      </div>
    </div>
  );
}
