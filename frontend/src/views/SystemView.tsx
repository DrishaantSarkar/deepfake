// src/views/SystemView.tsx
import React, { useState, useEffect, useCallback } from "react";
import { api } from "../services/api";
import { HealthResponse, CapabilitiesResponse } from "../types/api";

function StatusBadge({ value }: { value: string | undefined }) {
  if (!value) return <span className="badge unavailable">UNKNOWN</span>;
  const upper = value.toUpperCase();
  if (upper === "AVAILABLE" || upper === "OK" || upper === "HEALTHY" || upper === "PASS") {
    return <span className="badge success">{value}</span>;
  }
  if (upper === "UNAVAILABLE" || upper === "MISSING" || upper === "FAIL") {
    return <span className="badge warning">{value}</span>;
  }
  return <span className="badge unavailable">{value}</span>;
}

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(0)} MiB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KiB`;
  return `${bytes} B`;
}

export default function SystemView() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [capabilities, setCapabilities] = useState<CapabilitiesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [h, c] = await Promise.all([api.getHealth(), api.getCapabilities()]);
      setHealth(h);
      setCapabilities(c);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load system status.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section id="view-system" className="view active" aria-labelledby="system-heading">
      <div className="page-heading">
        <div>
          <div className="eyebrow">RUNTIME</div>
          <h1 id="system-heading">System status</h1>
          <p className="muted">
            Current local processing capabilities and their honest availability.
          </p>
        </div>
        <button
          type="button"
          id="refresh-system"
          className="button button-secondary"
          onClick={load}
          disabled={loading}
        >
          {loading ? "Checking…" : "↻ Refresh checks"}
        </button>
      </div>

      {error && (
        <div className="notice notice-error mb-4" role="alert">
          {error}{" "}
          <button type="button" className="text-button underline ml-2" onClick={load}>
            Retry
          </button>
        </div>
      )}

      <div id="system-content" className="system-grid" aria-live="polite">
        {loading ? (
          <div className="loading-row">Checking local capabilities…</div>
        ) : !health && !capabilities ? (
          <div className="empty-state">System status unavailable.</div>
        ) : (
          <>
            {/* Health Card */}
            {health && (
              <article className="stat-card total-card">
                <span className="stat-label">APPLICATION HEALTH</span>
                <strong>
                  <StatusBadge value={health.status} />
                </strong>
                <span className="stat-foot">
                  {health.application} · Persistence: {health.persistence}
                </span>
              </article>
            )}

            {/* Image subsystem */}
            {capabilities && (
              <article className="stat-card completed-card">
                <span className="stat-label">IMAGE PIPELINE</span>
                <div className="space-y-1 mt-1">
                  {Object.entries(capabilities.image).map(([key, val]) => (
                    <div key={key} className="flex items-center justify-between text-xs">
                      <span className="text-neutral-400 capitalize">{key.replace(/_/g, " ")}</span>
                      <StatusBadge value={String(val)} />
                    </div>
                  ))}
                </div>
              </article>
            )}

            {/* Video subsystem */}
            {capabilities && (
              <article className="stat-card warning-card">
                <span className="stat-label">VIDEO PIPELINE</span>
                <div className="space-y-1 mt-1">
                  {Object.entries(capabilities.video).map(([key, val]) => (
                    <div key={key} className="flex items-center justify-between text-xs">
                      <span className="text-neutral-400 capitalize">{key.replace(/_/g, " ")}</span>
                      <StatusBadge value={String(val)} />
                    </div>
                  ))}
                </div>
              </article>
            )}

            {/* Upload limits + misc */}
            {capabilities && (
              <article className="stat-card accent-card">
                <span className="stat-label">UPLOAD &amp; RETENTION</span>
                <div className="space-y-1 mt-1 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-neutral-400">Max upload size</span>
                    <span className="mono">{formatBytes(capabilities.max_upload_bytes)}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-neutral-400">Accepted formats</span>
                    <span className="mono text-right" style={{ maxWidth: "55%" }}>
                      {capabilities.supported_upload_extensions.join(", ")}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-neutral-400">Source media retention</span>
                    <span>{capabilities.source_media_retention}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-neutral-400">Report persistence</span>
                    <span>{capabilities.report_persistence}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-neutral-400">Authentication</span>
                    <span>{capabilities.authentication}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-neutral-400">Audio analysis</span>
                    <StatusBadge value={capabilities.audio_analysis} />
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-neutral-400">Fusion model</span>
                    <StatusBadge value={capabilities.fusion} />
                  </div>
                </div>
              </article>
            )}
          </>
        )}
      </div>

      <div className="retention-card mt-6">
        <div className="eyebrow">EVIDENCE HANDLING</div>
        <h2>Local retention</h2>
        <p>
          Source files and sampled frame files are temporary and deleted when the analysis service
          returns. SQLite stores report JSON and extracted metadata locally under the
          operating-system user profile. Deleting a record removes that report from the local
          history.
        </p>
      </div>
    </section>
  );
}
