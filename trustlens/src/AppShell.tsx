// src/AppShell.tsx
import React, { FormEvent, useEffect, useState } from "react";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import InvestigationDesk from "./InvestigationDesk";
import DevControls from "./DevControls";
import Spotlight from "./Spotlight";
import { WorkspaceProvider } from "./context/WorkspaceContext";
import { api } from "./services/api";

export default function AppShell() {
  const [hasSession, setHasSession] = useState(() => api.hasSession());
  const [accessKey, setAccessKey] = useState("");
  const [loginError, setLoginError] = useState("");
  const [loggingIn, setLoggingIn] = useState(false);

  useEffect(() => api.onSessionRequired(() => setHasSession(false)), []);

  const handleLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoginError("");
    setLoggingIn(true);
    try {
      await api.login(accessKey);
      setAccessKey("");
      setHasSession(true);
    } catch (error) {
      setLoginError(error instanceof Error ? error.message : "Sign-in failed.");
    } finally {
      setLoggingIn(false);
    }
  };

  const handleLogout = () => {
    api.logout();
    setHasSession(false);
  };

  if (!hasSession) {
    return (
      <main className="min-h-screen bg-[#090d12] px-5 py-12 text-slate-100 flex items-center justify-center">
        <form onSubmit={handleLogin} className="w-full max-w-md rounded-2xl border border-white/10 bg-[#111820] p-8 shadow-2xl">
          <p className="text-xs font-semibold tracking-[0.24em] text-cyan-300">TRUSTLENS · PRIVATE DEMO</p>
          <h1 className="mt-4 text-2xl font-semibold">Sign in to your workspace</h1>
          <p className="mt-2 text-sm leading-6 text-slate-400">Enter the shared access key configured for this backend. Keep it private; it protects saved analyses and uploaded files.</p>
          <label htmlFor="workspace-access-key" className="mt-6 block text-sm font-medium text-slate-200">Workspace access key</label>
          <input
            id="workspace-access-key"
            type="password"
            autoComplete="current-password"
            required
            value={accessKey}
            onChange={(event) => setAccessKey(event.target.value)}
            className="mt-2 w-full rounded-lg border border-white/15 bg-black/30 px-3 py-3 text-sm outline-none focus:border-cyan-400"
            placeholder="Enter access key"
          />
          {loginError && <p role="alert" className="mt-3 text-sm text-rose-300">{loginError}</p>}
          <button type="submit" disabled={loggingIn} className="mt-5 w-full rounded-lg bg-cyan-400 px-4 py-3 text-sm font-semibold text-slate-950 disabled:opacity-60">
            {loggingIn ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </main>
    );
  }

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
        <button type="button" onClick={handleLogout} className="fixed right-5 top-4 z-50 rounded-md border border-white/15 bg-slate-900/90 px-3 py-2 text-xs text-slate-200 hover:border-cyan-300">
          Sign out
        </button>
      </div>
    </WorkspaceProvider>
  );
}

