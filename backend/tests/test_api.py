"""Upload and API behaviour."""

from __future__ import annotations

import io

from PIL import Image

from tests.conftest import (
    StubClassifier,
    jpeg_with_exif,
    noise_image,
    post_image,
    to_bytes,
)
from app.services.classifiers.base import ClassifierFailure, ClassifierUnavailable


def test_health_and_status(client_factory):
    client = client_factory()
    assert client.get("/api/v1/health").json() == {"status": "ok"}
    body = client.get("/api/v1/status").json()
    assert body["ready"] is True
    assert body["limits"]["formats"] == ["JPEG", "PNG", "WEBP"]
    assert body["privacy"]["stores_uploads"] is False
    assert body["classifier"]["thresholds"]["validated"] is False
    assert body["evaluation"]["status"] == "none"


def test_status_never_exposes_secrets(client_factory):
    client = client_factory(http_api_key="super-secret-key-123", http_url="https://example.invalid/x")
    assert "super-secret-key-123" not in client.get("/api/v1/status").text


def test_security_headers_and_request_id(client_factory):
    r = client_factory().get("/api/v1/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-request-id"]


def test_analyze_returns_structured_result(client_factory):
    client = client_factory(StubClassifier(ai_score=0.97))
    r = post_image(client, jpeg_with_exif())
    assert r.status_code == 200, r.text
    body = r.json()
    for key in (
        "analysis_id", "created_at", "processing", "file", "assessment", "classification",
        "evidence_sources", "metadata", "provenance", "forensics", "limitations", "disclaimer",
    ):
        assert key in body
    assert body["assessment"]["category"] == "likely_ai_generated"
    assert body["assessment"]["basis"] == "classifier"
    c = body["classification"]
    assert c["ai_score"] == 0.97
    assert c["interpretation"]["calibrated"] is False
    assert c["interpretation"]["score_type"] == "raw_softmax"
    assert c["thresholds"]["validated"] is False
    assert c["model"]["external"] is False
    assert [s["id"] for s in body["evidence_sources"]] == ["classifier", "metadata", "provenance", "forensics"]
    assert body["file"]["format"] == "JPEG" and len(body["file"]["sha256"]) == 64
    assert all(s["status"] in ("completed", "skipped") for s in body["processing"]["steps"])


def test_category_thresholds(client_factory):
    cases = {0.99: "likely_ai_generated", 0.85: "likely_ai_generated", 0.5: "inconclusive",
             0.15: "likely_camera_captured", 0.01: "likely_camera_captured"}
    for score, expected in cases.items():
        client = client_factory(StubClassifier(ai_score=score))
        body = post_image(client, to_bytes(noise_image(512, 512), "JPEG", quality=92)).json()
        assert body["assessment"]["category"] == expected, score


def test_missing_metadata_never_makes_image_ai(client_factory):
    """Same pixels with and without EXIF must get the same category from the same classifier output."""
    img = noise_image(400, 300, seed=3)
    with_exif = jpeg_with_exif()
    plain = to_bytes(img, "JPEG", quality=90)
    for score in (0.05, 0.5):
        client = client_factory(StubClassifier(ai_score=score))
        a = post_image(client, with_exif).json()
        b = post_image(client, plain).json()
        assert a["assessment"]["category"] == b["assessment"]["category"]
        assert b["metadata"]["exif_present"] is False
        assert any("not evidence" in n for n in b["metadata"]["notes"])
        assert b["evidence_sources"][1]["status"] == "not_found"


def test_exif_extracted_and_private_fields_withheld(client_factory):
    body = post_image(client_factory(), jpeg_with_exif(make="Canon", model="EOS R5")).json()
    meta = body["metadata"]
    assert meta["exif_present"] and meta["camera_make_model_present"]
    fields = {f["key"]: f["value"] for g in meta["groups"] for f in g["fields"]}
    assert fields["Make"] == "Canon" and fields["Model"] == "EOS R5"
    assert fields["ExposureTime"] == "1/250 s"
    assert fields["FNumber"] == "f/1.8"
    assert "GPS location" in meta["withheld"]
    assert "GPSInfo" not in str(meta)


def test_generator_parameters_are_separate_evidence_not_a_verdict(client_factory):
    png = Image.new("RGB", (256, 256), (120, 130, 140))
    from PIL.PngImagePlugin import PngInfo
    info = PngInfo()
    info.add_text("parameters", "a cat\nSteps: 20, Sampler: Euler a, CFG scale: 7, Seed: 1")
    data = to_bytes(png, "PNG", pnginfo=info)
    body = post_image(client_factory(StubClassifier(0.05)), data, "x.png", "image/png").json()
    assert body["metadata"]["generator_signals"], "generator parameters should be reported"
    assert body["assessment"]["category"] == "likely_camera_captured"  # classifier decides
    assert any("conflict" in n.lower() for n in body["assessment"]["notes"])
    assert body["evidence_sources"][1]["used_in_classification"] is False


def test_provenance_not_found_is_neutral(client_factory):
    body = post_image(client_factory(), jpeg_with_exif()).json()
    assert body["provenance"]["status"] in ("not_found", "unavailable")
    assert body["assessment"]["basis"] == "classifier"


def test_png_and_webp_supported(client_factory):
    client = client_factory(StubClassifier(0.5))
    img = noise_image(300, 300)
    for fmt, mime in (("PNG", "image/png"), ("WEBP", "image/webp")):
        r = post_image(client, to_bytes(img, fmt), f"x.{fmt.lower()}", mime)
        assert r.status_code == 200, (fmt, r.text)
        assert r.json()["file"]["format"] == fmt


def test_format_detected_from_content_not_filename(client_factory):
    r = post_image(client_factory(), to_bytes(noise_image(), "PNG"), "pretend.jpg", "image/jpeg")
    assert r.status_code == 200
    assert r.json()["file"]["format"] == "PNG"


def test_unsupported_formats_rejected(client_factory):
    client = client_factory()
    gif = to_bytes(noise_image(100, 100), "GIF")
    r = post_image(client, gif, "a.gif", "image/gif")
    assert r.status_code == 415 and r.json()["error"]["code"] == "unsupported_media_type"
    r = post_image(client, b"just some text, not an image", "a.jpg", "image/jpeg")
    assert r.status_code == 415
    assert r.json()["request_id"]


def test_empty_file_rejected(client_factory):
    r = post_image(client_factory(), b"")
    assert r.status_code == 400 and r.json()["error"]["code"] == "empty_file"


def test_corrupt_and_truncated_images_rejected(client_factory):
    client = client_factory()
    good = to_bytes(noise_image(400, 300), "JPEG", quality=90)
    r = post_image(client, good[: len(good) // 2])
    assert r.status_code == 422 and r.json()["error"]["code"] == "corrupt_image"
    r = post_image(client, b"\xff\xd8\xff\xe0" + b"\x00" * 64)
    assert r.status_code == 422 and r.json()["error"]["code"] == "corrupt_image"


def test_oversized_file_rejected_with_content_length(client_factory):
    client = client_factory(max_upload_mb=0.05)
    big = to_bytes(noise_image(800, 800), "PNG")
    assert len(big) > 120_000
    r = post_image(client, big, "big.png", "image/png")
    assert r.status_code == 413 and r.json()["error"]["code"] == "file_too_large"


def test_oversized_streaming_body_rejected_without_content_length(client_factory):
    client = client_factory(max_upload_mb=0.05)
    boundary = "xBOUNDARYx"
    payload = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.png"\r\nContent-Type: image/png\r\n\r\n'.encode()
        + b"\x89PNG\r\n\x1a\n" + b"0" * 2_000_000 + f"\r\n--{boundary}--\r\n".encode()
    )

    def chunks():
        for i in range(0, len(payload), 65536):
            yield payload[i : i + 65536]

    r = client.post("/api/v1/analyze", content=chunks(), headers={"content-type": f"multipart/form-data; boundary={boundary}"})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "file_too_large"


def test_too_small_and_too_many_pixels(client_factory):
    r = post_image(client_factory(), to_bytes(noise_image(32, 32), "PNG"), "s.png", "image/png")
    assert r.status_code == 422 and r.json()["error"]["code"] == "image_too_small"
    client = client_factory(max_image_pixels=50_000)
    r = post_image(client, to_bytes(noise_image(400, 400), "PNG"), "b.png", "image/png")
    assert r.status_code == 422 and r.json()["error"]["code"] == "image_too_large_dimensions"


def test_animated_images_rejected(client_factory):
    frames = [noise_image(100, 100, seed=i) for i in range(3)]
    buf = io.BytesIO()
    frames[0].save(buf, "WEBP", save_all=True, append_images=frames[1:], duration=100)
    r = post_image(client_factory(), buf.getvalue(), "a.webp", "image/webp")
    assert r.status_code == 422 and r.json()["error"]["code"] == "animated_not_supported"


def test_missing_file_field_and_wrong_content_type(client_factory):
    client = client_factory()
    r = client.post("/api/v1/analyze", data={"other": "x"}, files={"unrelated": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 400 and r.json()["error"]["code"] == "missing_file"
    r = client.post("/api/v1/analyze", json={"file": "abc"})
    assert r.status_code == 415 and r.json()["error"]["code"] == "expected_multipart"


def test_classifier_not_configured_returns_error_not_a_fake_result(client_factory):
    stub = StubClassifier(state="not_configured")
    client = client_factory(stub)
    r = post_image(client, jpeg_with_exif())
    assert r.status_code == 503
    body = r.json()
    assert body["error"]["code"] == "model_not_configured"
    assert "assessment" not in body
    assert stub.calls == 0
    assert client.get("/api/v1/status").json()["ready"] is False


def test_classifier_loading_is_retryable(client_factory):
    r = post_image(client_factory(StubClassifier(state="loading")), jpeg_with_exif())
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "model_loading" and r.json()["error"]["retryable"] is True


def test_classifier_unavailable_and_failure_mapped(client_factory):
    r = post_image(client_factory(StubClassifier(error=ClassifierUnavailable("down"))), jpeg_with_exif())
    assert r.status_code == 503 and r.json()["error"]["code"] == "model_unavailable"
    r = post_image(client_factory(StubClassifier(error=ClassifierFailure("boom", retryable=True))), jpeg_with_exif())
    assert r.status_code == 502 and r.json()["error"]["code"] == "analysis_failed"
    r = post_image(client_factory(StubClassifier(error=RuntimeError("secret internals"))), jpeg_with_exif())
    assert r.status_code == 500 and "secret internals" not in r.text


def test_timeout_returns_504(client_factory):
    client = client_factory(StubClassifier(delay=1.0), analysis_timeout_seconds=0.2)
    r = post_image(client, jpeg_with_exif())
    assert r.status_code == 504 and r.json()["error"]["code"] == "analysis_timeout"


def test_rate_limit(client_factory):
    client = client_factory(rate_limit_requests=2, rate_limit_window_seconds=60)
    data = jpeg_with_exif()
    assert post_image(client, data).status_code == 200
    assert post_image(client, data).status_code == 200
    r = post_image(client, data)
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1


def test_low_resolution_withholds_confident_verdict(client_factory):
    client = client_factory(StubClassifier(ai_score=0.99))
    body = post_image(client, to_bytes(noise_image(100, 100), "PNG"), "s.png", "image/png").json()
    assert body["assessment"]["category"] == "inconclusive"
    assert body["assessment"]["reliability"]["level"] == "low"


def test_uploads_are_not_written_to_disk(client_factory, tmp_path, monkeypatch):
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    client = client_factory(max_upload_mb=3)
    big = to_bytes(noise_image(1000, 1000, seed=5), "PNG")  # > 1 MB: would spool to disk with Starlette defaults
    assert len(big) > 1_048_576
    assert post_image(client, big, "big.png", "image/png").status_code == 200
    assert list(tmp_path.iterdir()) == []
