"""C2PA Content Credentials verification.

Provenance is verified by the open-source C2PA SDK (``c2pa-python``). We report
what the SDK says and explain what that does and does not establish. A missing
manifest is the normal case and is never treated as evidence of anything.
"""

from __future__ import annotations

import io
import json
from importlib import metadata as importlib_metadata
from typing import Any

from app.schemas import ProvenanceAction, ProvenanceResult, ValidationIssue
from app.services.metadata import classify_source_type, short_source_type

MAX_ISSUES = 10
MAX_ACTIONS = 25


def provenance_library_info() -> dict[str, Any]:
    try:
        import c2pa  # noqa: F401
    except Exception as exc:  # ImportError or a native library load failure
        return {"available": False, "library": None, "reason": f"{type(exc).__name__}"}
    try:
        package_version = importlib_metadata.version("c2pa-python")
    except importlib_metadata.PackageNotFoundError:
        package_version = "unknown"
    try:
        sdk = c2pa.sdk_version()
    except Exception:
        sdk = "unknown"
    return {"available": True, "library": f"c2pa-python {package_version} (C2PA SDK {sdk})", "reason": None}


def _unavailable(reason: str) -> ProvenanceResult:
    return ProvenanceResult(
        status="unavailable",
        title="Content Credentials check unavailable",
        summary=(
            "The C2PA verification library is not available on this server, so provenance could not be checked. "
            "This is a limitation of the deployment, not a finding about the image."
        ),
        does_not_establish=["Whether the image has Content Credentials."],
        library=None,
    )


def _not_found(library: str | None) -> ProvenanceResult:
    return ProvenanceResult(
        status="not_found",
        title="No Content Credentials found",
        summary=(
            "The file does not contain an embedded C2PA manifest. Most images do not, and many platforms and editing tools "
            "remove manifests when an image is uploaded or re-encoded, so this says nothing about how the image was made."
        ),
        does_not_establish=[
            "That the image is authentic.",
            "That the image is AI-generated.",
            "That a manifest never existed before the file was re-saved or shared.",
        ],
        library=library,
    )


def _agent_to_str(agent: Any) -> str | None:
    if isinstance(agent, str):
        return agent[:120]
    if isinstance(agent, dict):
        name = agent.get("name")
        version = agent.get("version")
        if name:
            return f"{name} {version}".strip()[:120] if version else str(name)[:120]
    return None


def _parse_actions(active: dict[str, Any]) -> tuple[list[ProvenanceAction], bool, bool, bool]:
    actions: list[ProvenanceAction] = []
    ai_created = partial_ai = camera = False
    for assertion in active.get("assertions", []) or []:
        label = str(assertion.get("label", ""))
        if not label.startswith("c2pa.actions"):
            continue
        data = assertion.get("data", {}) or {}
        entries = list(data.get("actions", []) or [])
        for template in data.get("templates", []) or []:
            if isinstance(template, dict) and template.get("digitalSourceType"):
                entries.append(
                    {"action": f"{template.get('action', 'template')} (template)", "digitalSourceType": template["digitalSourceType"]}
                )
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            action_name = str(entry.get("action", "unknown"))[:80]
            dst = entry.get("digitalSourceType")
            info = classify_source_type(dst) if isinstance(dst, str) else None
            if info:
                category = info[0]
                is_creation = action_name.startswith("c2pa.created")
                if category == "ai":
                    if is_creation:
                        ai_created = True
                    else:
                        partial_ai = True
                elif category == "partial_ai":
                    partial_ai = True
                elif category == "camera" and is_creation:
                    camera = True
            if len(actions) < MAX_ACTIONS:
                actions.append(
                    ProvenanceAction(
                        action=action_name,
                        software_agent=_agent_to_str(entry.get("softwareAgent")),
                        digital_source_type=short_source_type(dst) if isinstance(dst, str) else None,
                        description=info[1] if info else None,
                    )
                )
    return actions, ai_created, partial_ai, camera


def _signer(active: dict[str, Any]) -> tuple[str | None, str | None]:
    info = active.get("signature_info") or {}
    common = info.get("common_name")
    issuer = info.get("issuer")
    if common and issuer and common != issuer:
        signer = f"{common} (issued by {issuer})"
    else:
        signer = common or issuer
    return (str(signer)[:160] if signer else None, info.get("time"))


def _claim_generator(active: dict[str, Any]) -> str | None:
    generator = active.get("claim_generator")
    if generator:
        return str(generator)[:160]
    infos = active.get("claim_generator_info")
    if isinstance(infos, list) and infos and isinstance(infos[0], dict):
        name, version = infos[0].get("name"), infos[0].get("version")
        if name:
            return f"{name} {version}".strip()[:160] if version else str(name)[:160]
    return None


def parse_manifest_store(store: dict[str, Any], state: str | None, library: str | None) -> ProvenanceResult:
    """Convert the SDK's manifest-store JSON into our result. Pure function; unit-tested."""
    active_label = store.get("active_manifest")
    manifests = store.get("manifests", {}) or {}
    active = manifests.get(active_label, {}) if active_label else {}
    state = state or store.get("validation_state")

    actions, ai_created, partial_ai, camera = _parse_actions(active)
    signer, signed_at = _signer(active)
    issues = [
        ValidationIssue(code=str(item.get("code", "unknown"))[:80], explanation=(str(item.get("explanation"))[:200] if item.get("explanation") else None))
        for item in (store.get("validation_status") or [])
        if isinstance(item, dict)
    ][:MAX_ISSUES]

    base = dict(
        validation_state=state,
        signer=signer,
        signed_at=signed_at,
        claim_generator=_claim_generator(active),
        actions=actions,
        ingredients_count=len(active.get("ingredients", []) or []),
        declares_ai_generation=ai_created,
        declares_partial_ai=partial_ai and not ai_created,
        declares_camera_capture=camera,
        issues=issues,
        library=library,
    )

    declared = ""
    if ai_created:
        declared = " The manifest declares that the image was created by a generative AI model."
    elif partial_ai:
        declared = " The manifest records edits that include generative-AI content."
    elif camera:
        declared = " The manifest declares a camera capture as the origin."

    if state == "Trusted":
        return ProvenanceResult(
            status="trusted",
            title="Content Credentials verified, trusted signer",
            summary=(
                "A C2PA manifest is embedded. Its signature and hash bindings validate, and the signing certificate chains to a trust anchor "
                "recognised by the verification library." + declared
            ),
            establishes=[
                "The manifest was signed by the named signer and has not been altered.",
                "The image data matches what was signed (no changes after signing).",
                "The declared actions and source type are the signer's own statements about the asset.",
            ],
            does_not_establish=[
                "That the depicted scene is real or truthful.",
                "That the declarations are correct beyond the signer's own assertion.",
            ],
            **base,
        )
    if state == "Valid":
        return ProvenanceResult(
            status="valid",
            title="Content Credentials found, signer not confirmed as trusted",
            summary=(
                "A C2PA manifest is embedded and its signature and hash bindings validate, but the signer was not confirmed against a trust list. "
                "Anyone can create a validly signed manifest with their own certificate." + declared
            ),
            establishes=[
                "The manifest is internally consistent and unmodified since it was signed.",
                "The image data matches what was signed.",
            ],
            does_not_establish=[
                "Who the signer really is.",
                "That the declarations are correct. They are the signer's own statements.",
                "That the depicted scene is real.",
            ],
            **base,
        )
    if state == "Invalid":
        return ProvenanceResult(
            status="invalid",
            title="Content Credentials found but failed validation",
            summary=(
                "A C2PA manifest is present, but validation failed. For example, the image may have been changed after signing, "
                "or the signature or certificate may be broken. Treat every claim in the manifest as unverified."
            ),
            does_not_establish=[
                "That the declarations in the manifest are true.",
                "Whether the image is authentic or AI-generated.",
            ],
            **base,
        )
    return ProvenanceResult(
        status="error",
        title="Content Credentials could not be evaluated",
        summary="A manifest was found but the library did not return a recognised validation state, so no conclusion is drawn from it.",
        does_not_establish=["Anything about the origin of the image."],
        **base,
    )


def inspect_provenance(data: bytes, mime_type: str) -> ProvenanceResult:
    info = provenance_library_info()
    if not info["available"]:
        return _unavailable(info["reason"] or "import failed")
    import c2pa

    library = info["library"]
    try:
        with io.BytesIO(data) as stream:
            reader = c2pa.Reader.try_create(mime_type, stream)
            if reader is None:
                return _not_found(library)
            try:
                state = reader.get_validation_state()
                store = json.loads(reader.json())
            finally:
                reader.close()
    except c2pa.C2paError.ManifestNotFound:
        return _not_found(library)
    except Exception:
        return ProvenanceResult(
            status="error",
            title="Content Credentials could not be read",
            summary="The file contains data that looks like Content Credentials, but it could not be parsed. No conclusion is drawn from it.",
            does_not_establish=["Anything about the origin of the image."],
            library=library,
        )
    return parse_manifest_store(store, state, library)
