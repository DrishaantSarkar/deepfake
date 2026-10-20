import React, { useState, useRef, useEffect } from "react";
import { useWorkspace } from "../context/WorkspaceContext";
import { api } from "../services/api";
import { TestSample } from "../types/api";

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

  const [samples, setSamples] = useState<TestSample[]>([]);
  const [samplesLoading, setSamplesLoading] = useState(false);
  const [sampleFilter, setSampleFilter] = useState<"all" | "video" | "image" | "audio">("all");
  const [loadingSampleId, setLoadingSampleId] = useState<string | null>(null);
  const [detectorActive, setDetectorActive] = useState<boolean | null>(null);
  const [modelName, setModelName] = useState<string>("");

  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  useEffect(() => {
    let mounted = true;
    setSamplesLoading(true);

    api
      .getCapabilities()
      .then((caps) => {
        if (!mounted) return;
        if (caps.image?.trained_detector === "available") {
          setDetectorActive(true);
          const m = caps.image.model as { name?: string } | undefined;
          setModelName(m?.name || "ResNet-18 Frame Baseline");
        } else {
          setDetectorActive(false);
        }
      })
      .catch(() => {
        if (mounted) setDetectorActive(false);
      });

    api
      .getTestSamples()
      .then((data) => {
        if (mounted && data?.samples) {
          setSamples(data.samples);
        }
      })
      .catch((err) => {
        console.warn("Failed to load test samples:", err);
      })
      .finally(() => {
        if (mounted) setSamplesLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, []);

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

    if (
      file.type.startsWith("image/") ||
      file.type.startsWith("video/") ||
      file.type.startsWith("audio/") ||
      ext === ".mp4" ||
      ext === ".mov" ||
      ext === ".avi" ||
      ext === ".wav" ||
      ext === ".mp3"
    ) {
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

  const handleSelectSample = async (sample: TestSample) => {
    try {
      setLoadingSampleId(sample.sample_id);
      setErrorMessage(null);
      showToast(`Loading ${sample.modality} sample: ${sample.file_name}…`);

      const blob = await api.getTestSampleBlob(sample.sample_id);
      let mime = blob.type;
      if (!mime || mime === "application/octet-stream") {
        if (sample.modality === "video" || sample.file_name.endsWith(".mp4")) {
          mime = "video/mp4";
        } else if (sample.modality === "image") {
          mime = "image/jpeg";
        } else if (sample.modality === "audio") {
          mime = "audio/wav";
        }
      }

      const file = new File([blob], sample.file_name, { type: mime });
      handleFile(file);
      setConsentChecked(true);
      showToast(`Loaded ${sample.file_name}! Click "Analyze media" to evaluate.`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load test sample.";
      setErrorMessage(msg);
      showToast(`Error: ${msg}`);
    } finally {
      setLoadingSampleId(null);
    }
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

  const videos = samples.filter((s) => s.modality === "video");
  const images = samples.filter((s) => s.modality === "image");
  const audios = samples.filter((s) => s.modality === "audio");

  const renderSampleButton = (sample: TestSample) => {
    const isReal = sample.ground_truth === "real";
    const isVid = sample.modality === "video";
    const icon = sample.modality === "image" ? "🖼️" : isVid ? "🎥" : "🎙️";
    const tagText = isVid ? (isReal ? "REAL VIDEO" : "AI VIDEO") : isReal ? "REAL" : "SYNTHETIC";
    const isLoadingThis = loadingSampleId === sample.sample_id;

    return (
      <button
        key={sample.sample_id}
        type="button"
        className={`demo-sample-btn ${isVid ? "video-sample-btn" : ""}`}
        disabled={uploading || isLoadingThis}
        onClick={() => handleSelectSample(sample)}
        title={sample.description || sample.file_name}
      >
        <span className="sample-name">
          {icon} {isLoadingThis ? "Loading…" : sample.file_name}
        </span>
        <span className={`sample-tag ${isReal ? "tag-real" : "tag-synthetic"}`}>{tagText}</span>
      </button>
    );
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
              ) : selectedFile?.type.startsWith("video/") || selectedFile?.name.endsWith(".mp4") ? (
                <video
                  src={previewUrl}
                  controls
                  className="max-h-52 object-contain"
                  aria-label="Selected video preview"
                />
              ) : (
                <div className="audio-beta-banner w-full p-2">
                  <strong>AUDIO DETECTION — BETA</strong>
                  <p className="text-xs text-neutral-400 mt-1">
                    Audio detection is experimental. Results may contain false positives or false
                    negatives.
                  </p>
                  <audio controls src={previewUrl} className="mt-2 w-full" />
                </div>
              )}
            </div>
          )}

          {/* DEMO TEST SAMPLES SECTION */}
          <div className="demo-samples-section">
            <div className="demo-samples-header">
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                  flexWrap: "wrap",
                  gap: "10px",
                }}
              >
                <div>
                  <span className="step-kicker">OR CHOOSE A DEMO TEST SAMPLE</span>
                  <h3>Judge Verification Samples</h3>
                  <p>Click any verified fixture to evaluate the pipeline with real or synthetic media.</p>
                </div>
                <div className="demo-filter-tabs" id="demo-filter-tabs">
                  <button
                    type="button"
                    className={`demo-tab ${sampleFilter === "all" ? "active" : ""}`}
                    onClick={() => setSampleFilter("all")}
                  >
                    All ({samples.length})
                  </button>
                  <button
                    type="button"
                    className={`demo-tab ${sampleFilter === "video" ? "active" : ""}`}
                    onClick={() => setSampleFilter("video")}
                  >
                    🎥 Videos ({videos.length})
                  </button>
                  <button
                    type="button"
                    className={`demo-tab ${sampleFilter === "image" ? "active" : ""}`}
                    onClick={() => setSampleFilter("image")}
                  >
                    🖼️ Photos ({images.length})
                  </button>
                  <button
                    type="button"
                    className={`demo-tab ${sampleFilter === "audio" ? "active" : ""}`}
                    onClick={() => setSampleFilter("audio")}
                  >
                    🎙️ Audio ({audios.length})
                  </button>
                </div>
              </div>
            </div>

            <div id="demo-samples-grid" className="demo-samples-container">
              {samplesLoading && <span className="muted">Loading test samples…</span>}

              {!samplesLoading && samples.length === 0 && (
                <span className="muted">No test samples found in manifest.</span>
              )}

              {!samplesLoading && sampleFilter === "all" && (
                <>
                  <div className="demo-category-group">
                    <div className="demo-category-header">
                      🎥 Video Verification Samples ({videos.length}){" "}
                      <span className="badge badge-success">READY</span>
                    </div>
                    <div className="demo-samples-grid">{videos.map(renderSampleButton)}</div>
                  </div>

                  <div className="demo-category-group">
                    <div className="demo-category-header">
                      🖼️ Photographic Verification Samples ({images.length})
                    </div>
                    <div className="demo-samples-grid">{images.map(renderSampleButton)}</div>
                  </div>

                  <div className="demo-category-group">
                    <div className="demo-category-header">
                      🎙️ Audio Verification Samples ({audios.length}){" "}
                      <span className="badge badge-beta">BETA</span>
                    </div>
                    <div className="demo-samples-grid">{audios.map(renderSampleButton)}</div>
                  </div>
                </>
              )}

              {!samplesLoading && sampleFilter !== "all" && (
                <div className="demo-samples-grid">
                  {samples
                    .filter((s) => s.modality === sampleFilter)
                    .map(renderSampleButton)}
                </div>
              )}
            </div>
          </div>

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

          <div
            id="detector-status-card"
            className={detectorActive ? "capability-success" : "capability-warning"}
          >
            <span>{detectorActive ? "✓" : "!"}</span>
            <p id="detector-status-text">
              {detectorActive ? (
                <>
                  <strong>ML Model Active: {modelName || "ResNet-18 Frame Baseline"}</strong>
                  <br />
                  PyTorch deepfake classifier loaded and active for real vs. synthetic inference.
                </>
              ) : (
                <>
                  <strong>Detector status: Fallback Mode</strong>
                  <br />
                  Primary ML model weights unconfigured. Using deterministic DCT frequency
                  descriptors.
                </>
              )}
            </p>
          </div>

          <div className="audio-beta-card audio-beta-banner mt-3">
            <strong>AUDIO DETECTION — BETA</strong>
            <p>
              Audio detection is experimental. Results may contain false positives or false
              negatives and should not be treated as definitive proof of authenticity.
            </p>
          </div>
        </aside>
      </div>
    </section>
  );
}
