import React, { useEffect, useState } from "react";
import { useWorkspace } from "../context/WorkspaceContext";
import { api } from "../services/api";
import { AnalysisListItem } from "../types/api";

export default function DashboardView() {
  const { stats, statsLoading, refreshStats, setCurrentView, openAnalysis } = useWorkspace();
  const [recentItems, setRecentItems] = useState<AnalysisListItem[]>([]);
  const [loadingRecent, setLoadingRecent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    const fetchRecent = async () => {
      try {
        setLoadingRecent(true);
        setError(null);
        const res = await api.getAnalyses({ limit: 5 });
        if (isMounted) {
          setRecentItems(res.items);
        }
      } catch (err: unknown) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : "Failed to load recent sessions.");
        }
      } finally {
        if (isMounted) {
          setLoadingRecent(false);
        }
      }
    };

    fetchRecent();
    return () => {
      isMounted = false;
    };
  }, []);

  const total = stats ? stats.total : 0;
  const completed = stats ? stats.completed : 0;
  const partialFailed = stats ? stats.partial + stats.failed + stats.unavailable : 0;
  const humanReview = stats ? stats.human_review : 0;

  // Calculate dynamic sparkline trace based on recent reports
  const reversedRecent = [...recentItems].slice(0, 5).reverse();
  const sparklinePoints = reversedRecent.map((item, index) => {
    const x =
      reversedRecent.length === 1 ? 60 : Math.round((index * 120) / (reversedRecent.length - 1));
    const y = item.processing_status === "SUCCESS" ? 8 : 25;
    return `${x},${y}`;
  });
  const sparklineD =
    sparklinePoints.length > 0 ? `M${sparklinePoints.join(" L")}` : "M0 32 L120 32";
  const sparklineFillD =
    sparklinePoints.length > 0 ? `${sparklineD} L120 33 L0 33 Z` : "M0 32 L120 32 L120 33 L0 33 Z";

  return (
    <section id="view-dashboard" className="view active" aria-labelledby="dashboard-heading">
      <div className="page-heading">
        <div>
          <div className="eyebrow">INVESTIGATION DESK</div>
          <h1 id="dashboard-heading">Overview</h1>
          <p className="muted">A clear view of analyses processed in this local workspace.</p>
        </div>
      </div>

      {error && (
        <div className="notice notice-error mb-4" role="alert">
          {error}
          <button
            type="button"
            className="text-button ml-3 underline"
            onClick={() => {
              refreshStats();
              api.getAnalyses({ limit: 5 }).then((res) => setRecentItems(res.items));
            }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Primary CTA Pill Button */}
      <button
        type="button"
        className="bg-[#1DB954] hover:bg-[#1ED760] text-black font-extrabold rounded-full px-7 py-3 transition-all duration-200 transform hover:scale-105 active:scale-95 shadow-[0_4px_20px_rgba(29,185,84,0.3)] flex items-center gap-2 mb-6"
        onClick={() => setCurrentView("new")}
      >
        <span>+</span> New analysis
      </button>

      {/* Metrics Category Cards */}
      <div className="stat-grid" id="stats-grid" aria-live="polite">
        <article className="stat-card total-card">
          <span className="stat-label">TOTAL ANALYSES</span>
          <strong data-stat="total">{statsLoading ? "…" : total}</strong>
          <span className="stat-foot">Saved in this workspace</span>
        </article>

        <article className="stat-card completed-card">
          <span className="stat-label">COMPLETED</span>
          <strong data-stat="completed">{statsLoading ? "…" : completed}</strong>
          <svg
            id="completion-sparkline"
            className="completion-sparkline"
            viewBox="0 0 120 34"
            role="img"
            aria-label={
              reversedRecent.length === 0
                ? "Recent outcome trace unavailable until reports exist"
                : `Recent outcomes: ${reversedRecent.map((r) => r.processing_status).join(", ")}`
            }
          >
            <defs>
              <linearGradient id="completion-fill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0" stopColor="#1DB954" stopOpacity=".32" />
                <stop offset="1" stopColor="#1DB954" stopOpacity="0" />
              </linearGradient>
            </defs>
            <path className="sparkline-fill" d={sparklineFillD} />
            <path className="sparkline-line" d={sparklineD} />
          </svg>
          <span className="stat-foot">Recent outcome trace · newest at right</span>
        </article>

        <article className="stat-card warning-card">
          <span className="stat-label">PARTIAL / FAILED</span>
          <strong data-stat="partial-failed">{statsLoading ? "…" : partialFailed}</strong>
          <span className="stat-foot">Review processing details</span>
        </article>

        <article
          className={`stat-card accent-card ${humanReview > 0 ? "has-review" : ""}`}
          id="human-review-card"
        >
          <span className="stat-label">HUMAN REVIEW</span>
          <strong data-stat="human_review">{statsLoading ? "…" : humanReview}</strong>
          <span className="stat-foot">Every current report requires review</span>
        </article>
      </div>

      {/* Recent Sessions */}
      <div className="section-header mt-8">
        <div>
          <div className="eyebrow">RECENT SESSIONS</div>
          <h2>Recently analyzed</h2>
        </div>
        <button type="button" className="text-button" onClick={() => setCurrentView("history")}>
          View all <span aria-hidden="true">→</span>
        </button>
      </div>

      <div id="recent-list" className="session-grid" aria-live="polite">
        {loadingRecent ? (
          <div className="loading-row">Loading local analyses…</div>
        ) : recentItems.length === 0 ? (
          <div className="empty-state">No saved investigations match this view.</div>
        ) : (
          recentItems.map((item) => (
            <article key={item.analysis_id} className="session-tile">
              <div className="session-tile-top">
                <span className="session-type">
                  {(item.media?.media_type || "media").toUpperCase()}
                </span>
                <span
                  className={`badge ${
                    item.processing_status === "SUCCESS"
                      ? "success"
                      : ["PARTIAL", "FAILED"].includes(item.processing_status)
                        ? "warning"
                        : "unavailable"
                  }`}
                >
                  {item.processing_status}
                </span>
              </div>
              <h3 title={item.media?.filename || "Untitled upload"}>
                {item.media?.filename || "Untitled upload"}
              </h3>
              <p>
                {new Date(item.created_at).toLocaleDateString(undefined, {
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </p>
              <div className="session-tile-foot">
                <span className="mono">SHA · {(item.media?.sha256 || "").slice(0, 10)}…</span>
                <button
                  type="button"
                  className="open-report text-button text-xs"
                  onClick={() => openAnalysis(item.analysis_id)}
                >
                  Open report →
                </button>
              </div>
            </article>
          ))
        )}
      </div>

      <div className="capability-strip mt-6">
        <div className="capability-icon">i</div>
        <div>
          <strong>Evidence first, conclusions second</strong>
          <p>
            TRUSTLENS preserves observed signals and limitations. It does not produce a calibrated
            authenticity verdict; investigator review is required.
          </p>
        </div>
      </div>
    </section>
  );
}
