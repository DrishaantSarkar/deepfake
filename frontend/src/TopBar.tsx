import React from "react";
import { useWorkspace } from "./context/WorkspaceContext";

const viewTitles: Record<string, string> = {
  dashboard: "Overview",
  new: "New analysis",
  history: "Investigations",
  detail: "Investigation",
  system: "System status",
};

export default function TopBar() {
  const { currentView, setCurrentView } = useWorkspace();

  return (
    <header className="topbar">
      <div className="breadcrumb">
        <span>TRUSTLENS</span>
        <span className="crumb-sep">/</span>
        <strong>{viewTitles[currentView] || "Overview"}</strong>
      </div>
      <div className="topbar-right">
        <span className="local-pill">
          <span className="status-dot" />
          LOCAL ONLY
        </span>
        <button
          type="button"
          className="button button-primary topbar-cta"
          data-go="new"
          onClick={() => setCurrentView("new")}
        >
          <span aria-hidden="true">＋</span> New analysis
        </button>
        <button type="button" className="avatar" aria-label="Local single-user workspace">
          L
        </button>
      </div>
    </header>
  );
}
