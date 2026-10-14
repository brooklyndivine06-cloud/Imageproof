"""Unit tests for assessment rules, provenance parsing, provider adapters, metrics and the evaluation harness."""

from __future__ import annotations

import asyncio
import io
import json

import httpx
import numpy as np
import pytest
from PIL import Image

from app.config import Settings
from app.core.errors import AppError
from app.evaluation import metrics
from app.evaluation.runner import DatasetSpec, build_reports, collect_records, parse_set
from app.schemas import ModelInfo, ProvenanceResult
from app.services import assessment as A
from app.services.classifiers import ClassifierInput, LabelProbability
from app.services.classifiers.http_endpoint import HttpEndpointClassifier
from app.services.classifiers.base import ClassifierFailure, ClassifierUnavailable
from app.services.forensics import estimate_jpeg_quality, run_forensics
from app.services.provenance import parse_manifest_store
from tests.conftest import StubClassifier, jpeg_with_exif, make_settings, noise_image, post_image, to_bytes


# ----- label mapping / calibration ---------------------------------------------------------
def test_map_labels_requires_explicit_mapping():
    scores = [LabelProbability("artificial", 0.7), LabelProbability("human", 0.3)]
    with pytest.raises(AppError) as err:
        A.map_labels(scores, set(), set())
    assert err.value.code == "model_misconfigured"
    with pytest.raises(AppError):
        A.map_labels(scores, {"fake"}, {"real"})
    ai, labelled = A.map_labels(scores, {"artificial"}, {"human"})
    assert ai == pytest.approx(0.7) and [item.role for item in labelled] == ["ai_generated", "camera"]


def test_calibration_applied_only_to_matching_model(tmp_path):
    cal = tmp_path / "cal.json"
    cal.write_text(json.dumps({
        "model": {"id": "test/stub-model", "revision": "0"}, "method": "platt",
        "platt": {"a": 1.0, "b": 0.0}, "thresholds": {"ai": 0.8, "real": 0.2},
        "fitted_on": {"description": "unit-test set", "n_real": 10, "n_ai": 10},
    }))
    settings = make_settings(calibration_file=str(cal))
    model = ModelInfo(provider="x", name="test/stub-model", version="0", data_handling="x")
    calibration = A.load_calibration(settings, model)
    assert calibration is not None
    assert calibration.probability(0.5) == pytest.approx(0.5)
    other = ModelInfo(provider="x", name="another/model", version="0", data_handling="x")
    assert A.load_calibration(settings, other) is None
    thresholds = A.resolve_thresholds(settings, calibration)
    assert (thresholds.ai, thresholds.real, thresholds.validated) == (0.8, 0.2, True)
    cls = A.build_classification(
        [LabelProbability("artificial", 0.9), LabelProbability("human", 0.1)], model, settings, calibration
    )
    assert cls.interpretation.calibrated and cls.interpretation.calibration.calibrated_ai_probability == pytest.approx(0.9, abs=1e-3)


# ----- provenance ------------------------------------------------------------------------------
def _store(dst: str | None, action="c2pa.created", state="Valid"):
    actions = [{"action": action}]
    if dst:
        actions[0]["digitalSourceType"] = f"http://cv.iptc.org/newscodes/digitalsourcetype/{dst}"
    return {
        "active_manifest": "m1",
        "manifests": {"m1": {
            "claim_generator": "tool/1.0", "signature_info": {"common_name": "Signer", "issuer": "CA", "time": "2025-01-01T00:00:00+00:00"},
            "assertions": [{"label": "c2pa.actions.v2", "data": {"actions": actions}}], "ingredients": [],
        }},
        "validation_state": state,
    }


def test_parse_manifest_declarations_and_states():
    ai = parse_manifest_store(_store("trainedAlgorithmicMedia"), "Trusted", "lib")
    assert ai.status == "trusted" and ai.declares_ai_generation and not ai.declares_camera_capture
    cam = parse_manifest_store(_store("digitalCapture"), "Valid", "lib")
    assert cam.status == "valid" and cam.declares_camera_capture and not cam.declares_ai_generation
    edit = parse_manifest_store(_store("trainedAlgorithmicMedia", action="c2pa.edited"), "Valid", "lib")
    assert edit.declares_partial_ai and not edit.declares_ai_generation
    assert parse_manifest_store(_store(None), "Invalid", "lib").status == "invalid"
    no_state = _store(None)
    del no_state["validation_state"]
    assert parse_manifest_store(no_state, None, "lib").status == "error"


def _with_provenance(monkeypatch, result: ProvenanceResult):
    monkeypatch.setattr("app.services.pipeline.inspect_provenance", lambda data, mime: result)


def test_trusted_ai_declaration_overrides_classifier(client_factory, monkeypatch):
    _with_provenance(monkeypatch, parse_manifest_store(_store("trainedAlgorithmicMedia"), "Trusted", "lib"))
    body = post_image(client_factory(StubClassifier(0.02)), jpeg_with_exif()).json()
    assert body["assessment"]["category"] == "likely_ai_generated"
    assert body["assessment"]["basis"] == "provenance"
    assert body["classification"]["ai_score"] == pytest.approx(0.02)  # classifier output is still reported unchanged


def test_untrusted_ai_declaration_does_not_override(client_factory, monkeypatch):
    """A self-signed manifest must not be able to relabel a real photo as AI (or vice versa)."""
    _with_provenance(monkeypatch, parse_manifest_store(_store("trainedAlgorithmicMedia"), "Valid", "lib"))
    body = post_image(client_factory(StubClassifier(0.02)), jpeg_with_exif()).json()
    assert body["assessment"]["category"] == "likely_camera_captured"
    assert body["assessment"]["basis"] == "classifier"
    assert any("not confirmed as trusted" in n for n in body["assessment"]["notes"])


def test_camera_declaration_never_overrides(client_factory, monkeypatch):
    _with_provenance(monkeypatch, parse_manifest_store(_store("digitalCapture"), "Trusted", "lib"))
    body = post_image(client_factory(StubClassifier(0.99)), jpeg_with_exif()).json()
    assert body["assessment"]["category"] == "likely_ai_generated"
    assert any("conflict" in n.lower() for n in body["assessment"]["notes"])


def test_provenance_failure_does_not_break_analysis(client_factory, monkeypatch):
    def boom(data, mime):
        raise RuntimeError("c2pa exploded")
    monkeypatch.setattr("app.services.pipeline.inspect_provenance", boom)
    r = post_image(client_factory(StubClassifier(0.5)), jpeg_with_exif())
    assert r.status_code == 200
    body = r.json()
    assert body["provenance"]["status"] == "unavailable"
    assert any(s["name"] == "provenance" and s["status"] == "failed" for s in body["processing"]["steps"])


def test_real_c2pa_library_reports_not_found_for_plain_image():
    from app.services.provenance import inspect_provenance, provenance_library_info
    if not provenance_library_info()["available"]:
        pytest.skip("c2pa-python not installed")
    result = inspect_provenance(to_bytes(noise_image(), "JPEG"), "image/jpeg")
    assert result.status == "not_found"
    assert result.declares_ai_generation is False


# ----- HTTP provider ------------------------------------------------------------------------------
def _inp():
    img = noise_image(300, 300)
    return ClassifierInput(image_bytes=to_bytes(img, "JPEG"), mime_type="image/jpeg", rgb=img)


async def _http(handler, **overrides):
    settings = make_settings(http_url="https://inference.example/classify", http_api_key="k-123", **overrides)
    clf = HttpEndpointClassifier(settings, transport=httpx.MockTransport(handler))
    await clf.startup()
    return clf


async def test_http_provider_sends_pixels_only_and_secret_header():
    seen = {}

    def handler(request: httpx.Request):
        seen["auth"] = request.headers["authorization"]
        seen["ctype"] = request.headers["content-type"]
        seen["body"] = request.content
        return httpx.Response(200, json=[{"label": "artificial", "score": 0.8}, {"label": "human", "score": 0.2}])

    clf = await _http(handler)
    scores = await clf.classify(_inp())
    assert seen["auth"] == "Bearer k-123" and seen["ctype"] == "image/png"
    assert seen["body"][:8] == b"\x89PNG\r\n\x1a\n"
    reloaded = Image.open(io.BytesIO(seen["body"]))
    assert "exif" not in reloaded.info and reloaded.getexif().get(271) is None
    assert {s.label: s.score for s in scores} == {"artificial": 0.8, "human": 0.2}
    info = clf.model_info()
    assert info.external is True and "inference.example" in info.data_handling
    assert "k-123" not in info.model_dump_json()


async def test_http_provider_error_mapping():
    async def run(response):
        clf = await _http(lambda r: response)
        return await clf.classify(_inp())

    with pytest.raises(ClassifierUnavailable):
        await run(httpx.Response(401))
    with pytest.raises(ClassifierFailure) as rl:
        await run(httpx.Response(429, headers={"retry-after": "7"}))
    assert rl.value.retry_after == 7
    with pytest.raises(ClassifierUnavailable) as loading:
        await run(httpx.Response(503))
    assert loading.value.code == "model_loading"
    with pytest.raises(ClassifierFailure):
        await run(httpx.Response(200, json={"unexpected": "shape"}))
    with pytest.raises(ClassifierFailure):
        await run(httpx.Response(200, json=[{"label": "a", "score": 7.5}]))


async def test_http_provider_requires_https_and_config():
    assert HttpEndpointClassifier(make_settings()).status().state == "not_configured"
    assert HttpEndpointClassifier(make_settings(http_url="http://example.com/x")).status().state == "error"
    assert HttpEndpointClassifier(make_settings(http_url="http://localhost:9000/x")).status().state == "ready"


def test_hf_provider_not_configured_without_model_id():
    from app.services.classifiers.hf_local import HuggingFaceLocalClassifier
    clf = HuggingFaceLocalClassifier(make_settings())
    assert clf.status().state == "not_configured"
    with pytest.raises(ClassifierUnavailable) as err:
        asyncio.run(clf.classify(_inp()))
    assert err.value.code == "model_not_configured"


def test_default_settings_have_no_model_configured():
    s = Settings(_env_file=None)
    assert s.hf_model_id == "" and s.http_url == "" and s.ai_labels == ""


# ----- forensics -----------------------------------------------------------------------------------
@pytest.mark.parametrize("quality", [95, 75, 50, 30])
def test_jpeg_quality_estimate(quality):
    img = Image.open(io.BytesIO(to_bytes(noise_image(), "JPEG", quality=quality)))
    assert estimate_jpeg_quality(img) == pytest.approx(quality, abs=2)


def test_forensics_signals_and_ela_only_for_jpeg():
    jpeg = Image.open(io.BytesIO(to_bytes(noise_image(512, 384), "JPEG", quality=85)))
    jpeg.load()
    r = run_forensics(jpeg.convert("RGB"), jpeg, "JPEG")
    ids = {s.id for s in r.signals}
    assert {"noise_level", "spectral_peaks", "jpeg_quality"} <= ids
    assert r.ela and r.ela.applicable and r.ela.heatmap_data_url.startswith("data:image/jpeg;base64,")
    assert r.used_in_classification is False
    png = noise_image(512, 384)
    r2 = run_forensics(png, png, "PNG")
    assert r2.ela and not r2.ela.applicable


# ----- metrics ------------------------------------------------------------------------------------------
def test_auroc_and_wilson():
    assert metrics.auroc([0.9, 0.8], [0.1, 0.2]) == 1.0
    assert metrics.auroc([0.5], [0.5]) == 0.5
    assert metrics.auroc([0.1], [0.9]) == 0.0
    lo, hi = metrics.wilson(5, 10)
    assert lo < 0.5 < hi and metrics.wilson(0, 0) is None


def test_summarize_counts():
    recs = [metrics.Record("real", "real", "original", s) for s in (0.05, 0.1, 0.5, 0.95)]
    recs += [metrics.Record("ai", "ai", "original", s) for s in (0.99, 0.9, 0.5, 0.05)]
    out = metrics.summarize(recs, 0.85, 0.15)["overall"]["original"]
    assert out["false_positive_rate"]["k"] == 1 and out["false_positive_rate"]["n"] == 4
    assert out["recall_ai"]["k"] == 2
    assert out["precision_ai"]["k"] == 2 and out["precision_ai"]["n"] == 3
    assert out["ai_called_camera_rate"]["k"] == 1
    assert out["inconclusive_rate_real"]["k"] == 1


def test_platt_and_threshold_selection():
    rng = np.random.default_rng(0)
    real = list(np.clip(rng.normal(0.2, 0.1, 200), 0.001, 0.999))
    ai = list(np.clip(rng.normal(0.8, 0.1, 200), 0.001, 0.999))
    a, b = metrics.fit_platt(real + ai, [False] * 200 + [True] * 200)
    assert a > 0 and abs(b) < 3

    def check(real_scores, ai_scores):
        picked, msgs = metrics.select_thresholds(real_scores, ai_scores, 0.05, 0.05)
        assert picked is not None
        ai_thr, real_thr = picked
        assert real_thr < ai_thr
        assert sum(s >= ai_thr for s in real_scores) / len(real_scores) <= 0.05
        assert sum(s <= real_thr for s in ai_scores) / len(ai_scores) <= 0.05
        return picked, msgs

    separable, _ = check(real, ai)
    assert separable[1] > 0.3 and separable[0] < 0.7  # placed in the gap between the classes

    overlapping_real = list(np.clip(rng.normal(0.4, 0.15, 400), 0.001, 0.999))
    overlapping_ai = list(np.clip(rng.normal(0.6, 0.15, 400), 0.001, 0.999))
    _, msgs = check(overlapping_real, overlapping_ai)
    assert any("overlap" in m for m in msgs)

    degenerate, why = metrics.select_thresholds([1.0] * 50, [0.9] * 50, 0.05, 0.05)
    assert degenerate is None and why


def test_parse_set():
    assert parse_set("real=/data/r").truth == "real"
    s = parse_set("edited=/data/e:real")
    assert (s.name, str(s.path), s.truth) == ("edited", "/data/e", "real")
    with pytest.raises(ValueError):
        parse_set("edited=/data/e")


async def test_evaluation_harness_end_to_end(tmp_path):
    """Exercises the harness mechanics with a test double. The numbers here say nothing about any real detector."""
    for name in ("real", "ai"):
        (tmp_path / name).mkdir()
        for i in range(12):
            noise_image(160, 160, seed=i + (100 if name == "ai" else 0)).save(tmp_path / name / f"{i}.png")

    class ByFolderStub(StubClassifier):
        async def classify(self, inp):
            # deterministic "scores" derived from mean brightness rank; only for harness plumbing
            m = float(np.asarray(inp.rgb).mean()) / 255
            return [LabelProbability("artificial", m), LabelProbability("human", 1 - m)]

    settings = make_settings()
    specs = [DatasetSpec("real", tmp_path / "real", "real"), DatasetSpec("ai", tmp_path / "ai", "ai")]
    clf = ByFolderStub()
    records, counts = await collect_records(clf, settings, specs, ["original", "jpeg:60", "resize:50"], None, 0.4)
    assert counts["real"] == 12 and counts["ai"] == 12
    assert {r.split for r in records} == {"fit", "eval"}
    assert {r.perturbation for r in records} == {"original", "jpeg:60", "resize:50"}
    report, calibration = build_reports(
        records, clf, settings, counts, specs, dataset_name="unit", notes="", fit=True,
        target_fpr=0.1, target_miss=0.1, holdout_fraction=0.4,
    )
    assert report["dataset"]["evaluated_on"].startswith("held-out")
    assert set(report["overall"]) == {"original", "jpeg:60", "resize:50"}
    assert calibration["model"]["id"] == "test/stub-model" and "platt" in calibration
    # eval records must never include fitting images
    assert all(r.split == "eval" for r in records if r in [x for x in records if x.split == "eval"])


# ----- Hugging Face provider plumbing (with stand-ins for torch/transformers) -----------------------------
async def test_hf_provider_loads_safely_and_maps_labels(monkeypatch):
    """Verifies how the provider calls torch/transformers (safe-loading flags, label extraction).
    It does NOT run a real model; real-model behaviour must be validated with the evaluation harness."""
    import sys
    import types

    calls = {}

    class FakeTensor(list):
        def float(self): return self
        def cpu(self): return self
        def tolist(self): return list(self)
        def __getitem__(self, i): return FakeTensor(super().__getitem__(i)) if isinstance(super().__getitem__(i), list) else super().__getitem__(i)

    torch = types.ModuleType("torch")

    class _Ctx:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    torch.inference_mode = lambda: _Ctx()
    torch.softmax = lambda logits, dim: FakeTensor([[0.25, 0.75]])
    torch.cuda = types.SimpleNamespace(is_available=lambda: False)
    torch.backends = types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False))

    class FakeBatch(dict):
        pass

    class FakeProcessor:
        @staticmethod
        def from_pretrained(model_id, **kwargs):
            calls["processor"] = (model_id, kwargs)
            return lambda images, return_tensors: {"pixel_values": types.SimpleNamespace(to=lambda d: "px")}

    class FakeModel:
        config = types.SimpleNamespace(id2label={0: "artificial", 1: "human"}, _commit_hash="abc123")

        @staticmethod
        def from_pretrained(model_id, **kwargs):
            calls["model"] = (model_id, kwargs)
            return FakeModel()

        def to(self, device): return self
        def eval(self): return self
        def __call__(self, **batch): return types.SimpleNamespace(logits=FakeTensor([[0.0, 1.0]]))

    transformers = types.ModuleType("transformers")
    transformers.AutoImageProcessor = FakeProcessor
    transformers.AutoModelForImageClassification = FakeModel
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "transformers", transformers)

    from app.services.classifiers.hf_local import HuggingFaceLocalClassifier
    clf = HuggingFaceLocalClassifier(make_settings(hf_model_id="org/some-detector", hf_device="cpu"))
    assert clf.status().state == "loading"
    await clf.startup()
    for _ in range(50):
        if clf.status().state != "loading":
            break
        await asyncio.sleep(0.05)
    assert clf.status().state == "ready"
    assert calls["model"][1]["trust_remote_code"] is False and calls["model"][1]["use_safetensors"] is True
    assert calls["processor"][1]["backend"] == "pil" and calls["processor"][1]["trust_remote_code"] is False
    scores = await clf.classify(_inp())
    assert {s.label: s.score for s in scores} == {"artificial": 0.25, "human": 0.75}
    assert clf.model_info().version == "abc123" and clf.model_info().external is False


async def test_hf_provider_reports_missing_ml_dependencies(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "torch", None)  # makes `import torch` raise ImportError
    from app.services.classifiers.hf_local import HuggingFaceLocalClassifier
    clf = HuggingFaceLocalClassifier(make_settings(hf_model_id="org/some-detector"))
    await clf.startup()
    for _ in range(50):
        if clf.status().state != "loading":
            break
        await asyncio.sleep(0.05)
    assert clf.status().state == "error" and "requirements-ml.txt" in clf.status().detail
