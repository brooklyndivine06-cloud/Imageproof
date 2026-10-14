"""Server-side upload validation and safe decoding.

Everything here works on the bytes of the upload. The declared file name and
Content-Type are never trusted: the format is detected from magic bytes and then
confirmed by actually decoding the image with Pillow.
"""

from __future__ import annotations

import hashlib
import io
import warnings
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps

from app.config import SUPPORTED_FORMATS, Settings
from app.core.errors import AppError

SUPPORTED_LIST = "JPEG, PNG or WebP"

_OTHER_SIGNATURES: list[tuple[bytes, str]] = [
    (b"GIF8", "GIF"),
    (b"BM", "BMP"),
    (b"II*\x00", "TIFF"),
    (b"MM\x00*", "TIFF"),
    (b"%PDF", "PDF"),
    (b"PK\x03\x04", "ZIP"),
]


@dataclass
class ValidatedImage:
    original: Image.Image  # decoded exactly as stored (used to read metadata / tables)
    rgb: Image.Image  # orientation-corrected, 8-bit RGB (used for analysis)
    format: str
    mime_type: str
    width: int
    height: int
    mode: str
    size_bytes: int
    sha256: str


def sniff_format(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "JPEG"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "PNG"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    return None


def _describe_unsupported(data: bytes) -> str:
    for signature, name in _OTHER_SIGNATURES:
        if data.startswith(signature):
            return name
    if data[4:8] == b"ftyp":
        return "HEIC/AVIF/video container"
    return "unknown"


def _to_rgb(img: Image.Image) -> Image.Image:
    if img.mode == "RGB":
        return img
    if img.mode in ("I;16", "I;16L", "I;16B", "I"):
        arr = np.asarray(img, dtype=np.float32)
        top = 65535.0 if arr.max() > 255 else 255.0
        arr8 = np.clip(arr / top * 255.0, 0, 255).astype("uint8")
        return Image.fromarray(arr8).convert("RGB")
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return img.convert("RGB")


def validate_image(data: bytes, settings: Settings) -> ValidatedImage:
    if not data:
        raise AppError(400, "empty_file", "The uploaded file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise AppError(
            413,
            "file_too_large",
            f"The file is larger than the {settings.max_upload_mb:g} MB limit.",
            details={"max_bytes": settings.max_upload_bytes, "size_bytes": len(data)},
        )

    fmt = sniff_format(data)
    if fmt is None:
        detected = _describe_unsupported(data)
        raise AppError(
            415,
            "unsupported_media_type",
            f"This file is not a supported image. Upload a {SUPPORTED_LIST} image.",
            details={"detected": detected, "supported": list(SUPPORTED_FORMATS)},
        )

    Image.MAX_IMAGE_PIXELS = settings.max_image_pixels
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            img = Image.open(io.BytesIO(data), formats=[fmt])
            width, height = img.size
            frames = getattr(img, "n_frames", 1)
            if width * height > settings.max_image_pixels:
                raise Image.DecompressionBombError("pixel limit exceeded")
            if min(width, height) < settings.min_image_side:
                raise AppError(
                    422,
                    "image_too_small",
                    f"The image is too small to analyze. Both sides must be at least {settings.min_image_side} px.",
                    details={"width": width, "height": height, "min_side": settings.min_image_side},
                )
            if frames > 1:
                raise AppError(
                    422,
                    "animated_not_supported",
                    "Animated images are not supported. Upload a single-frame image.",
                )
            img.load()
    except AppError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise AppError(
            422,
            "image_too_large_dimensions",
            f"The image has too many pixels. The limit is {settings.max_image_pixels / 1_000_000:g} megapixels.",
            details={"max_pixels": settings.max_image_pixels},
        ) from None
    except (OSError, SyntaxError, ValueError, EOFError, Image.UnidentifiedImageError):
        raise AppError(
            422,
            "corrupt_image",
            "The file could not be decoded. It may be corrupted or truncated.",
        ) from None

    try:
        upright = ImageOps.exif_transpose(img)
        rgb = _to_rgb(upright if upright is not None else img)
    except (OSError, ValueError):
        raise AppError(422, "corrupt_image", "The file could not be decoded.") from None

    return ValidatedImage(
        original=img,
        rgb=rgb,
        format=fmt,
        mime_type=SUPPORTED_FORMATS[fmt],
        width=width,
        height=height,
        mode=img.mode,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
