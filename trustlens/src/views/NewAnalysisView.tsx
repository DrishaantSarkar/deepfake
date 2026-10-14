import React, { useState, useRef, useEffect } from "react";
import { useWorkspace } from "../context/WorkspaceContext";
import { api } from "../services/api";

const ALLOWED_EXTENSIONS = [
  ".jpg",
  ".jpeg",
  ".png",
  ".webp",
  ".mp4",
  ".mov",
  ".avi",
  ".wav",
  ".mp3",
];
const MAX_FILE_BYTES = 100 * 1024 * 1024; // 100 MiB

export default function NewAnalysisView() {
  const { openAnalysis, refreshStats, showToast } = useWorkspace();

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [consentChecked, setConsentChecked] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  const handleFile = (file: File | undefined | null) => {
    if (!file) return;

    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
    }
    setErrorMessage(null);

    const ext = "." + (file.name.split(".").pop() || "").toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      setErrorMessage("Choose a supported image, video, WAV, or MP3 file.");
      setSelectedFile(null);
      return;
    }

    if (file.size > MAX_FILE_BYTES) {
      setErrorMessage("The file exceeds the 100 MiB limit.");
      setSelectedFile(null);
      return;
    }

    setSelectedFile(file);

    if (file.type.startsWith("image/") || file.type.startsWith("video/")) {
      const url = URL.createObjectURL(file);
      setPreviewUrl(url);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (uploading) return;
    const file = e.dataTransfer.files?.[0];
    handleFile(file);
  };

  const handleSubmit = async () => {
    if (!selectedFile || !consentChecked || uploading) return;

    try {
      setUploading(true);
      setErrorMessage(null);

      const record = await api.submitAnalysis(selectedFile);
      showToast("Report saved to this local workspace.");
      await refreshStats();
      openAnalysis(record.analysis_id);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : "Analysis submission failed.");
    } finally {
      setUploading(false);
    }
  };

  const formatBytes = (bytes: number) => {
    let n = bytes;
    const units = ["B", "KiB", "MiB", "GiB"];
    let i = 0;
    while (n >= 1024 && i < units.length - 1) {
      n /= 1024;
      i++;
    }
    return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
  };

  return (
    <section id="view-new" className="view active" aria-labelledby="new-heading">
      <div className="page-heading">
        <div>
          <div className="eyebrow">MEDIA INTAKE</div>
          <h1 id="new-heading">New analysis</h1>
          <p className="muted">
            Submit one supported image or video for the local processing pipeline. WAV/MP3 can be
            recorded, but audio analysis is unavailable.
          </p>
        </div>
      </div>

      <div className="upload-layout">
        <div className="panel upload-panel">
          <div className="panel-heading">
            <div>
              <span className="step-kicker">01 / SOURCE MEDIA</span>
              <h2>Select evidence</h2>
            </div>
            <span className="panel-icon">↥</span>
          </div>

          <label
            id="drop-zone"
            className={`drop-zone ${isDragging ? "dragging" : ""}`}
            htmlFor="media-file-input"
            tabIndex={0}
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={(e) => {
              e.preventDefault();
              setIsDragging(false);
            }}
            onDrop={handleDrop}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                fileInputRef.current?.click();
              }
            }}
          >
            <span className="upload-glyph" aria-hidden="true">
              ↑
            </span>
            <strong>
              Drop a file here or <span>browse</span>
            </strong>
            <small>JPG, JPEG, PNG, WEBP · MP4, MOV, AVI · up to 100 MiB</small>
            <input
              id="media-file-input"
              ref={fileInputRef}
              type="file"
              accept=".jpg,.jpeg,.png,.webp,.mp4,.mov,.avi,.wav,.mp3"
              hidden
              disabled={uploading}
              onChange={(e) => handleFile(e.target.files?.[0])}
            />
          </label>

          {errorMessage && (
            <div className="field-error mt-3 text-sm text-[#FF4D4D]" role="alert">
              {errorMessage}
            </div>
          )}

          {selectedFile && (
            <div className="selected-file mt-3 text-xs text-[#00F0FF]">
              {selectedFile.name} · {formatBytes(selectedFile.size)}
            </div>
          )}

          {previewUrl && (
            <div className="preview mt-3 max-h-56 flex justify-center overflow-hidden rounded-lg bg-black/60 p-2 border border-white/10">
              {selectedFile?.type.startsWith("image/") ? (
                <img
                  src={previewUrl}
                  alt="Selected evidence preview"
                  className="max-h-52 object-contain"
                />
              ) : (
                <video
                  src={previewUrl}
                  controls
                  className="max-h-52 object-contain"
                  aria-label="Selected video preview"
                />
              )}
            </div>
          )}

          <div className="intake-note mt-4 pt-3 border-t border-white/10">
            <strong>What happens to this file?</strong>
            <p className="text-xs text-neutral-400 mt-1">
              The original is staged temporarily for analysis and deleted when processing returns.
              This app saves the report and metadata in a local SQLite database; video frame
              artifacts are not retained.
            </p>
          </div>

          <label className="consent-row flex items-start gap-2.5 my-3 text-xs text-neutral-300">
            <input
              type="checkbox"
              id="evidence-consent"
              className="mt-0.5"
              checked={consentChecked}
              disabled={uploading}
              onChange={(e) => setConsentChecked(e.target.checked)}
            />
            <span>
              I understand the local retention behavior and confirm I am authorized to submit this
              media.
            </span>
          </label>

          <button
            type="button"
            className="button button-primary button-wide w-full justify-between"
            disabled={!selectedFile || !consentChecked || uploading}
            onClick={handleSubmit}
          >
            <span>{uploading ? "Analyzing media locally…" : "Analyze media"}</span>
            <span aria-hidden="true">→</span>
          </button>

          {uploading && (
            <div
              className="upload-state mt-3 text-xs text-[#1DB954]"
              role="status"
              aria-live="polite"
            >
              Uploading and analyzing locally… Backend stage progress is tracked.
            </div>
          )}
        </div>

        <aside className="panel side-info">
          <div className="eyebrow">PROCESSING NOTES</div>
          <h2>What to expect</h2>
          <ul className="note-list">
            <li>
              <span className="note-number">01</span>
              <div>
                <strong>Validation & integrity</strong>
                <small>Content is checked and the original bytes are hashed.</small>
              </div>
            </li>
            <li>
              <span className="note-number">02</span>
              <div>
                <strong>Available analysis</strong>
                <small>Image descriptors or bounded video frame sampling may run.</small>
              </div>
            </li>
            <li>
              <span className="note-number">03</span>
              <div>
                <strong>Evidence report</strong>
                <small>Observed signals, unavailable methods and limitations are preserved.</small>
              </div>
            </li>
          </ul>

          <div className="capability-warning">
            <span>!</span>
            <p>
              <strong>Detector availability</strong>
              <br />
              No trained deepfake detector or calibrated fusion model is configured. Reports will
              abstain and require human review.
            </p>
          </div>

          <div className="audio-note">
            <strong>Audio is not analyzed</strong>
            <p>
              WAV and MP3 may be recognized by the ingestion library, but audio forensic analysis is
              deferred.
            </p>
          </div>
        </aside>
      </div>
    </section>
  );
}
