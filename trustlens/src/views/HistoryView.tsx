import React, { useState, useEffect, useCallback } from "react";
import { useWorkspace } from "../context/WorkspaceContext";
import { api } from "../services/api";
import { AnalysisListItem } from "../types/api";

const PAGE_SIZE = 20;

export default function HistoryView() {
  const { openAnalysis } = useWorkspace();

  const [items, setItems] = useState<AnalysisListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [mediaFilter, setMediaFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.getAnalyses({
        limit: PAGE_SIZE,
        offset,
        q: searchQuery.trim() || undefined,
        status: statusFilter || undefined,
        media_type: mediaFilter || undefined,
      });
      setItems(res.items);
      setTotal(res.total);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load investigations.");
    } finally {
      setLoading(false);
    }
  }, [offset, searchQuery, statusFilter, mediaFilter]);

  useEffect(() => {
    const timer = setTimeout(() => {
      loadData();
    }, 200);
    return () => clearTimeout(timer);
  }, [loadData]);

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(e.target.value);
    setOffset(0);
  };

  const handleStatusChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setStatusFilter(e.target.value);
    setOffset(0);
  };

  const handleMediaChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setMediaFilter(e.target.value);
    setOffset(0);
  };

  const statusBadge = (status: string) => {
    const klass =
      status === "SUCCESS"
        ? "success"
        : ["PARTIAL", "FAILED"].includes(status)
          ? "warning"
          : "unavailable";
    return <span className={`badge ${klass}`}>{status || "UNKNOWN"}</span>;
  };

  return (
    <section id="view-history" className="view active" aria-labelledby="history-heading">
      <div className="page-heading">
        <div>
          <div className="eyebrow">LOCAL RECORDS</div>
          <h1 id="history-heading">Investigations</h1>
          <p className="muted">Persisted report records from this local workstation.</p>
        </div>
      </div>

      <div className="filter-bar">
        <label className="search-box">
          <span aria-hidden="true">⌕</span>
          <input
            id="history-search"
            type="search"
            placeholder="Search filename or SHA-256"
            aria-label="Search investigations"
            value={searchQuery}
            onChange={handleSearchChange}
          />
        </label>

        <label className="filter-select">
          <span className="sr-only">Filter by status</span>
          <select id="status-filter" value={statusFilter} onChange={handleStatusChange}>
            <option value="">All statuses</option>
            <option value="SUCCESS">SUCCESS</option>
            <option value="PARTIAL">PARTIAL</option>
            <option value="FAILED">FAILED</option>
            <option value="UNAVAILABLE">UNAVAILABLE</option>
          </select>
        </label>

        <label className="filter-select">
          <span className="sr-only">Filter by media type</span>
          <select id="media-filter" value={mediaFilter} onChange={handleMediaChange}>
            <option value="">All media</option>
            <option value="image">Image</option>
            <option value="video">Video</option>
            <option value="audio">Audio</option>
          </select>
        </label>
      </div>

      {error && (
        <div className="notice notice-error my-3" role="alert">
          {error}
        </div>
      )}

      <div id="history-list" className="table-card mt-3" aria-live="polite">
        {loading ? (
          <div className="loading-row">Loading investigations…</div>
        ) : items.length === 0 ? (
          <div className="empty-state">No saved investigations match this view.</div>
        ) : (
          <>
            <div className="table-head">
              <span>INVESTIGATION</span>
              <span>MEDIA</span>
              <span>STATUS</span>
              <span>CREATED</span>
              <span></span>
            </div>
            {items.map((item) => (
              <div key={item.analysis_id} className="table-row">
                <div className="table-name">
                  <strong title={item.media?.filename || "Untitled upload"}>
                    {item.media?.filename || "Untitled upload"}
                  </strong>
                  <small>
                    {item.analysis_id.slice(0, 8)}… · {(item.media?.sha256 || "").slice(0, 16)}…
                  </small>
                </div>
                <div className="table-cell">{item.media?.media_type || "unknown"}</div>
                <div className="table-cell">{statusBadge(item.processing_status)}</div>
                <div className="table-cell">
                  {new Date(item.created_at).toLocaleDateString(undefined, {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </div>
                <button
                  type="button"
                  className="open-report text-button text-xs"
                  onClick={() => openAnalysis(item.analysis_id)}
                >
                  Open →
                </button>
              </div>
            ))}
          </>
        )}
      </div>

      <div className="pagination flex items-center justify-between mt-3 text-xs text-neutral-400">
        <span id="history-count">
          {total > 0
            ? `Showing ${offset + 1}–${Math.min(offset + items.length, total)} of ${total}`
            : "0 investigations"}
        </span>
        <div className="space-x-2">
          <button
            type="button"
            id="page-prev"
            className="button button-secondary"
            disabled={offset === 0 || loading}
            onClick={() => setOffset((prev) => Math.max(0, prev - PAGE_SIZE))}
          >
            Previous
          </button>
          <button
            type="button"
            id="page-next"
            className="button button-secondary"
            disabled={offset + PAGE_SIZE >= total || loading}
            onClick={() => setOffset((prev) => prev + PAGE_SIZE)}
          >
            Next
          </button>
        </div>
      </div>
    </section>
  );
}
