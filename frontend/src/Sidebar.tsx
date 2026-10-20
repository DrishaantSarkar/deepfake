import React from "react";
import { useWorkspace, ViewType } from "./context/WorkspaceContext";

export default function Sidebar() {
  const { currentView, setCurrentView } = useWorkspace();

  const navItems: { view: ViewType; icon: string; label: string }[] = [
    { view: "dashboard", icon: "◫", label: "Overview" },
    { view: "new", icon: "＋", label: "New analysis" },
    { view: "history", icon: "▤", label: "Investigations" },
    { view: "system", icon: "⌁", label: "System status" },
  ];

  return (
    <aside className="sidebar" aria-label="Investigation sidebar">
      <a
        className="brand"
        href="#dashboard"
        aria-label="TRUSTLENS home"
        onClick={(e) => {
          e.preventDefault();
          setCurrentView("dashboard");
        }}
      >
        <span className="brand-mark" aria-hidden="true">
          T
        </span>
        <span>
          <strong>TRUSTLENS</strong>
          <small>LOCAL FORENSICS</small>
        </span>
      </a>
      <div className="workspace-label">WORKSPACE</div>
      <nav className="nav-list" aria-label="Primary navigation">
        {navItems.map((item) => {
          const isActive =
            currentView === item.view || (item.view === "history" && currentView === "detail");
          return (
            <button
              key={item.view}
              type="button"
              className={`nav-item ${isActive ? "active" : ""}`}
              data-view={item.view}
              aria-current={isActive ? "page" : undefined}
              onClick={() => setCurrentView(item.view)}
            >
              <span className="nav-icon">{item.icon}</span>
              {item.label}
            </button>
          );
        })}
      </nav>
      <div className="sidebar-spacer" />
      <div className="local-notice enclave-status">
        <span className="status-dot" />
        <div>
          <strong>LOCAL WORKSPACE</strong>
          <small>Single-user · loopback bound</small>
        </div>
      </div>
      <div className="sidebar-footer">
        AI-assisted decision support
        <br />
        Human investigator retains final judgment.
      </div>
    </aside>
  );
}
