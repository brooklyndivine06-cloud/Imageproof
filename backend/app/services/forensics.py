"""Visual forensic measurements.

These are plain signal-processing measurements (noise residual statistics,
Fourier-spectrum peaks, JPEG quantisation, error-level analysis). They are
reported as *informational evidence*: no detection threshold has been
validated for them, so they are NOT used in the classification. Each signal
carries a neutral interpretation that explains what the number is and which
benign processing steps can produce it.
"""

from __future__ import annotations

import base64
import io

import numpy as np
from PIL import Image

from app.schemas import ElaResult, ForensicSignal, ForensicsResult

NOISE_CROP = 1024
SPECTRUM_SIZE = 512
BLOCK = 32
ELA_MAX_PIXELS = 8_000_000
ELA_QUALITY = 90
HEATMAP_MAX_SIDE = 640

# Standard IJG luminance quantisation table (natural order).
_STD_LUMA_QT = np.array(
    [
        16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55,
        14, 13, 16, 24, 40, 57, 69, 56, 14, 17, 22, 29, 51, 87, 80, 62,
        18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92,
        49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99,
    ],
    dtype=np.float64,
)


def estimate_jpeg_quality(img: Image.Image) -> float | None:
    """IJG-equivalent quality estimated from the luminance quantisation table.

    Encoders that do not use IJG-scaled tables (many cameras, Photoshop) give an
    approximate "equivalent" value only. Returns None if the file has no tables.
    """
    tables = getattr(img, "quantization", None)
    if not tables or 0 not in tables or len(tables[0]) != 64:
        return None
    scale = 100.0 * float(np.mean(np.array(tables[0], dtype=np.float64) / _STD_LUMA_QT))
    if scale <= 0:
        return None
    quality = 5000.0 / scale if scale >= 100 else (200.0 - scale) / 2.0
    return float(min(100.0, max(1.0, quality)))


def _center_crop(arr: np.ndarray, size: int) -> np.ndarray:
    h, w = arr.shape[:2]
    ch, cw = min(h, size), min(w, size)
    top, left = (h - ch) // 2, (w - cw) // 2
    return arr[top : top + ch, left : left + cw]


def _box3(arr: np.ndarray) -> np.ndarray:
    padded = np.pad(arr, 1, mode="reflect")
    h, w = arr.shape
    acc = np.zeros_like(arr, dtype=np.float32)
    for dy in range(3):
        for dx in range(3):
            acc += padded[dy : dy + h, dx : dx + w]
    return acc / 9.0


def noise_signals(gray: np.ndarray) -> tuple[list[ForensicSignal], str]:
    crop = _center_crop(gray, NOISE_CROP).astype(np.float32)
    h, w = crop.shape
    residual = crop - _box3(crop)
    sigma = float(np.median(np.abs(residual - np.median(residual))) * 1.4826)

    block_sigmas: list[float] = []
    for y in range(0, h - BLOCK + 1, BLOCK):
        for x in range(0, w - BLOCK + 1, BLOCK):
            block = residual[y : y + BLOCK, x : x + BLOCK]
            block_sigmas.append(float(np.median(np.abs(block - np.median(block))) * 1.4826))
    signals = [
        ForensicSignal(
            id="noise_level",
            label="Noise level",
            value=round(sigma, 3),
            unit="8-bit levels",
            interpretation=(
                "Typical high-frequency noise left after removing a 3×3 local average (robust estimate). Sensor noise, denoising, "
                "sharpening, compression and resizing all change this value, so it is context rather than a verdict."
            ),
        )
    ]
    if len(block_sigmas) >= 4:
        arr = np.array(block_sigmas)
        mean = float(arr.mean())
        cv = float(arr.std() / mean) if mean > 1e-6 else 0.0
        flat = float(np.mean(arr < 0.5))
        signals.append(
            ForensicSignal(
                id="noise_uniformity",
                label="Noise variation across regions",
                value=round(cv, 3),
                unit="coefficient of variation",
                interpretation=(
                    "How much the noise level differs between 32 px blocks. Scenes with sky, shadows or blur naturally vary a lot, "
                    "so a high or low value is not suspicious by itself."
                ),
            )
        )
        signals.append(
            ForensicSignal(
                id="flat_blocks",
                label="Very smooth regions",
                value=round(flat * 100, 1),
                unit="% of blocks",
                interpretation=(
                    "Share of 32 px blocks with almost no fine detail. Smooth backgrounds, bokeh, heavy denoising or beauty filters "
                    "raise this share; so does synthetic content."
                ),
            )
        )
    region = f"central {crop.shape[1]}×{crop.shape[0]} px region"
    return signals, region


def spectral_peaks(gray: np.ndarray) -> ForensicSignal | None:
    crop = _center_crop(gray, SPECTRUM_SIZE).astype(np.float32)
    h, w = crop.shape
    size = min(h, w)
    if size < 128:
        return None
    crop = crop[:size, :size]
    window = np.outer(np.hanning(size), np.hanning(size)).astype(np.float32)
    spectrum = np.fft.fftshift(np.fft.fft2((crop - crop.mean()) * window))
    log_mag = np.log1p(np.abs(spectrum)).astype(np.float64)

    yy, xx = np.indices(log_mag.shape)
    cy = cx = size // 2
    radius = np.hypot(yy - cy, xx - cx).astype(np.int32)
    max_r = size // 2
    counts = np.bincount(radius.ravel())
    means = np.bincount(radius.ravel(), weights=log_mag.ravel()) / np.maximum(counts, 1)
    sq = np.bincount(radius.ravel(), weights=(log_mag**2).ravel()) / np.maximum(counts, 1)
    stds = np.sqrt(np.maximum(sq - means**2, 1e-12))
    z = (log_mag - means[radius]) / stds[radius]

    mask = (radius >= 8) & (radius <= max_r - 2)
    mask &= (np.abs(yy - cy) > 2) & (np.abs(xx - cx) > 2)  # exclude the window/edge cross
    padded = np.pad(z, 1, mode="constant", constant_values=-np.inf)
    local_max = np.ones_like(z, dtype=bool)
    for dy in range(3):
        for dx in range(3):
            if dy == 1 and dx == 1:
                continue
            local_max &= z > padded[dy : dy + size, dx : dx + size]
    peaks = int(np.count_nonzero(local_max & mask & (z >= 6.0)))
    return ForensicSignal(
        id="spectral_peaks",
        label="Isolated Fourier-spectrum peaks",
        value=peaks,
        unit="count",
        interpretation=(
            "Narrow peaks in the 2-D frequency spectrum that stand out from their surroundings. Up-sampling layers in some generators can "
            "leave periodic traces, but JPEG block grids, resizing, screen patterns and scanner halftones produce them too. "
            "No validated decision threshold exists for this count."
        ),
    )


_HEAT_ANCHORS = np.array([0.0, 0.35, 0.7, 1.0])
_HEAT_COLORS = np.array([[16, 24, 48], [24, 110, 140], [236, 190, 70], [255, 248, 225]], dtype=np.float64)


def _heatmap(values: np.ndarray) -> Image.Image:
    peak = float(values.max())
    norm = values / peak if peak > 0 else values
    lut = np.stack(
        [np.interp(np.linspace(0, 1, 256), _HEAT_ANCHORS, _HEAT_COLORS[:, c]) for c in range(3)], axis=1
    ).astype("uint8")
    idx = np.clip(norm * 255.0, 0, 255).astype("uint8")
    return Image.fromarray(lut[idx], "RGB")


def error_level_analysis(rgb: Image.Image, source_format: str) -> ElaResult:
    if source_format != "JPEG":
        return ElaResult(
            applicable=False,
            reason="Error-level analysis is only meaningful for JPEG files. This file is not a JPEG.",
        )
    if rgb.width * rgb.height > ELA_MAX_PIXELS:
        return ElaResult(
            applicable=False,
            reason=f"The image is larger than {ELA_MAX_PIXELS / 1_000_000:g} megapixels, so error-level analysis was skipped.",
        )
    buffer = io.BytesIO()
    rgb.save(buffer, "JPEG", quality=ELA_QUALITY)
    buffer.seek(0)
    recompressed = Image.open(buffer).convert("RGB")
    diff = np.abs(np.asarray(rgb, dtype=np.int16) - np.asarray(recompressed, dtype=np.int16)).max(axis=2).astype(np.float32)
    heat = _heatmap(diff)
    heat.thumbnail((HEATMAP_MAX_SIDE, HEATMAP_MAX_SIDE), Image.Resampling.BILINEAR)
    out = io.BytesIO()
    heat.save(out, "JPEG", quality=82)
    data_url = "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode("ascii")
    return ElaResult(
        applicable=True,
        mean=round(float(diff.mean()), 3),
        p99=round(float(np.percentile(diff, 99)), 3),
        heatmap_data_url=data_url,
        note=(
            f"The image was re-saved at JPEG quality {ELA_QUALITY} and compared with itself. Brighter areas changed more. "
            "Brightness is scaled to this image's own maximum. Edges, texture, saturation and prior editing all affect it, "
            "so uneven patterns do not by themselves indicate manipulation."
        ),
    )


def run_forensics(rgb: Image.Image, original: Image.Image, source_format: str) -> ForensicsResult:
    signals: list[ForensicSignal] = []
    notes: list[str] = []
    failures = 0

    gray = np.asarray(rgb.convert("L"), dtype=np.float32)

    region = None
    try:
        noise, region = noise_signals(gray)
        signals.extend(noise)
    except Exception:
        failures += 1
        notes.append("Noise analysis could not be completed for this image.")

    try:
        peaks = spectral_peaks(gray)
        if peaks is not None:
            signals.append(peaks)
        else:
            notes.append("Frequency analysis was skipped because the image is too small (needs at least 128 px on both sides).")
    except Exception:
        failures += 1
        notes.append("Frequency analysis could not be completed for this image.")

    if source_format == "JPEG":
        quality = estimate_jpeg_quality(original)
        if quality is not None:
            signals.append(
                ForensicSignal(
                    id="jpeg_quality",
                    label="Estimated JPEG quality",
                    value=round(quality, 0),
                    unit="IJG-equivalent, 1-100",
                    interpretation=(
                        "Derived from the file's quantisation table. Low values mean strong compression, which erases fine detail that "
                        "detectors may rely on. Cameras and editors that do not use the standard scaling give only an approximate equivalent."
                    ),
                )
            )

    ela: ElaResult | None
    try:
        ela = error_level_analysis(rgb, source_format)
    except Exception:
        failures += 1
        ela = ElaResult(applicable=False, reason="Error-level analysis could not be completed for this image.")

    notes.append(
        "These measurements are informational. No decision threshold has been validated for them, so they did not influence the assessment."
    )
    status = "completed" if failures == 0 else ("partial" if signals or (ela and ela.applicable) else "unavailable")
    return ForensicsResult(status=status, signals=signals, ela=ela, notes=notes, region=region)
