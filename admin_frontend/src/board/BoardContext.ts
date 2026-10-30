import { createContext } from "react";

// Provided by every flowchart mount (editor, read-only viewer, tour). A node's
// ⊞ button calls openBoard(nodeId); the mount decides whether that opens the
// editor or the read-only popup.
export const BoardContext = createContext<{ openBoard: (nodeId: string) => void } | null>(null);
