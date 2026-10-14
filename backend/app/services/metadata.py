"""Metadata extraction (EXIF, XMP, PNG text chunks, ICC profile).

Design rules:
* Metadata is its own evidence source. It never feeds the classifier and the
  absence of metadata is never treated as a sign of AI generation.
* Output is minimised: only an allow-list of technically relevant fields is
  returned. GPS coordinates, serial numbers and owner/author names are detected
  but withheld.
* Embedded generator strings are unauthenticated declarations. They are
  reported as "signals", not as proof.
"""

from __future__ import annotations

import io
import re
from typing import Any

from PIL import ExifTags, Image, ImageCms

from app.schemas import GeneratorSignal, MetadataField, MetadataGroup, MetadataResult

MAX_VALUE_LEN = 160

# (group, key, label) per IFD ------------------------------------------------------
_BASE_FIELDS = {
    271: ("camera", "Make", "Camera make"),
    272: ("camera", "Model", "Camera model"),
    305: ("software", "Software", "Software"),
    306: ("dates", "DateTime", "Modified"),
    274: ("image", "Orientation", "Orientation"),
}
_EXIF_FIELDS = {
    42035: ("camera", "LensMake", "Lens make"),
    42036: ("camera", "LensModel", "Lens model"),
    33434: ("capture", "ExposureTime", "Exposure time"),
    33437: ("capture", "FNumber", "Aperture"),
    34855: ("capture", "ISOSpeedRatings", "ISO"),
    37386: ("capture", "FocalLength", "Focal length"),
    41989: ("capture", "FocalLengthIn35mmFilm", "Focal length (35 mm equiv.)"),
    37385: ("capture", "Flash", "Flash (raw flag)"),
    36867: ("dates", "DateTimeOriginal", "Captured"),
    36868: ("dates", "DateTimeDigitized", "Digitized"),
    40961: ("image", "ColorSpace", "Color space"),
}
_WITHHELD_BASE = {315: "author/artist name", 33432: "copyright holder", 270: "image description"}
_WITHHELD_EXIF = {
    42032: "camera owner name",
    42033: "camera body serial number",
    42037: "lens serial number",
    37510: "user comment",
}
GPS_IFD = 0x8825
EXIF_IFD = 0x8769

GROUP_LABELS = {
    "camera": "Camera",
    "capture": "Capture settings",
    "dates": "Dates",
    "software": "Software and editing",
    "image": "Image properties",
}
GROUP_ORDER = ["camera", "capture", "dates", "software", "image"]

# Words that appear in software/creator strings written by generative tools.
_GENERATOR_RE = re.compile(
    r"\b(stable[ _-]?diffusion|midjourney|dall[-· ]?e|adobe firefly|firefly|comfyui|automatic1111|"
    r"invokeai|novelai|leonardo\.ai|ideogram|flux\.1|sdxl|imagen|runway(?:ml)?|bing image creator|"
    r"gpt-image|nano banana)\b",
    re.IGNORECASE,
)

DIGITAL_SOURCE_TYPES: dict[str, tuple[str, str]] = {
    # short name -> (category, human description)
    "trainedAlgorithmicMedia": ("ai", "Created by a generative AI model"),
    "compositeWithTrainedAlgorithmicMedia": ("partial_ai", "Composite that includes generative-AI content"),
    "algorithmicMedia": ("other", "Created by an algorithm (not a trained model)"),
    "digitalCapture": ("camera", "Captured by a digital camera"),
    "computationalCapture": ("camera", "Computational photography capture"),
    "compositeCapture": ("camera", "Composite of camera captures"),
    "negativeFilm": ("camera", "Scan of negative film"),
    "positiveFilm": ("camera", "Scan of positive film"),
    "print": ("other", "Scan of a printed image"),
    "screenCapture": ("other", "Screen capture"),
    "humanEdits": ("other", "Edited by a human"),
    "algorithmicallyEnhanced": ("other", "Algorithmically enhanced"),
    "digitalCreation": ("other", "Created digitally by a human"),
    "dataDrivenMedia": ("other", "Created from data"),
    "virtualRecording": ("other", "Virtual recording"),
    "composite": ("other", "Composite of several sources"),
    "compositeSynthetic": ("partial_ai", "Composite containing synthetic elements"),
}


def short_source_type(value: str | None) -> str | None:
    if not value:
        return None
    return value.rstrip("/").rsplit("/", 1)[-1]


def classify_source_type(value: str | None) -> tuple[str, str] | None:
    short = short_source_type(value)
    if short and short in DIGITAL_SOURCE_TYPES:
        return DIGITAL_SOURCE_TYPES[short]
    return None


def _clip(text: str) -> str:
    text = text.replace("\x00", "").strip()
    return text if len(text) <= MAX_VALUE_LEN else text[: MAX_VALUE_LEN - 1] + "…"


def _fmt(value: Any) -> str:
    if isinstance(value, bytes):
        try:
            return _clip(value.decode("utf-8", errors="replace"))
        except Exception:  # pragma: no cover - defensive
            return f"{len(value)} bytes"
    if isinstance(value, (tuple, list)):
        return _clip(", ".join(_fmt(v) for v in value))
    try:
        from PIL.TiffImagePlugin import IFDRational

        if isinstance(value, IFDRational):
            value = float(value)
    except Exception:  # pragma: no cover - defensive
        pass
    if isinstance(value, float):
        return f"{value:.6g}"
    return _clip(str(value))


def _format_special(key: str, value: Any) -> str:
    if isinstance(value, tuple) and len(value) == 2 and all(isinstance(v, int) for v in value) and value[1]:
        value = value[0] / value[1]  # raw (numerator, denominator) pair
    try:
        if key == "ExposureTime":
            seconds = float(value)
            if 0 < seconds < 1:
                return f"1/{round(1 / seconds)} s"
            return f"{seconds:g} s"
        if key == "FNumber":
            return f"f/{float(value):g}"
        if key in ("FocalLength", "FocalLengthIn35mmFilm"):
            return f"{float(value):g} mm"
        if key == "Orientation":
            names = {1: "Normal", 3: "Rotated 180°", 6: "Rotated 90° CW", 8: "Rotated 90° CCW"}
            return names.get(int(value), str(value))
        if key == "ColorSpace":
            return {1: "sRGB", 65535: "Uncalibrated"}.get(int(value), str(value))
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    return _fmt(value)


def _find_xmp(data: bytes) -> str | None:
    start = data.find(b"<x:xmpmeta")
    if start == -1:
        return None
    end = data.find(b"</x:xmpmeta>", start)
    if end == -1:
        return None
    return data[start : end + len(b"</x:xmpmeta>")].decode("utf-8", errors="replace")


def _xmp_values(xmp: str, tag: str) -> list[str]:
    values: list[str] = []
    # attribute form: ns:Tag="value"
    values += re.findall(rf'(?:\w+:)?{tag}="([^"]{{1,300}})"', xmp)
    # element form: <ns:Tag>value</ns:Tag>
    values += re.findall(rf"<(?:\w+:)?{tag}[^>]*>([^<]{{1,300}})</(?:\w+:)?{tag}>", xmp)
    return [v.strip() for v in values if v.strip()]


def _parse_xmp(xmp: str) -> dict[str, Any]:
    return {
        "creator_tool": (_xmp_values(xmp, "CreatorTool") or [None])[0],
        "digital_source_types": _xmp_values(xmp, "DigitalSourceType"),
        "software_agents": list(dict.fromkeys(_xmp_values(xmp, "softwareAgent")))[:5],
    }


def _decode_user_comment(raw: Any) -> str:
    if isinstance(raw, bytes):
        for prefix in (b"ASCII\x00\x00\x00", b"UNICODE\x00", b"JIS\x00\x00\x00\x00\x00"):
            if raw.startswith(prefix):
                raw = raw[len(prefix) :]
                break
        for enc in ("utf-8", "utf-16-be", "utf-16-le", "latin-1"):
            try:
                text = raw.decode(enc)
                if text.strip("\x00"):
                    return text
            except UnicodeDecodeError:
                continue
        return ""
    return str(raw)


def _looks_like_sd_parameters(text: str) -> bool:
    return "Steps:" in text and ("Sampler:" in text or "CFG scale:" in text or "Seed:" in text)


def extract_metadata(img: Image.Image, data: bytes) -> MetadataResult:
    fields: dict[str, list[MetadataField]] = {g: [] for g in GROUP_ORDER}
    signals: list[GeneratorSignal] = []
    withheld: list[str] = []
    other_tags: list[str] = []
    notes: list[str] = []

    # --- EXIF ---------------------------------------------------------------
    exif_present = False
    camera_present = False
    try:
        exif = img.getexif()
    except Exception:  # corrupt EXIF block must not abort the analysis
        exif = None
    if exif is not None and len(exif) > 0:
        exif_present = True
        base_values = dict(exif.items())
        try:
            exif_ifd = dict(exif.get_ifd(EXIF_IFD))
        except Exception:
            exif_ifd = {}
        try:
            gps_ifd = dict(exif.get_ifd(GPS_IFD))
        except Exception:
            gps_ifd = {}

        for tag, (group, key, label) in _BASE_FIELDS.items():
            if tag in base_values and base_values[tag] not in (None, ""):
                fields[group].append(MetadataField(key=key, label=label, value=_format_special(key, base_values[tag])))
        for tag, (group, key, label) in _EXIF_FIELDS.items():
            if tag in exif_ifd and exif_ifd[tag] not in (None, ""):
                fields[group].append(MetadataField(key=key, label=label, value=_format_special(key, exif_ifd[tag])))

        for tag, description in _WITHHELD_BASE.items():
            if tag in base_values:
                withheld.append(description)
        for tag, description in _WITHHELD_EXIF.items():
            if tag in exif_ifd:
                withheld.append(description)
        if GPS_IFD in base_values or gps_ifd:
            withheld.append("GPS location")

        shown = set(_BASE_FIELDS) | set(_WITHHELD_BASE) | {EXIF_IFD, GPS_IFD}
        shown_exif = set(_EXIF_FIELDS) | set(_WITHHELD_EXIF)
        for tag in base_values:
            if tag not in shown:
                other_tags.append(ExifTags.TAGS.get(tag, f"Tag {tag}"))
        for tag in exif_ifd:
            if tag not in shown_exif:
                other_tags.append(ExifTags.TAGS.get(tag, f"Tag {tag}"))

        camera_present = any(f.key in ("Make", "Model") for f in fields["camera"])

        # Generation parameters can be written to EXIF UserComment by some UIs.
        if 37510 in exif_ifd and _looks_like_sd_parameters(_decode_user_comment(exif_ifd[37510])):
            signals.append(
                GeneratorSignal(
                    source="EXIF UserComment",
                    kind="generation_parameters",
                    description="Text that matches the format used by Stable Diffusion tools for generation parameters (steps, sampler, seed).",
                )
            )

    # --- XMP ------------------------------------------------------------------
    xmp_text = _find_xmp(data)
    xmp_present = xmp_text is not None
    if xmp_text:
        xmp = _parse_xmp(xmp_text)
        if xmp["creator_tool"]:
            fields["software"].append(MetadataField(key="XMP:CreatorTool", label="Creator tool (XMP)", value=_clip(xmp["creator_tool"])))
            if _GENERATOR_RE.search(xmp["creator_tool"]):
                signals.append(
                    GeneratorSignal(
                        source="XMP CreatorTool",
                        kind="software_string",
                        description="The creator-tool field names a generative AI product.",
                        excerpt=_clip(xmp["creator_tool"])[:80],
                    )
                )
        for agent in xmp["software_agents"]:
            fields["software"].append(MetadataField(key="XMP:softwareAgent", label="Software agent (XMP history)", value=_clip(agent)))
            if _GENERATOR_RE.search(agent):
                signals.append(
                    GeneratorSignal(
                        source="XMP edit history",
                        kind="software_string",
                        description="An entry in the XMP edit history names a generative AI product.",
                        excerpt=_clip(agent)[:80],
                    )
                )
        for dst in xmp["digital_source_types"]:
            info = classify_source_type(dst)
            short = short_source_type(dst) or dst
            fields["software"].append(
                MetadataField(key="XMP:DigitalSourceType", label="Digital source type (XMP)", value=short)
            )
            if info and info[0] in ("ai", "partial_ai"):
                signals.append(
                    GeneratorSignal(
                        source="XMP DigitalSourceType",
                        kind="declared_digital_source_type",
                        description=f"Declares the image as: {info[1].lower()}.",
                        excerpt=short,
                    )
                )

    # --- Format specific: PNG text / generic info -----------------------------------
    text_chunks: dict[str, str] = {}
    if img.format == "PNG":
        for key, value in img.info.items():
            if isinstance(value, str) and key not in ("icc_profile",):
                text_chunks[key] = value
    elif isinstance(img.info.get("comment"), (bytes, str)):
        comment = img.info["comment"]
        text_chunks["comment"] = comment.decode("utf-8", "replace") if isinstance(comment, bytes) else comment
    text_present = bool(text_chunks)

    for key, value in text_chunks.items():
        lower = key.lower()
        if lower == "parameters" and _looks_like_sd_parameters(value):
            signals.append(
                GeneratorSignal(
                    source=f"PNG text chunk '{key}'",
                    kind="generation_parameters",
                    description="Stable Diffusion WebUI style generation parameters (prompt, steps, sampler, seed) are embedded in the file.",
                )
            )
        elif lower in ("prompt", "workflow") and '"class_type"' in value:
            signals.append(
                GeneratorSignal(
                    source=f"PNG text chunk '{key}'",
                    kind="generation_parameters",
                    description="A node-graph workflow in the format used by ComfyUI is embedded in the file.",
                )
            )
        elif lower in ("invokeai_metadata", "invokeai_graph", "sd-metadata", "dream"):
            signals.append(
                GeneratorSignal(
                    source=f"PNG text chunk '{key}'",
                    kind="generation_parameters",
                    description="Metadata in the format written by InvokeAI is embedded in the file.",
                )
            )
        elif lower in ("software", "source", "comment", "description", "title") and _GENERATOR_RE.search(value):
            match = _GENERATOR_RE.search(value)
            signals.append(
                GeneratorSignal(
                    source=f"PNG text chunk '{key}'",
                    kind="software_string",
                    description="A text field names a generative AI product.",
                    excerpt=match.group(0) if match else None,
                )
            )
        if lower == "software":
            fields["software"].append(MetadataField(key="PNG:Software", label="Software (PNG text)", value=_clip(value)))
        elif lower not in ("parameters", "prompt", "workflow") and lower not in (
            "invokeai_metadata", "invokeai_graph", "sd-metadata", "dream", "comment", "description", "title", "author",
        ):
            other_tags.append(f"PNG text: {key}")

    # Software tags in EXIF that name a generator
    for field in fields["software"]:
        if field.key == "Software" and _GENERATOR_RE.search(field.value):
            match = _GENERATOR_RE.search(field.value)
            signals.append(
                GeneratorSignal(
                    source="EXIF Software",
                    kind="software_string",
                    description="The Software field names a generative AI product.",
                    excerpt=match.group(0) if match else None,
                )
            )

    # --- ICC profile -----------------------------------------------------------------
    icc_bytes = img.info.get("icc_profile")
    icc_present = bool(icc_bytes)
    if icc_bytes:
        description = None
        try:
            profile = ImageCms.ImageCmsProfile(io.BytesIO(icc_bytes))
            description = ImageCms.getProfileDescription(profile).strip()
        except Exception:
            description = None
        fields["image"].append(
            MetadataField(key="ICCProfile", label="Color profile", value=_clip(description) if description else "Embedded (unreadable description)")
        )

    # --- Basic image facts -------------------------------------------------------------
    dpi = img.info.get("dpi")
    if isinstance(dpi, tuple) and len(dpi) == 2 and all(isinstance(v, (int, float)) for v in dpi):
        fields["image"].append(MetadataField(key="DPI", label="Resolution", value=f"{dpi[0]:g} × {dpi[1]:g} dpi"))

    groups = [
        MetadataGroup(id=g, label=GROUP_LABELS[g], fields=_dedupe(fields[g]))
        for g in GROUP_ORDER
        if fields[g]
    ]
    any_metadata = bool(exif_present or xmp_present or text_present or icc_present)

    # --- Notes (plain-language interpretation) ---------------------------------------------
    if not exif_present:
        notes.append(
            "No EXIF metadata was found. Messaging apps, social networks, screenshots and editing tools routinely remove it, "
            "and AI-generated images usually do not have it either. Its absence is not evidence for or against AI generation and was not used in the assessment."
        )
    elif camera_present:
        notes.append(
            "Camera make and model are recorded in the file. These fields can be copied between files or edited with common tools, "
            "so they are supporting context, not proof of a genuine capture."
        )
    else:
        notes.append("EXIF metadata is present but does not include a camera make or model.")
    if signals:
        notes.append(
            "Embedded text names generation tooling or declares a synthetic source. Such fields are unauthenticated: they can be added to any file and removed from AI-generated ones."
        )
    if withheld:
        notes.append(
            "Some personal or location fields are present in the file but are not returned or stored by ImageProof: "
            + ", ".join(sorted(set(withheld)))
            + "."
        )

    return MetadataResult(
        any_metadata=any_metadata,
        exif_present=exif_present,
        xmp_present=xmp_present,
        icc_profile_present=icc_present,
        text_chunks_present=text_present,
        camera_make_model_present=camera_present,
        groups=groups,
        generator_signals=_dedupe_signals(signals),
        withheld=sorted(set(withheld)),
        other_tag_names=sorted(set(other_tags))[:40],
        notes=notes,
    )


def _dedupe(items: list[MetadataField]) -> list[MetadataField]:
    seen: set[tuple[str, str]] = set()
    out: list[MetadataField] = []
    for item in items:
        k = (item.key, item.value)
        if k not in seen:
            seen.add(k)
            out.append(item)
    return out


def _dedupe_signals(items: list[GeneratorSignal]) -> list[GeneratorSignal]:
    seen: set[tuple[str, str]] = set()
    out: list[GeneratorSignal] = []
    for item in items:
        k = (item.source, item.description)
        if k not in seen:
            seen.add(k)
            out.append(item)
    return out
