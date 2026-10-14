# ImageProof

An image-authenticity analysis web application. A user uploads an image and receives an assessment of
whether it is **Likely AI-Generated**, **Likely Camera-Captured**, **Inconclusive**, or **Unable to Analyze**,
together with the evidence behind it. Four evidence sources are examined and reported separately:

| Source | What it is | Can it decide the assessment? |
|---|---|---|
| Visual classifier | A pretrained image-classification model scores the pixels | Yes (default basis) |
| Provenance (C2PA) | Cryptographic verification of Content Credentials | Only if the signer is *trusted* **and** declares AI generation |
| Metadata | EXIF, XMP, PNG text chunks, colour profile | No. Shown as context |
| Visual forensics | Noise, Fourier-spectrum, JPEG-quality and error-level measurements | No. Informational |

**Nothing in the app is simulated.** Results come from the configured model and the real analysis modules. If no
model is configured or it is unavailable, the API returns an error and the UI shows *Unable to Analyze*. It never
invents a result.

---

## Read this first: what has and has not been verified

I built and tested this in a sandbox that could reach package registries but **not** Hugging Face or any model
hub, and had no browser. Be clear about what that means:

* **Verified here:** the backend test-suite (51 tests), the frontend test-suite (28 tests), type-checking, linting,
  the production Next.js build, and a live end-to-end run (browser-less, with `curl`) through the Next.js proxy to
  FastAPI to a hosted-endpoint provider. C2PA parsing was checked against a real signed sample image from the
  `c2pa-python` repository.
* **Not verified here:** running a **real detection model**. The self-hosted Hugging Face provider is unit-tested
  against stand-ins for `torch`/`transformers` (it checks the safe-loading flags and label handling), but it has
  not loaded real weights. The end-to-end run used a throwaway mock inference server whose scores mean nothing.
* **Not verified here:** how the UI looks in a real browser (layout, dark mode, mobile). Components were exercised
  with jsdom, and the compiled CSS was inspected, but nobody has looked at the pixels. Expect to do a visual pass.
* **Not verified here:** the Docker files and `docker-compose.yml` (no Docker daemon was available).
* **No accuracy figures are shipped, and none should be quoted.** Accuracy is unknown until you run the
  evaluation harness on data representative of *your* images (see [Evaluation](#evaluation)).

---

## Repository layout

```
imageproof/
├── backend/                    FastAPI service (Python 3.12)
│   ├── app/
│   │   ├── main.py             app factory (uvicorn app.main:create_app --factory)
│   │   ├── config.py           all settings, IMAGEPROOF_* environment variables
│   │   ├── api/v1/routes.py    GET /health, GET /status, POST /analyze
│   │   ├── core/               error envelope, middleware, rate limiter
│   │   ├── services/
│   │   │   ├── validation.py   magic-byte sniffing, safe decoding, limits
│   │   │   ├── metadata.py     EXIF / XMP / PNG text extraction (privacy-minimised)
│   │   │   ├── provenance.py   C2PA verification
│   │   │   ├── forensics.py    noise / spectrum / JPEG quality / ELA
│   │   │   ├── assessment.py   thresholds, calibration, reliability, decision rules
│   │   │   ├── pipeline.py     the analysis workflow
│   │   │   └── classifiers/    replaceable model providers
│   │   └── evaluation/         evaluation + calibration harness (python -m app.evaluation)
│   ├── tests/                  51 tests
│   ├── requirements*.txt, .env.example, Dockerfile
├── frontend/                   Next.js 16 · React 19 · TypeScript · Tailwind CSS 4
│   ├── src/app/                pages + same-origin API proxy (api/v1/[...path]/route.ts)
│   ├── src/components/         analyzer UI, shadcn-style primitives (ui/), site chrome
│   ├── src/lib/                API client, validation, PDF report, summary, local history
│   └── Dockerfile, .env.example
└── docker-compose.yml
```

```
Browser ──HTTPS──▶ Next.js (UI + /api/v1 proxy) ──▶ FastAPI ──▶ classifier provider
                                                         ├─▶ metadata  ├─▶ C2PA  └─▶ forensics
```

The browser only talks to the Next.js origin. The proxy forwards just `analyze`, `status` and `health`, streams
uploads without buffering, and never forwards cookies or authorization headers. The backend address and any
provider API key live only on the server.

---

## Quick start (development)

Requirements: Python 3.12+, Node.js 22.12+.

### 1. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt          # core + test tools
cp .env.example .env
```

At this point the API runs but reports `ready: false` because **no model is enabled**. Enable one:

```bash
# Option A: self-hosted model (images never leave your server)
# CPU-only torch is far smaller than the default Linux wheel:
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-ml.txt
# then edit .env: uncomment IMAGEPROOF_HF_MODEL_ID and IMAGEPROOF_DETECTOR_LICENSE (see "Choosing a model")
```

```bash
uvicorn app.main:create_app --factory --reload --port 8000
```

The first start downloads the weights, so `/api/v1/status` shows `state: "loading"` for a while.

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local        # BACKEND_URL=http://127.0.0.1:8000
npm run dev                       # http://localhost:3000
```

### 3. Tests and checks

```bash
cd backend  && pytest -q && ruff check app tests
cd frontend && npm test && npm run typecheck && npm run lint && npm run build
```

---

## Model configuration

The classifier sits behind an interface (`backend/app/services/classifiers/base.py`). Select a provider with
`IMAGEPROOF_PROVIDER`.

### Provider `huggingface_local` (self-hosted)

Runs a Hugging Face `AutoModelForImageClassification` on your server. Security and reproducibility choices:

* `trust_remote_code=False` always, and `use_safetensors=True`, so loading a model cannot execute code from the repo
  or from a pickle file.
* `IMAGEPROOF_HF_MODEL_REVISION` pins an exact commit. Do this in production. The loaded revision is reported with
  every result.
* `IMAGEPROOF_HF_PROCESSOR_BACKEND=pil` (default) uses the portable Pillow preprocessing path of transformers 5.x,
  which needs no `torchvision` and gives the same preprocessing on every machine.
* `IMAGEPROOF_HF_LOCAL_FILES_ONLY=true` runs fully offline from a pre-populated cache.

### Provider `http_endpoint` (hosted inference)

Posts the image to `IMAGEPROOF_HTTP_URL` and expects a JSON list of `{"label": "...", "score": 0.0-1.0}` objects
(the Hugging Face image-classification response format).

* **The image leaves your server.** The results page, `/api/v1/status` and the Privacy page say so, and name the host.
  The provider applies its own retention policy.
* By default (`IMAGEPROOF_HTTP_PAYLOAD=pixels_png`) only decoded pixels are sent, re-encoded losslessly as PNG, so
  EXIF/GPS/XMP never leave your server. `original` sends the file untouched.
* `https://` is required (plain `http://` only for `localhost`). The API key is read from `IMAGEPROOF_HTTP_API_KEY`
  and sent as `IMAGEPROOF_HTTP_AUTH_HEADER` / `IMAGEPROOF_HTTP_AUTH_SCHEME`. It is never returned by any endpoint.
* Other vendors with other response formats need a small adapter (below). I did not write adapters for specific
  commercial detectors because I could not verify their APIs.

### Adding a provider

```python
# backend/app/services/classifiers/my_provider.py
from app.services.classifiers import ImageClassifier, ClassifierInput, ClassifierStatus, LabelProbability, register_provider

class MyClassifier(ImageClassifier):
    provider_id = "my_provider"
    def status(self) -> ClassifierStatus: ...      # ready / loading / not_configured / error
    def model_info(self): ...                      # name, version, external?, data-handling statement
    async def classify(self, inp: ClassifierInput) -> list[LabelProbability]: ...

@register_provider("my_provider")
def _factory(settings): return MyClassifier(settings)
```

Import the module in `registry._load_builtin()` and set `IMAGEPROOF_PROVIDER=my_provider`. Nothing else changes.

### Label mapping is mandatory

`IMAGEPROOF_AI_LABELS` and `IMAGEPROOF_REAL_LABELS` say which of the model's labels mean "AI-generated" and "real".
The app will not guess. If the configured names don't match what the model returns, requests fail with
`model_misconfigured` rather than produce a wrong verdict. Check the model's `config.json` (`id2label`).

### Choosing a detection model

`.env.example` contains a commented **starter example**, `Organika/sdxl-detector`. Know what you are choosing:

* It is a Swin-based binary classifier whose configured labels are `artificial` and `human` (verify against the
  revision you pin).
* **License: CC-BY-NC-3.0, non-commercial only.** Do not deploy it in a commercial product without permission.
* It was trained to detect Stable Diffusion XL output against photographs. Newer or different generators may pass.
  Published numbers for it come from its own in-distribution validation split and say little about your images.
* ImageProof has **not** evaluated it. Treat it as a way to get the pipeline running, then evaluate whatever
  model you intend to rely on.

Prefer a model whose license, training data and known weaknesses you have read, and evaluate it yourself.

### Thresholds, scores and calibration

* The classifier's score for the AI-labelled output is compared with two thresholds
  (`IMAGEPROOF_AI_THRESHOLD`, default 0.85 and `IMAGEPROOF_REAL_THRESHOLD`, default 0.15). In between: *Inconclusive*.
* **The defaults are conservative guesses, not validated values.** The UI says "configured, not validated".
* A softmax score is **not a probability**. The UI labels it "uncalibrated model score" and shows it as `0.930`, not
  `93%`. It shows a percentage only when a calibration fitted on a labelled dataset is loaded (`IMAGEPROOF_CALIBRATION_FILE`),
  and then it states what the calibration was fitted on.
* A calibration file is applied only if it was produced for exactly the running model (and revision, when known).

---

## Evaluation

`python -m app.evaluation` runs the *configured* classifier over a labelled image folder and writes
`evaluation_report.json` (and optionally `calibration.json`).

```bash
cd backend
python -m app.evaluation \
  --set real=./data/photos            `# camera photographs (truth: real)` \
  --set ai=./data/generated           `# AI-generated images (truth: ai)` \
  --set edited=./data/edited:real     `# retouched camera photos (NAME=PATH:real|ai)` \
  --perturb jpeg:75 --perturb resize:50 --perturb resize:50+jpeg:70 \
  --dataset-name "My validation set v1" \
  --fit-calibration --holdout-fraction 0.3 \
  --target-fpr 0.05 --target-miss 0.05 \
  --out ./reports
```

* Every image is also scored after each perturbation (JPEG re-compression, down-sizing, or chains) so you see the
  effect of compression and resizing.
* With `--fit-calibration`, images are split by a content hash into a **fitting** split and a **held-out** split.
  Thresholds (and Platt scaling) are chosen on the fitting split only; every reported metric is computed on the held-out
  split. The thresholds pick the smallest AI threshold with at most `--target-fpr` real photos flagged, and the largest
  camera threshold with at most `--target-miss` AI images called camera-like. If the classes overlap, the band between them
  becomes *Inconclusive*. If the targets can't be met, thresholds are left unchanged and the report says so.
* Reported: AUROC, **false-positive rate** (real flagged as AI), **recall** and **precision** for AI, inconclusive
  rates, per-category breakdown, each with 95% Wilson intervals.
* Precision depends on how common AI images are in your dataset; recall and false-positive rate do not. The report says so.

Then enable the results:

```env
IMAGEPROOF_CALIBRATION_FILE=/path/to/reports/calibration.json     # validated thresholds + calibrated estimate
IMAGEPROOF_EVALUATION_REPORT=/path/to/reports/evaluation_report.json   # shown on /detection-technology
```

Without an evaluation report the Detection Technology page states that no evaluation exists. You need a dataset of
real photos, AI images, edited photos and processed copies with trustworthy labels. The tool cannot supply one, and it
does not verify your labels.

---

## API

### `POST /api/v1/analyze`

`multipart/form-data` with one field, `file`. Returns `200` with:

| Field | Meaning |
|---|---|
| `analysis_id`, `created_at`, `app_version` | identifier and UTC timestamp |
| `processing` | `status`, total `duration_ms`, per-step status and timings |
| `file` | detected `format`, size, dimensions, colour mode, `sha256` |
| `assessment` | `category` (`likely_ai_generated`, `likely_camera_captured`, `inconclusive`), `basis` (`classifier`/`provenance`), plain-language `summary`, `decision_trace`, `reliability` factors, `notes` (conflicts) |
| `classification` | `model` (name, version, provider, `external`, data handling, license), `ai_score`, per-label scores, `interpretation` (raw vs calibrated), `thresholds` (and whether validated) |
| `evidence_sources` | the four sources, each with status and whether it was used for the assessment |
| `metadata` | allow-listed fields, generator signals, what was withheld |
| `provenance` | C2PA status, validation state, signer, actions, declared origin, what it does / doesn't establish |
| `forensics` | measurements with neutral interpretations, ELA heatmap (JPEG only) |
| `limitations`, `disclaimer` | always present |

Failures use one envelope: `{"error": {"code", "message", "details", "retryable"}, "request_id"}`.

| HTTP | `code` | Meaning |
|---|---|---|
| 400 | `empty_file`, `missing_file`, `malformed_request` | bad request |
| 413 | `file_too_large` | over `IMAGEPROOF_MAX_UPLOAD_MB` |
| 415 | `unsupported_media_type`, `expected_multipart` | not JPEG/PNG/WebP (detected from content) |
| 422 | `corrupt_image`, `image_too_small`, `image_too_large_dimensions`, `animated_not_supported` | undecodable or outside limits |
| 429 | `rate_limited` | `Retry-After` header set |
| 502 | `analysis_failed` | model failed on this request |
| 503 | `model_not_configured`, `model_loading`, `model_unavailable`, `model_misconfigured`, `server_busy` | no result is produced |
| 504 | `analysis_timeout` | exceeded `IMAGEPROOF_ANALYSIS_TIMEOUT_SECONDS` |

*Unable to Analyze* in the UI is any of the 4xx/5xx outcomes above.

### `GET /api/v1/status`
Readiness, model information, thresholds, limits, module availability, evaluation summary and the privacy statement
(including whether images go to an external provider). Contains no secrets.

### `GET /api/v1/health`
Liveness probe.

OpenAPI docs are served at `/docs` unless `IMAGEPROOF_ENVIRONMENT=production`.

---

## Supported formats and limits

| | Default | Setting |
|---|---|---|
| Formats | JPEG, JPG, PNG, WebP (detected from bytes, not file names) | n/a |
| Max file size | 10 MB | `IMAGEPROOF_MAX_UPLOAD_MB` (and `MAX_UPLOAD_MB` in the frontend) |
| Min dimensions | 64 px per side | `IMAGEPROOF_MIN_IMAGE_SIDE` |
| Max pixels | 40 megapixels | `IMAGEPROOF_MAX_IMAGE_PIXELS` |
| Animated images | rejected | n/a |
| Timeout | 60 s | `IMAGEPROOF_ANALYSIS_TIMEOUT_SECONDS` |
| Rate limit | 20 analyses / 10 min / client | `IMAGEPROOF_RATE_LIMIT_*` |

Images under 128 px on the short side are treated as too small for a confident verdict (shown as *Inconclusive*);
images under 256 px, or JPEGs at estimated quality below 50, get a reduced-reliability warning. These cut-offs are
policy heuristics, not empirically derived values.

---

## Decision rules

1. Classifier AI-label score ≥ AI threshold → *Likely AI-Generated*; ≤ camera threshold → *Likely Camera-Captured*;
   otherwise *Inconclusive*.
2. Very low resolution withholds a confident verdict (`IMAGEPROOF_DEGRADE_LOW_RELIABILITY`).
3. Content Credentials with validation state **Trusted** that declare `trainedAlgorithmicMedia` as the creation source
   override the classifier. Credentials that are merely *Valid* (signature intact, signer not on a trust list) are
   shown but never change the category, because anyone can sign a manifest with their own certificate, and that would
   let a forged manifest brand a real photo as fake.
4. Generator strings in metadata, a missing EXIF block or missing credentials never change the category. Conflicts
   (for example metadata naming a generator while the classifier says camera) are flagged to the user.

Whether signers are reported as *Trusted* depends on the trust configuration of the underlying C2PA SDK. In my test
of the SDK's own sample file, the signer was reported as *Valid* with a `signingCredential.untrusted` note.

---

## Privacy and security

Implemented:

* **No persistent storage of uploads.** Uploads are held in memory. Starlette's multipart parser would normally
  spool files above 1 MB to temp files, so `main.py` raises the in-memory threshold to the upload limit. A test asserts no temp
  files are written.
* No image content, file names or metadata in logs: only request id, path, status, duration, and for completed analyses format, size and category. Run uvicorn with `--no-access-log` (the Dockerfile does) to keep client IPs out of server logs.
* **Metadata minimisation:** GPS, serial numbers, owner/author names and image descriptions are detected but withheld.
* Server-side validation by content: size streamed and capped at the ASGI layer (before buffering), magic bytes, full decode, pixel and animation limits, decompression-bomb guard, corrupt/truncated detection.
* Rate limiting per client IP, bounded concurrency with a short queue, per-request timeout, uniform error envelope that never leaks internals.
* Secrets only in server environment variables. `/status` and results never include them (tested).
* Security headers: the frontend sends a CSP, `X-Content-Type-Options`, frame denial and (in production) HSTS; the API sends `nosniff`, frame denial, `Referrer-Policy: no-referrer` and `Cache-Control: no-store`.
* When an external provider is used, that is disclosed in the results, the status endpoint and the Privacy page.
* Local history is opt-in, browser-only, stores a summary only (no image, no metadata), and turning it off deletes it.

Not promised, because the architecture can't guarantee it:

* That memory is wiped after a request, or that your hosting provider, reverse proxy or an external inference provider keeps no logs.
* That an analysis cannot be timed out while a worker thread finishes in the background (Python threads can't be cancelled).

Hardening checklist for operators: serve over HTTPS only; keep the backend off the public network (the compose file
doesn't publish it); set `IMAGEPROOF_TRUSTED_PROXY_COUNT` to the number of proxies that append to `X-Forwarded-For`
in front of the backend, otherwise every user shares one rate-limit bucket; enforce rate limits at your gateway too
(the built-in limiter is per process); keep `MAX_UPLOAD_MB` and `IMAGEPROOF_MAX_UPLOAD_MB` equal; pin the model revision;
keep dependencies updated.

---

## Deployment

```bash
cp backend/.env.example backend/.env      # configure model + limits
docker compose up --build
```

(Untested, see the verification notes at the top.) Put a TLS-terminating reverse proxy in front of port 3000 and set
generous request-body and read timeouts (≥ 65 s) for `/api/v1/analyze`.

Notes:

* Each uvicorn worker loads its own copy of the model. Start with one worker and scale by replicas; the in-process rate
  limiter and concurrency limit are per worker.
* CPU inference of an image classifier takes on the order of a second or more per image depending on the model and
  hardware; set `IMAGEPROOF_MAX_CONCURRENT_ANALYSES` accordingly.
* `BACKEND_URL` and `MAX_UPLOAD_MB` are read by the frontend at request time, so they can change without a rebuild.
* Without Docker: `npm run build && npm start` for the frontend and `uvicorn app.main:create_app --factory --no-access-log` for the backend.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| UI says *Detection model not configured* | `IMAGEPROOF_HF_MODEL_ID` (or `IMAGEPROOF_HTTP_URL`) unset. See `/api/v1/status` |
| `ML dependencies are not installed` | `pip install -r requirements-ml.txt` |
| Status stuck on *loading* | first start is downloading weights; check backend logs. Offline? use `IMAGEPROOF_HF_LOCAL_FILES_ONLY=true` with a pre-filled cache |
| `model_misconfigured` | `IMAGEPROOF_AI_LABELS`/`REAL_LABELS` don't match the model's `id2label` |
| 502 `backend_unreachable` | `BACKEND_URL` wrong or backend down |
| 429 for everyone behind a proxy | set `IMAGEPROOF_TRUSTED_PROXY_COUNT` |
| Provenance shows *unavailable* | no `c2pa-python` wheel for your platform; remove it from `requirements.txt` to silence, or use a supported platform |
| Large uploads fail | proxy/body-size limits in front of the app; keep both `MAX_UPLOAD_MB` values equal |
| Pasted screenshots show no metadata | browsers re-encode pasted images. Upload the original file |

---

## Limitations of detection

No detector can guarantee the origin of every image. In particular: classifiers only know the generators and photographs
they were trained on; compression, resizing, cropping, filters and screenshots change the cues they rely on; real photos
that are heavily processed can be flagged and new generators can pass; AI-*assisted* edits to a real photo are generally
invisible to a whole-image classifier; metadata and unsigned provenance claims can be forged or stripped; and raw scores
are not probabilities. The app says all of this to users on every result. Do not use it as the sole basis for consequential decisions.

---

## Design notes and deliberate omissions

* **No Sign In.** The brief made it optional; accounts would add personal data for no analytical benefit, and a decorative
  button would be dishonest.
* **No demonstration images or example results** are included anywhere. Test fixtures live in `tests/` and `src/test/` only.
* **shadcn/ui:** components in `frontend/src/components/ui/` follow shadcn/ui's conventions (Radix primitives, `cva`, `cn`)
  and `components.json` is included. They were written by hand because the shadcn registry wasn't reachable from my sandbox; you can overwrite them with `npx shadcn@latest add`.
* **PDF reports are generated in the browser** (`jspdf`), so results and the image never make another trip to a server.
  Reports are not tamper-evident.
* **Fonts:** Inter is self-hosted via `@fontsource-variable/inter`, so no request goes to Google Fonts.
* `forensics` measurements deliberately have no verdict: no threshold for them has been validated.
