// src/AppShell.tsx
import React from "react";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import InvestigationDesk from "./InvestigationDesk";
import DevControls from "./DevControls";
import Spotlight from "./Spotlight";
import { WorkspaceProvider } from "./context/WorkspaceContext";

export default function AppShell() {
  return (
    <WorkspaceProvider>
      <div className="app-shell flex">
        <Sidebar />
        <main className="main-column flex-1">
          <TopBar />
          <InvestigationDesk />
        </main>
        <DevControls />
        <Spotlight />
      </div>
    </WorkspaceProvider>
  );
}
