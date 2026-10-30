import React from "react";
import { createRoot } from "react-dom/client";
import FlowchartEditor from "./FlowchartEditor";
import FlowchartTour, { type TourConfig } from "./FlowchartTour";
import "@xyflow/react/dist/style.css";
import "./editor.css";
import "./nodes.css";

declare global {
  interface Window {
    FLOWCHART_EDITOR_CONFIG: {
      reactFlowData: Record<string, unknown> | null;
      adjustedJson: Record<string, unknown> | null;
      adjustUrl: string;
      csrfToken: string;
      detail: string;
      rulebookTitle: string;
      isAdjusted: boolean;
      readOnly?: boolean;
      gameName?: string | null;
      thumbnailUrl?: string | null;
      logoUrl?: string | null;
    };
    flowchartEditorAutosave?: () => Promise<boolean>;
    FLOWCHART_VIEWER_CONFIGS?: Array<{
      mountId: string;
      reactFlowData: Record<string, unknown> | null;
      detail: string;
      rulebookTitle: string;
      isAdjusted: boolean;
      readOnly: boolean;
    }>;
    // Set by the popup window opened from the 👣 toolbar button
    FLOWCHART_TOUR_CONFIG?: TourConfig;
  }
}

const root = document.getElementById("flowchart-editor-root");
if (root) {
  createRoot(root).render(
    <React.StrictMode>
      <FlowchartEditor config={{ ...window.FLOWCHART_EDITOR_CONFIG, id: "editor" }} />
    </React.StrictMode>
  );
}

if (window.FLOWCHART_VIEWER_CONFIGS) {
  window.FLOWCHART_VIEWER_CONFIGS.forEach(cfg => {
    const el = document.getElementById(cfg.mountId);
    if (!el) return;
    createRoot(el).render(
      <React.StrictMode>
        <FlowchartEditor config={{
          id: `rf-${cfg.mountId}`,
          reactFlowData: cfg.reactFlowData,
          adjustedJson: null,
          adjustUrl: "",
          csrfToken: "",
          detail: cfg.detail,
          rulebookTitle: cfg.rulebookTitle,
          isAdjusted: cfg.isAdjusted,
          readOnly: true,
        }} />
      </React.StrictMode>
    );
  });
}

if (window.FLOWCHART_TOUR_CONFIG) {
  const tourRoot = document.getElementById("flowchart-tour-root");
  if (tourRoot) {
    createRoot(tourRoot).render(
      <React.StrictMode>
        <FlowchartTour config={window.FLOWCHART_TOUR_CONFIG} />
      </React.StrictMode>
    );
  }
}
