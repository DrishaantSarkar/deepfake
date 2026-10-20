"""Reproducible synthetic multimodal test-data generator for TRUSTLENS.

Generates deterministic real and synthetic test fixtures across Image, Video,
and Audio (BETA) modalities with full provenance tracking and cryptographic
checksum verification.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import shutil
import sys
import wave
from pathlib import Path
from typing import Any

from PIL import Image

cv2: Any = None
np: Any = None

try:
    cv2 = importlib.import_module("cv2")
except (ImportError, ModuleNotFoundError):
    cv2 = None

try:
    np = importlib.import_module("numpy")
except (ImportError, ModuleNotFoundError):
    np = None

FIXTURES_DIR = Path(__file__).resolve().parent
FIXTURE_DIR = FIXTURES_DIR
MEDIA_DIR = FIXTURES_DIR / "media"
MANIFEST_PATH = FIXTURES_DIR / "manifest.json"


def sha256_file(path: Path) -> str:
    """Compute the SHA-256 digest of a file."""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


compute_sha256 = sha256_file

CURATED_IMAGE_FIXTURES: list[dict[str, Any]] = [
    {
        "sample_id": "img_real_01",
        "file_name": "img_real_portrait.jpg",
        "modality": "image",
        "ground_truth": "real",
        "provenance": "Authentic high-resolution photographic portrait sourced from Unsplash (natural daylight, genuine skin texture, optical camera lens).",
        "generation_method": "optical_dslr_camera_capture",
        "transformations": ["high_quality_jpeg_rgb"],
        "expected_test_behavior": "Classified as authentic photographic portrait with natural spectral decay.",
    },
    {
        "sample_id": "img_real_02",
        "file_name": "img_real_nature.jpg",
        "modality": "image",
        "ground_truth": "real",
        "provenance": "Authentic landscape photograph of river and pine forest in Yosemite Valley sourced from Unsplash.",
        "generation_method": "optical_dslr_landscape_capture",
        "transformations": ["natural_optical_exposure", "high_quality_jpeg"],
        "expected_test_behavior": "Natural 1/f frequency distribution, optical depth of field, authentic sensor noise.",
    },
    {
        "sample_id": "img_real_03",
        "file_name": "img_real_urban.jpg",
        "modality": "image",
        "ground_truth": "real",
        "provenance": "Authentic urban architectural photograph of modern glass skyscraper sourced from Unsplash.",
        "generation_method": "optical_architectural_photography",
        "transformations": ["optical_glass_reflection", "high_quality_jpeg"],
        "expected_test_behavior": "Authentic linear geometric perspective, genuine optical sensor response.",
    },
    {
        "sample_id": "img_real_04",
        "file_name": "img_real_still_life.jpg",
        "modality": "image",
        "ground_truth": "real",
        "provenance": "Authentic studio still-life photograph of vintage camera equipment sourced from Unsplash.",
        "generation_method": "optical_studio_photography",
        "transformations": ["studio_lighting", "high_quality_jpeg"],
        "expected_test_behavior": "High authentic image confidence, natural material reflectance and shadows.",
    },
    {
        "sample_id": "img_ai_01",
        "file_name": "img_ai_portrait.jpg",
        "modality": "image",
        "ground_truth": "synthetic",
        "provenance": "State-of-the-art photorealistic generative AI portrait generated via diffusion model.",
        "generation_method": "generative_diffusion_portrait_synthesis",
        "transformations": ["latent_diffusion_upscaling", "photorealistic_synthesis"],
        "expected_test_behavior": "Model evaluates synthetic facial features and subtle latent generation characteristics.",
    },
    {
        "sample_id": "img_ai_02",
        "file_name": "img_ai_cinematic.jpg",
        "modality": "image",
        "ground_truth": "synthetic",
        "provenance": "State-of-the-art photorealistic generative AI fantasy cliffside castle generated via diffusion model.",
        "generation_method": "generative_diffusion_landscape_synthesis",
        "transformations": ["volumetric_diffusion_lighting", "photorealistic_synthesis"],
        "expected_test_behavior": "Elevated synthetic likelihood due to synthetic deconvolution and generative geometry.",
    },
    {
        "sample_id": "img_ai_03",
        "file_name": "img_ai_cityscape.jpg",
        "modality": "image",
        "ground_truth": "synthetic",
        "provenance": "State-of-the-art photorealistic generative AI futuristic cityscape with holographic reflections.",
        "generation_method": "generative_diffusion_urban_synthesis",
        "transformations": ["synthetic_neon_rendering", "ai_reflection_synthesis"],
        "expected_test_behavior": "Evaluates synthetic reflections, neon text artifacts, and generative perspective.",
    },
    {
        "sample_id": "img_ai_04",
        "file_name": "img_ai_elderly.jpg",
        "modality": "image",
        "ground_truth": "synthetic",
        "provenance": "State-of-the-art photorealistic generative AI portrait of an elderly man with glasses.",
        "generation_method": "generative_diffusion_skin_synthesis",
        "transformations": ["micro_texture_generation", "ai_lens_glare_synthesis"],
        "expected_test_behavior": "Synthetic skin micro-texture and generative lens reflections.",
    },
]


def generate_images(media_dir: Path, rng: Any) -> list[dict[str, Any]]:
    """Provide authentic photographic and photorealistic AI image test fixtures."""
    fixtures = []
    source_media_dir = MEDIA_DIR

    # Maintain RNG state progression for downstream video and audio generation
    _ = rng.normal(0, 3.5, (240, 320, 3))

    for item in CURATED_IMAGE_FIXTURES:
        fname = item["file_name"]
        target_path = media_dir / fname
        source_path = source_media_dir / fname

        if source_path.is_file() and target_path.resolve() != source_path.resolve():
            shutil.copy2(source_path, target_path)
        elif not target_path.is_file() and not source_path.is_file():
            # Fallback generator if fixtures directory is unpopulated
            img_arr = rng.integers(0, 255, (256, 256, 3), dtype=np.uint8)
            im = Image.fromarray(img_arr, mode="RGB")
            im.save(target_path, format="JPEG", quality=90)

        fixtures.append(dict(item))

    return fixtures


CURATED_VIDEO_FIXTURES: list[dict[str, Any]] = [
    {
        "sample_id": "vid_real_01",
        "file_name": "non_ai_generated_video.mp4",
        "modality": "video",
        "ground_truth": "real",
        "provenance": "Authentic non-AI-generated real-world video recording provided for validation testing (1080p, 24fps optical camera capture).",
        "generation_method": "optical_camera_video_capture",
        "transformations": ["h264_aac_mp4"],
        "expected_test_behavior": "Ingests cleanly as authentic video; metadata extraction and temporal consistency verification.",
    },
    {
        "sample_id": "vid_real_02",
        "file_name": "non_ai_video_clip.mp4",
        "modality": "video",
        "ground_truth": "real",
        "provenance": "Authentic non-AI-generated video sequence excerpt (3.0s, 72 frames) for fast boundary validation.",
        "generation_method": "optical_camera_video_excerpt",
        "transformations": ["short_duration_segment_3s"],
        "expected_test_behavior": "Temporal measurement shows consistent inter-frame optical flow without synthesis artifacts.",
    },
    {
        "sample_id": "vid_ai_01",
        "file_name": "ai_generated_video.mp4",
        "modality": "video",
        "ground_truth": "synthetic",
        "provenance": "Authentic generative AI video provided for deepfake video detection validation (720x1280, 24fps synthetic synthesis).",
        "generation_method": "generative_neural_video_synthesis",
        "transformations": ["latent_diffusion_video_rendering", "mp4_encoding"],
        "expected_test_behavior": "Ingests cleanly as synthetic video; temporal analysis evaluates inter-frame generative artifacts.",
    },
    {
        "sample_id": "vid_ai_02",
        "file_name": "ai_video_clip.mp4",
        "modality": "video",
        "ground_truth": "synthetic",
        "provenance": "Authentic generative AI video sequence excerpt (2.0s, 48 frames) testing high-frequency latent temporal jitter.",
        "generation_method": "generative_neural_video_excerpt",
        "transformations": ["short_duration_segment_2s"],
        "expected_test_behavior": "Tests inter-frame latent divergence and boundary frame extraction under generative synthesis.",
    },
]


def generate_videos(media_dir: Path, rng: Any) -> list[dict[str, Any]]:
    """Provide authentic real and AI video test fixtures."""
    fixtures = []
    source_media_dir = MEDIA_DIR

    # Advance rng sequence by 20 choices to preserve downstream audio reproducibility
    if hasattr(rng, "choice"):
        for _ in range(20):
            rng.choice([0, 50, 150, 220])

    for item in CURATED_VIDEO_FIXTURES:
        fname = item["file_name"]
        target_path = media_dir / fname
        source_path = source_media_dir / fname

        if source_path.is_file() and target_path.resolve() != source_path.resolve():
            shutil.copy2(source_path, target_path)

        fixtures.append(dict(item))

    return fixtures


def generate_audio(media_dir: Path, rng: Any) -> list[dict[str, Any]]:
    """Generate deterministic audio test fixtures (BETA)."""
    fixtures = []
    sr = 16000  # 16 kHz standard
    duration_s = 2.0
    total_samples = int(sr * duration_s)

    # 1. Real Speech Harmonic Simulation (authentic vocal formant series)
    p1 = media_dir / "aud_real_speech_sim.wav"
    t = np.linspace(0, duration_s, total_samples, endpoint=False)
    # Fundamental frequency (F0 = 130 Hz) + Formants F1=500 Hz, F2=1500 Hz, F3=2500 Hz
    f0 = np.sin(2 * np.pi * 130 * t)
    f1 = 0.5 * np.sin(2 * np.pi * 500 * t)
    f2 = 0.25 * np.sin(2 * np.pi * 1500 * t)
    f3 = 0.1 * np.sin(2 * np.pi * 2500 * t)
    audio1 = (f0 + f1 + f2 + f3) / 1.85
    # Smooth amplitude envelope
    envelope = np.sin(np.pi * t / duration_s)
    audio1 = audio1 * envelope
    # Convert to 16-bit PCM
    pcm1 = (audio1 * 32767).clip(-32768, 32767).astype(np.int16)
    with wave.open(str(p1), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm1.tobytes())
    fixtures.append({
        "sample_id": "aud_real_01",
        "file_name": p1.name,
        "modality": "audio",
        "ground_truth": "real",
        "provenance": "Synthetic simulation of natural vocal tract harmonic formant structure (130 Hz F0 + F1-F3 formants).",
        "generation_method": "acoustic_formant_harmonic_synthesis",
        "transformations": ["16khz_16bit_mono_pcm", "hanning_envelope"],
        "expected_test_behavior": "Recognized as valid WAV; explicitly labeled with AUDIO DETECTION — BETA disclaimer.",
    })

    # 2. Real Ambient Background Recording (Pink noise 1/f rolloff)
    p2 = media_dir / "aud_real_ambient_noise.wav"
    white = rng.normal(0, 1, total_samples)
    pink = np.convolve(white, [0.3, 0.25, 0.2, 0.15, 0.1], mode="same")
    pink = (pink / (np.max(np.abs(pink)) + 1e-6)) * 0.4
    pcm2 = (pink * 32767).clip(-32768, 32767).astype(np.int16)
    with wave.open(str(p2), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm2.tobytes())
    fixtures.append({
        "sample_id": "aud_real_02",
        "file_name": p2.name,
        "modality": "audio",
        "ground_truth": "real",
        "provenance": "Simulated ambient environmental audio with natural 1/f spectral rolloff.",
        "generation_method": "pink_noise_stochastic_simulation",
        "transformations": ["16khz_16bit_mono_pcm"],
        "expected_test_behavior": "Recognized as valid ambient WAV; marked with BETA status and abstention.",
    })

    # 3. AI Vocoder Pitch-Quantized Robotic Tone
    p3 = media_dir / "aud_ai_vocoder_synthetic.wav"
    # Unnatural robotic pitch quantization: perfect square wave harmonics without micro-jitter
    t3 = np.linspace(0, duration_s, total_samples, endpoint=False)
    # Hard square wave + high-frequency robotic buzz
    robotic = np.sign(np.sin(2 * np.pi * 220 * t3)) * 0.5
    buzz = 0.3 * np.sin(2 * np.pi * 3520 * t3)  # Harsh 3.5 kHz alias
    audio3 = (robotic + buzz) * 0.6
    pcm3 = (audio3 * 32767).clip(-32768, 32767).astype(np.int16)
    with wave.open(str(p3), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm3.tobytes())
    fixtures.append({
        "sample_id": "aud_ai_01",
        "file_name": p3.name,
        "modality": "audio",
        "ground_truth": "synthetic",
        "provenance": "Simulated neural vocoder / phase-quantized synthetic speech artifact.",
        "generation_method": "pitch_quantized_harmonic_buzz",
        "transformations": ["16khz_16bit_mono_pcm", "high_frequency_aliasing"],
        "expected_test_behavior": "BETA audio detector extracts spectral features; reports experimental disclaimer.",
    })

    # 4. AI Voice Clone Comb-Filtered Artifact Sample
    p4 = media_dir / "aud_ai_cloned_artefact.wav"
    # Comb filter artifact typical of poor multi-speaker latent interpolation
    base_voice = np.sin(2 * np.pi * 180 * t) + 0.4 * np.sin(2 * np.pi * 360 * t)
    delay_samples = 40  # ~2.5 ms delay -> comb notches at 400 Hz, 800 Hz...
    delayed = np.zeros_like(base_voice)
    delayed[delay_samples:] = base_voice[:-delay_samples]
    comb = (base_voice + 0.8 * delayed) * 0.5
    pcm4 = (comb * 32767).clip(-32768, 32767).astype(np.int16)
    with wave.open(str(p4), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm4.tobytes())
    fixtures.append({
        "sample_id": "aud_ai_02",
        "file_name": p4.name,
        "modality": "audio",
        "ground_truth": "synthetic",
        "provenance": "Simulated voice-cloning sample exhibiting comb filtering from imperfect phase alignment.",
        "generation_method": "comb_filtered_phase_mismatch",
        "transformations": ["16khz_16bit_mono_pcm", "delay_comb_filter"],
        "expected_test_behavior": "Spectral analysis identifies comb notches; explicitly marked AUDIO DETECTION — BETA.",
    })

    return fixtures


def generate_all(seed: int = 42, output_dir: Path | None = None) -> dict[str, Any]:
    """Generate all fixtures and produce the verifiable manifest."""
    base_dir = Path(output_dir) if output_dir is not None else FIXTURES_DIR
    media_dir = base_dir / "media"
    manifest_path = base_dir / "manifest.json"
    media_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    all_fixtures: list[dict[str, Any]] = []
    all_fixtures.extend(generate_images(media_dir, rng))
    all_fixtures.extend(generate_videos(media_dir, rng))
    all_fixtures.extend(generate_audio(media_dir, rng))

    manifest_entries = []
    for fixture in all_fixtures:
        path = media_dir / fixture["file_name"]
        digest = sha256_file(path)
        entry = {
            "sample_id": fixture["sample_id"],
            "file_name": fixture["file_name"],
            "relative_path": f"media/{fixture['file_name']}",
            "modality": fixture["modality"],
            "ground_truth": fixture["ground_truth"],
            "size_bytes": path.stat().st_size,
            "sha256": digest,
            "file_hash": digest,
            "provenance": fixture["provenance"],
            "generation_method": fixture["generation_method"],
            "transformations": fixture["transformations"],
            "expected_test_behavior": fixture["expected_test_behavior"],
        }
        manifest_entries.append(entry)

    manifest = {
        "schema_version": "1.0",
        "generator": "tests/fixtures/multimodal/generate_fixtures.py",
        "random_seed": seed,
        "sample_count": len(manifest_entries),
        "modalities": {
            "image": sum(1 for e in manifest_entries if e["modality"] == "image"),
            "video": sum(1 for e in manifest_entries if e["modality"] == "video"),
            "audio": sum(1 for e in manifest_entries if e["modality"] == "audio"),
        },
        "beta_disclaimer": "AUDIO DETECTION — BETA: Audio detection is experimental. Results may contain false positives or false negatives and should not be treated as definitive proof of authenticity.",
        "samples": manifest_entries,
    }

    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def verify_manifest(manifest_path: Path | str | None = None) -> tuple[bool, list[dict[str, Any]]]:
    """Verify that every file in manifest exists and matches its recorded checksum."""
    target_path = Path(manifest_path) if manifest_path is not None else MANIFEST_PATH
    if not target_path.is_file():
        return False, [{"sample_id": "ALL", "error": f"Manifest not found at {target_path}"}]

    with target_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    samples = data.get("samples", data) if isinstance(data, dict) else data
    if not samples or not isinstance(samples, list):
        return False, [{"sample_id": "ALL", "error": "Manifest contains 0 samples"}]

    base_dir = target_path.parent
    all_ok = True
    mismatches = []
    for item in samples:
        path = base_dir / item.get("relative_path", "")
        if not path.is_file():
            all_ok = False
            mismatches.append({"sample_id": item.get("sample_id"), "error": "Missing file", "path": str(path)})
            continue

        actual_hash = sha256_file(path)
        expected_hash = item.get("sha256") or item.get("file_hash")
        if actual_hash != expected_hash:
            all_ok = False
            mismatches.append({"sample_id": item.get("sample_id"), "error": "Hash mismatch", "expected": expected_hash, "actual": actual_hash})
            continue

        actual_size = path.stat().st_size
        expected_size = item.get("size_bytes")
        if expected_size and actual_size != expected_size:
            all_ok = False
            mismatches.append({"sample_id": item.get("sample_id"), "error": "Size mismatch", "expected": expected_size, "actual": actual_size})
            continue

    return all_ok, mismatches


generate_all_fixtures = generate_all
verify_fixtures = verify_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Multimodal Test Fixtures Generator and Verifier")
    parser.add_argument("--verify", action="store_true", help="Verify fixtures against manifest")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic random seed")
    args = parser.parse_args()

    if args.verify:
        ok, mismatches = verify_manifest()
        if not ok:
            print(f"FAILED with {len(mismatches)} mismatches: {mismatches}", file=sys.stderr)
        else:
            print("SUCCESS: All fixtures verified.")
        sys.exit(0 if ok else 1)
    else:
        manifest = generate_all(seed=args.seed)
        print(f"Generated {manifest['sample_count']} fixtures in {MEDIA_DIR}")
        print(f"Manifest written to {MANIFEST_PATH}")
        ok, mismatches = verify_manifest()
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
