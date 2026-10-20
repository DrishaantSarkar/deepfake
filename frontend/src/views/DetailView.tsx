import React, { useState, useEffect } from "react";
import { useWorkspace } from "../context/WorkspaceContext";
import { api } from "../services/api";
import { AnalysisDetailResponse, EvidenceDetailResponse } from "../types/api";

export default function DetailView() {
  const { selectedAnalysisId, setCurrentView, refreshStats, showToast } = useWorkspace();

  const [detail, setDetail] = useState<AnalysisDetailResponse | null>(null);
  const [evidence, setEvidence] = useState<EvidenceDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!selectedAnalysisId) {
      setCurrentView("history");
      return;
    }

    let isMounted = true;
    const fetchDetail = async () => {
      try {
        setLoading(true);
        setError(null);
        const [detailData, evidenceData] = await Promise.all([
          api.getAnalysis(selectedAnalysisId),
          api.getEvidence(selectedAnalysisId),
        ]);
        if (isMounted) {
          setDetail(detailData);
          setEvidence(evidenceData);
        }
      } catch (err: unknown) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : "Failed to load investigation report.");
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    fetchDetail();
    return () => {
      isMounted = false;
    };
  }, [selectedAnalysisId, setCurrentView]);

  const handleCopySha = async (sha: string) => {
    try {
      await navigator.clipboard.writeText(sha);
      setCopied(true);
      showToast("SHA-256 copied to clipboard.");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      showToast("Failed to copy to clipboard.");
    }
  };

  const handleDelete = async () => {
    if (!selectedAnalysisId) return;
    const confirmed = window.confirm(
      "Delete this saved report from local history? This cannot be undone."
    );
    if (!confirmed) return;

    try {
      await api.deleteAnalysis(selectedAnalysisId);
      showToast("Report deleted from local history.");
      await refreshStats();
      setCurrentView("history");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to delete report.");
    }
  };

  const handleExport = () => {
    if (!selectedAnalysisId) return;
    const downloadUrl = api.getReportDownloadUrl(selectedAnalysisId);
    const a = document.createElement("a");
    a.href = downloadUrl;
    a.download = `trustlens-${selectedAnalysisId}.json`;
    a.click();
    showToast("Exporting forensic JSON report.");
  };

  if (loading) {
    return (
      <section id="view-detail" className="view active" aria-labelledby="detail-heading">
        <div className="loading-row py-12 text-center text-sm">Loading investigation dossier…</div>
      </section>
    );
  }

  if (error || !detail) {
    return (
      <section id="view-detail" className="view active" aria-labelledby="detail-heading">
        <button
          type="button"
          className="back-button mb-3 text-xs"
          onClick={() => setCurrentView("history")}
        >
          ← Investigations
        </button>
        <div className="notice notice-error" role="alert">
          {error || "Report not found."}
        </div>
      </section>
    );
  }

  const report = detail.report || {};
  const source = report.source || detail.media || {};
  const sourceHash = source.sha256 || "";
  const evChannels = evidence?.evidence || [];
  const provenance = evidence?.provenance || {};
  const frames = evidence?.frames || [];
  const fusion = evidence?.fusion || report.fusion || {};
  const limitations = [
    ...(evidence?.limitations || []),
    ...(report.limitations || []),
    ...(evidence?.uncertainty?.reasons || []),
  ];
  const uniqueLimitations = Array.from(new Set(limitations));

  return (
    <section id="view-detail" className="view active" aria-labelledby="detail-heading">
      <div className="page-heading">
        <div>
          <button
            type="button"
            className="back-button"
            data-go="history"
            onClick={() => setCurrentView("history")}
          >
            ← Investigations
          </button>
          <div className="eyebrow">ANALYSIS REPORT</div>
          <h1 id="detail-heading">{source.filename || "Investigation"}</h1>
          <p id="detail-subtitle" className="muted text-xs">
            {detail.analysis_id} ·{" "}
            {new Date(detail.created_at).toLocaleDateString(undefined, {
              dateStyle: "medium",
              timeStyle: "short",
            })}
          </p>
        </div>
        <div className="heading-actions flex gap-2">
          <button
            type="button"
            id="print-report"
            className="button button-secondary"
            onClick={() => window.print()}
          >
            Print report
          </button>
          <button
            type="button"
            id="download-report"
            className="button button-secondary"
            onClick={handleExport}
          >
            ↓ Export JSON
          </button>
          <button
            type="button"
            id="delete-analysis"
            className="button button-danger"
            onClick={handleDelete}
          >
            Delete record
          </button>
        </div>
      </div>

      <div id="detail-content" className="space-y-4">
        {/* Detail Hero Cards */}
        <div className="detail-hero">
          <article className="detail-card">
            <span>Processing status</span>
            <strong>
              {detail.processing_status}{" "}
              <span
                className={`badge ml-2 ${
                  detail.processing_status === "SUCCESS"
                    ? "success"
                    : ["PARTIAL", "FAILED"].includes(detail.processing_status)
                      ? "warning"
                      : "unavailable"
                }`}
              >
                {detail.processing_status}
              </span>
            </strong>
          </article>
          <article className="detail-card">
            <span>Assessment</span>
            <strong>{report.proposed_outcome || "Review required"}</strong>
          </article>
          <article className="detail-card">
            <span>Human review</span>
            <strong>{detail.human_review_required ? "Required" : "Not flagged"}</strong>
          </article>
        </div>

        {/* Source & Integrity */}
        <section className="detail-section">
          <h2>Source & integrity</h2>
          <div className="system-row">
            <span>Media</span>
            <span>
              {source.media_type} · {(source.size_bytes / 1024).toFixed(1)} KiB
            </span>
          </div>
          <div className="system-row">
            <span>SHA-256</span>
            <span className="mono">
              {sourceHash}{" "}
              {sourceHash && (
                <button
                  type="button"
                  className="text-button ml-2"
                  onClick={() => handleCopySha(sourceHash)}
                  aria-label="Copy source SHA-256"
                >
                  {copied ? "Copied!" : "Copy"}
                </button>
              )}
            </span>
          </div>
          <div className="system-row">
            <span>Metadata observed</span>
            <span className="max-w-xl text-right">{JSON.stringify(source.metadata || {})}</span>
          </div>
        </section>

        {/* Evidence Signals */}
        <section className="detail-section">
          <h2>Evidence signals</h2>
          {evChannels.length === 0 ? (
            <p className="text-xs text-neutral-400">
              No evidence signal was emitted for this media.
            </p>
          ) : (
            evChannels.map((item, idx) => (
              <div key={idx} className="evidence-item">
                <div className="flex items-center gap-2">
                  <strong>{item.method || item.source || "Observed signal"}</strong>
                  <span
                    className={`badge ${
                      item.status === "SUCCESS"
                        ? "success"
                        : ["PARTIAL", "FAILED"].includes(item.status)
                          ? "warning"
                          : "unavailable"
                    }`}
                  >
                    {item.status}
                  </span>
                </div>
                <p className="text-xs text-neutral-400 mt-1">
                  {item.output_semantics ||
                    item.description ||
                    JSON.stringify(item.measured_signal)}
                </p>
                {item.measured_signal && (
                  <pre className="mt-1 text-[10px] bg-black/40 p-2 rounded overflow-x-auto text-cyan-300">
                    {JSON.stringify(item.measured_signal, null, 2)}
                  </pre>
                )}
              </div>
            ))
          )}
        </section>

        {/* Metadata & Provenance Checks */}
        <section className="detail-section">
          <h2>Metadata & provenance checks</h2>
          {Object.entries(provenance).length === 0 ? (
            <p className="text-xs text-neutral-400">
              No provenance assessment is available for this report.
            </p>
          ) : (
            Object.entries(provenance).map(([name, val]) => (
              <div key={name} className="evidence-item">
                <div className="flex items-center gap-2">
                  <strong>{name.replace(/_/g, " ")}</strong>
                  {val?.status && (
                    <span
                      className={`badge ${
                        val.status === "DETECTED" || val.status === "SUCCESS"
                          ? "success"
                          : val.status === "UNAVAILABLE"
                            ? "unavailable"
                            : "warning"
                      }`}
                    >
                      {val.status}
                    </span>
                  )}
                </div>
                <p className="text-xs text-neutral-400 mt-1">
                  {val?.interpretation ||
                    val?.reason ||
                    "Parser observation only; does not verify authenticity claims."}
                </p>
                {val?.observed_fields && (
                  <pre className="mt-1 text-[10px] bg-black/40 p-2 rounded overflow-x-auto text-neutral-300">
                    {JSON.stringify(val.observed_fields, null, 2)}
                  </pre>
                )}
              </div>
            ))
          )}
        </section>

        {/* Sampled Video Frames */}
        {frames.length > 0 && (
          <section className="detail-section">
            <h2>Sampled video frames</h2>
            <ul className="list-disc pl-5 space-y-1 text-xs text-neutral-300">
              {frames.map((frame, idx) => (
                <li key={idx}>
                  Frame {frame.sample_index + 1}
                  {frame.timestamp_seconds != null && ` at ${frame.timestamp_seconds} s`}:{" "}
                  <span className="mono">SHA-256 {frame.sha256}</span> (Artifact: NOT_RETAINED)
                </li>
              ))}
            </ul>
            <p className="text-xs text-neutral-500 mt-2">
              Sampled frame artifacts are temporary and purged from local disk after analysis.
            </p>
          </section>
        )}

        {/* Evidence Fusion & Abstention */}
        <section className="detail-section">
          <h2>Evidence fusion & abstention</h2>
          <p className="text-xs text-neutral-300 mb-2">
            {String(
              fusion.summary ||
                fusion.decision ||
                "Fusion preserves available evidence and does not aggregate calibrated likelihoods."
            )}
          </p>
          <pre className="text-[10px] bg-black/50 p-3 rounded overflow-x-auto text-emerald-300">
            {JSON.stringify(fusion, null, 2)}
          </pre>
        </section>

        {/* Limitations & Uncertainty */}
        <section className="detail-section">
          <h2>Limitations & uncertainty</h2>
          {uniqueLimitations.length === 0 ? (
            <p className="text-xs text-neutral-400">
              Review the report fields and processing status. This tool does not provide a
              calibrated authenticity verdict.
            </p>
          ) : (
            <ul className="list-disc pl-5 space-y-1 text-xs text-neutral-400">
              {uniqueLimitations.map((lim, idx) => (
                <li key={idx}>{lim}</li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </section>
  );
}
