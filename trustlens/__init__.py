"""TRUSTLENS media-analysis package with lazy exports for dependency diagnostics."""

from importlib import import_module

_EXPORTS = {
    "IngestedMedia": ("ingestion", "IngestedMedia"),
    "MediaLimits": ("ingestion", "MediaLimits"),
    "MediaType": ("ingestion", "MediaType"),
    "ProcessingStatus": ("ingestion", "ProcessingStatus"),
    "ingest_media": ("ingestion", "ingest_media"),
    "DetectorDescriptor": ("image_analysis", "DetectorDescriptor"),
    "DetectorOutput": ("image_analysis", "DetectorOutput"),
    "ImageAssessment": ("image_analysis", "ImageAssessment"),
    "ImageDetector": ("image_analysis", "ImageDetector"),
    "analyze_image": ("image_analysis", "analyze_image"),
    "VideoAssessment": ("video_analysis", "VideoAssessment"),
    "VideoSamplingConfig": ("video_analysis", "VideoSamplingConfig"),
    "analyze_video": ("video_analysis", "analyze_video"),
    "EvidenceRecord": ("evidence_fusion", "EvidenceRecord"),
    "FusionAssessment": ("evidence_fusion", "FusionAssessment"),
    "fuse_reports": ("evidence_fusion", "fuse_reports"),
    "build_evidence_graph": ("evidence_graph", "build_evidence_graph"),
    "validate_evidence_graph": ("evidence_graph", "validate_evidence_graph"),
    "AnalysisReport": ("service", "AnalysisReport"),
    "analyze_upload": ("service", "analyze_upload"),
    "validate_analysis_report": ("service", "validate_analysis_report"),
    "PyTorchModelDetector": ("detector_adapter", "PyTorchModelDetector"),
    "load_model_detector": ("detector_adapter", "load_model_detector"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = _EXPORTS[name]
    return getattr(import_module(f".{module_name}", __name__), attribute)
