// src/InvestigationDesk.tsx
import React from "react";
import { useWorkspace } from "./context/WorkspaceContext";
import DashboardView from "./views/DashboardView";
import NewAnalysisView from "./views/NewAnalysisView";
import HistoryView from "./views/HistoryView";
import DetailView from "./views/DetailView";
import SystemView from "./views/SystemView";

export default function InvestigationDesk() {
  const { currentView } = useWorkspace();

  return (
    <main id="main" className="content" tabIndex={-1}>
      {currentView === "dashboard" && <DashboardView />}
      {currentView === "new" && <NewAnalysisView />}
      {currentView === "history" && <HistoryView />}
      {currentView === "detail" && <DetailView />}
      {currentView === "system" && <SystemView />}
    </main>
  );
}
