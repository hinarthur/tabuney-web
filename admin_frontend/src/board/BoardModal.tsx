/** Read-only popup showing one step's board. */
import { useEffect } from "react";
import BoardView from "./BoardView";
import type { Board } from "./types";

export default function BoardModal({ board, fallbackTitle, onClose }: {
  board: Board;
  fallbackTitle?: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const title = board.title?.trim() || fallbackTitle || "";
  return (
    <div className="fc-board-backdrop" onClick={onClose}>
      <div className="fc-board-modal" role="dialog" aria-modal="true" aria-label={title || "Board"}
           onClick={(e) => e.stopPropagation()}>
        <button type="button" className="fc-board-close" aria-label="Close" onClick={onClose}>×</button>
        {title && <div className="fc-board-title">{title}</div>}
        <div className="fc-board-scroll">
          <BoardView board={board} scale={1.5} />
        </div>
      </div>
    </div>
  );
}
