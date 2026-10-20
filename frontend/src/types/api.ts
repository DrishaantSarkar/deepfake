export type ProcessingStatus = "SUCCESS" | "PARTIAL" | "FAILED" | "UNAVAILABLE";

export type MediaType = "image" | "video" | "audio";

export type ProposedOutcome =
  "LIKELY_AUTHENTIC" | "AI_GENERATED" | "MANIPULATED" | "INSUFFICIENT_EVIDENCE_REVIEW";

export interface AnalysisStats {
  total: number;
  completed: number;
  partial: number;
  failed: number;
  unavailable: number;
  human_review: number;
}

export interface MediaMetadata {
  format?: string;
  width?: number;
  height?: number;
  mode?: string;
  codec?: string;
  duration_seconds?: number;
  frame_rate?: string;
  audio_stream_present?: boolean;
  exif_status?: string;
  metadata_status?: string;
  metadata_warnings?: string[];
  [key: string]: unknown;
}

export interface MediaInfo {
  filename: string;
  media_type: string;
  sha256: string;
  size_bytes: number;
  metadata?: MediaMetadata;
}

export interface AnalysisListItem {
  analysis_id: string;
  created_at: string;
  updated_at: string;
  processing_status: ProcessingStatus;
  media: MediaInfo;
  human_review_required: boolean;
}

export interface AnalysisListResponse {
  total: number;
  limit: number;
  offset: number;
  items: AnalysisListItem[];
}

export interface EvidenceChannel {
  source: string;
  method: string;
  method_version?: string;
  status: ProcessingStatus;
  measured_signal?: Record<string, unknown>;
  output_semantics?: string;
  limitations?: string[];
  description?: string;
  summary?: string;
  value?: unknown;
}

export interface ProvenanceAssessment {
  status: string;
  observed_fields?: Record<string, unknown>;
  interpretation?: string;
  reason?: string;
  exif_tag_ids?: string[];
}

export interface VideoFrameSample {
  sample_index: number;
  timestamp_seconds?: number;
  sha256: string;
  status?: string;
  artifact_reference?: string;
}

export interface EvidenceDetailResponse {
  analysis_id: string;
  processing_status: ProcessingStatus;
  evidence: EvidenceChannel[];
  frames: VideoFrameSample[];
  temporal_analysis?: Record<string, unknown>;
  provenance?: Record<string, ProvenanceAssessment>;
  fusion?: {
    summary?: string;
    decision?: string;
    proposed_outcome?: string;
    conflicts?: unknown[];
    [key: string]: unknown;
  };
  limitations: string[];
  uncertainty?: {
    calibration_status?: string;
    uncertainty_status?: string;
    reasons?: string[];
  };
}

export interface AnalysisReportEnvelope {
  schema_version: string;
  report_id: string;
  processing_status: ProcessingStatus;
  proposed_outcome: ProposedOutcome;
  human_review_required: boolean;
  source: MediaInfo & { source_id: string };
  validation: {
    status: string;
    warnings: string[];
    errors: string[];
  };
  analysis: {
    kind: string;
    status: string;
    result?: Record<string, unknown>;
  };
  fusion?: Record<string, unknown>;
  uncertainty?: Record<string, unknown>;
  limitations: string[];
  errors: string[];
}

export interface AnalysisDetailResponse {
  analysis_id: string;
  created_at: string;
  updated_at: string;
  processing_status: ProcessingStatus;
  media: MediaInfo;
  human_review_required: boolean;
  report: AnalysisReportEnvelope;
}

export interface HealthResponse {
  status: string;
  application: string;
  persistence: string;
}

export interface SubsystemStatus {
  ingestion?: string;
  frequency_descriptor?: string;
  trained_detector?: string;
  metadata?: string;
  frame_sampling?: string;
  temporal_measurement?: string;
  temporal_classifier?: string;
  metadata_inspection?: string;
  c2pa_verification?: string;
  watermark_detection?: string;
  [key: string]: unknown;
}

export interface CapabilitiesResponse {
  supported_upload_extensions: string[];
  max_upload_bytes: number;
  image: SubsystemStatus;
  video: SubsystemStatus;
  provenance: SubsystemStatus;
  fusion: string;
  audio_analysis: string;
  source_media_retention: string;
  report_persistence: string;
  authentication: string;
}

export interface ApiError {
  code: string;
  message: string;
}

export interface TestSample {
  sample_id: string;
  file_name: string;
  modality: "image" | "video" | "audio";
  ground_truth: "real" | "synthetic";
  description?: string;
  expected_outcome?: string;
  relative_path?: string;
  sha256?: string;
}

export interface TestSamplesResponse {
  schema_version: string;
  sample_count: number;
  beta_disclaimer?: string;
  samples: TestSample[];
}
