# Lane F — ML Models Inventory (Reference vs Find)

Read-only discovery. Reference ML = Immich machine-learning service (FastAPI + ONNX Runtime).
Find ML = `backend/src/find_api/ml/` (PyTorch / Ultralytics / InsightFace / Transformers / PaddleOCR, driven by RQ workers + a `ModelManager`).

Cited paths are relative to repo root `C:\Users\abhas\Desktop\Find`.

---

## 1. Reference ML models (Immich)

Reference is built entirely around **ONNX Runtime** (`onnxruntime as ort`) with a pluggable execution-provider stack and downloadable model variants (ONNX / ARMNN / RKNN). It does not run PyTorch at inference time.

### Embedding / search (CLIP)
- **Architecture:** OpenCLIP-family visual + textual encoders, run as ONNX sessions.
  `OpenClipVisualEncoder(BaseCLIPVisualEncoder)` — `reference-app/machine-learning/immich_ml/models/clip/visual.py:61`; runs `self.session.run(...)` (`visual.py:31`). Textual twin in `models/clip/textual.py`.
- **Supported model catalog:** large `_OPENCLIP_MODELS` set incl. RN50/RN101, `ViT-B-16__openai`, `ViT-B-32__openai`, `ViT-L-14*`, and many **SigLIP / SigLIP2** webli variants (e.g. `ViT-B-16-SigLIP__webli`, `ViT-SO400M-14-SigLIP2-378__webli`) — `models/constants.py:4-59`. Multilingual M-CLIP (`_MCLIP_MODELS`, `constants.py:62-67`) and NLLB-CLIP for i18n.
- **Source routing:** `get_model_source()` maps a model name to `OPENCLIP` / `MCLIP` / `INSIGHTFACE` / `PADDLE` — `constants.py:163-178`.
- **Preprocessing** is config-driven from `preprocess_cfg.json` (size/mean/std/interpolation) — `visual.py:46-77`, so swapping CLIP variants needs no code change.

### Facial recognition
- **Detection:** InsightFace **RetinaFace** wrapped over an ONNX session — `models/facial_recognition/detection.py:4,20-25`. Default `min_score=0.7`, `input_size=(640,640)` (`detection.py:16,23`). Output = boxes/scores/landmarks (`detection.py:31-35`).
- **Recognition:** InsightFace **ArcFaceONNX** — `models/facial_recognition/recognition.py:7,40-43`. Emits 512-d face embeddings; supports dynamic batch axis injection into the ONNX graph (`recognition.py:79-87`) and batched inference (`recognition.py:56-64`).
- **Model packs:** `_INSIGHTFACE_MODELS = {antelopev2, buffalo_s, buffalo_m, buffalo_l}` — `constants.py:70-75`. (`buffalo_*` = RetinaFace det + ArcFace recog bundles; `_s` is the CPU-light variant.)

### OCR
- PaddleOCR **PP-OCRv5** server/mobile variants (`_PADDLE_MODELS`, `constants.py:78-89`), also run via ONNX (`models/ocr/detection.py`, `recognition.py`).

### ONNX execution providers (the key asset)
- `SUPPORTED_PROVIDERS` preference order — `constants.py:91-97`:
  `CUDAExecutionProvider → MIGraphXExecutionProvider (ROCm) → OpenVINOExecutionProvider → CoreMLExecutionProvider → CPUExecutionProvider`.
- `OrtSession` auto-selects the **intersection of supported and actually-available** providers, descending preference — `sessions/ort.py:109-113`. This is a clean CUDA→CPU fallback with no code change.
- Per-provider tuned options — `sessions/ort.py:124-168` (CPU arena strategy, CUDA device id, OpenVINO GPU/CPU autodetect + precision, CoreML, MIGraphX fp16 cache).
- **CPU thread tuning:** when running CPU-only it sets `inter_op=1`, `intra_op=2` and arena defaults that "work well for CPU" — `sessions/ort.py:181-203`.

### CPU / quantized / accelerated variants
- **ARMNN** (ARM CPU/GPU) and **RKNN** (Rockchip NPU) model formats selected automatically — `models/base.py:161-176` (`_model_format_default`: RKNN if available, else ARMNN, else ONNX). Format-specific files downloaded via `snapshot_download` with ignore patterns — `base.py:68-79`.
- Dedicated sessions exist: `sessions/ann/loader.py` (ARMNN) and `sessions/rknn/rknnpool.py`.
- OpenVINO precision + ROCm precision (FP32/FP16) are settings — `config.py:75-76`; ANN fp16 turbo flag — `config.py:69`.

---

## 2. Find ML models (today)

Find runs PyTorch/library models in-process, leased through a singleton `ModelManager`. Three modes: `ML_MODE ∈ {full, mock, remote}` — `backend/src/find_api/core/config.py:43`.

| Capability | Library / model | File |
|---|---|---|
| Embedding | **open_clip SigLIP `ViT-B-16-SigLIP` / `webli`**, 768-d | `ml/clip_embedder.py:33-37`; defaults `config.py:50-51,64` |
| Object detection | **Ultralytics YOLO `yolo26n.pt`** (also `yolov10b.pt` at backend root) | `ml/object_detector.py:29`; default `config.py:53` |
| Face detect + recognize | **InsightFace `antelopev2`** via `FaceAnalysis` (det+recog+age/gender in one), 512-d embedding | `ml/face_detector.py:35-40,67` |
| Captioning | **Florence-2-base** (`microsoft/Florence-2-base`, Transformers) | `ml/captioner.py`; default `config.py:52` |
| OCR | **PaddleOCR** (PP-OCR, lang=en, CPU) | `ml/ocr.py:11,20` |
| Clustering / ranking | local (`ml/clusterer.py`, `ml/search_ranking.py`) | — |
| Mock | deterministic fake embedder for tests | `ml/mock_embedder.py` |

### ML interface
- **ModelManager** (`core/model_manager.py`): singleton, lazy `get_model(name, loader, config_key)` + `use_model()` context lease so idle cleanup can't unload mid-inference (`model_manager.py:142-242`). LRU eviction at `ML_MAX_LOADED_MODELS=5` (`config.py:49`, `model_manager.py:340-363`), idle TTL unload `ML_MODEL_IDLE_TTL_SECONDS=300` (`config.py:48`, `model_manager.py:256-291`), `config_key` fingerprint forces reload on config change and gates failure-retry (`model_manager.py:163-177`), per-process status published to Redis (`model_manager.py:324-333`).
- **GPU handling:** simple boolean `USE_GPU` (`config.py:54`); each model picks `cuda` vs `cpu` itself (`clip_embedder.py:31`, `object_detector.py:30,55`, `face_detector.py:27-29`). No execution-provider abstraction, no automatic CUDA→CPU fallback inside ORT (relies on torch / library defaults).
- **Remote ML:** `ML_MODE=remote` offloads to a self-hosted Find ML HTTP server; requires `REMOTE_ML_URL` + `REMOTE_ML_API_KEY` (validated, `config.py:104-118`; `test_remote_ml_config.py`). Feature flags `REMOTE_ML_FEATURES="embed,caption,detect,ocr,cluster"` (`config.py:47`).
- **Hybrid embedding:** `generate_hybrid_embedding()` in `workers/processors.py` blends image + text(caption/label) CLIP vectors; covered by `tests/test_hybrid_embedding.py` (math-only, mocked).

---

## 3. Adopt / Keep / Defer

| Capability | Find today | Reference | Recommendation | Reasoning (CPU latency + license) |
|---|---|---|---|---|
| **ONNX Runtime + EP fallback layer** | none (torch + lib defaults) | `OrtSession` w/ auto provider intersection + CPU thread tuning (`ort.py:109-203`) | **ADOPT (highest value)** | Biggest CPU-mode win. ORT-quantized/ONNX CLIP+ArcFace are far faster and lighter on CPU than torch+open_clip+FaceAnalysis. Gives clean CUDA→CPU→CoreML fallback for free. Apache-2.0 (ORT). |
| **CLIP embedding** | open_clip SigLIP ViT-B-16 (torch, 768-d) | OpenCLIP **ONNX** incl. SigLIP/SigLIP2 + smaller ViT-B-32 (`constants.py:13-58`) | **ADOPT model-as-ONNX; KEEP SigLIP family** | Keep the SigLIP choice (good quality), but run it as ONNX. Optionally offer `ViT-B-32__openai` ONNX as a low-latency CPU default. Models: OpenAI CLIP = MIT; SigLIP/webli weights = Apache-2.0; check per-checkpoint. Re-embeds if dim/model changes → migration cost. |
| **Face detect + recognize** | InsightFace `antelopev2` (`FaceAnalysis`, 512-d) | InsightFace RetinaFace + ArcFaceONNX, packs incl. **`buffalo_s`** (`constants.py:70-75`) | **ADOPT `buffalo_s` (ONNX) for CPU; KEEP antelopev2 for GPU/quality** | `buffalo_s` is markedly faster on CPU than antelopev2 with small accuracy loss; both 512-d ArcFace so embeddings stay compatible-ish (still a re-index). LICENSE FLAG: InsightFace models (antelopev2, buffalo_*) are **non-commercial / research-only** — applies to both apps. |
| **Object detection** | Ultralytics YOLO `yolo26n.pt` | not present (Immich has no object detector) | **KEEP** | Reference offers nothing here. LICENSE FLAG: Ultralytics YOLO is **AGPL-3.0** — matches Find's new AGPL license, so OK for this repo. |
| **OCR** | PaddleOCR PP-OCR (en) | PaddleOCR PP-OCRv5 server/mobile as ONNX (`constants.py:78-89`) | **DEFER → later ADOPT mobile-ONNX** | Same engine family; reference's `PP-OCRv5_mobile` ONNX is the CPU-friendly variant. Low priority. PaddleOCR = Apache-2.0. |
| **Captioning** | Florence-2-base (Transformers) | not present | **KEEP** | Reference has no captioner. Florence-2 = MIT. Heavy on CPU; consider lazy/optional. |
| **Model lifecycle (manager)** | Find `ModelManager` (lease, LRU, TTL, Redis status, remote mode) | Immich `ModelCache` (TTL via `model_ttl`) | **KEEP Find's** | Find's manager is richer (in-flight leasing, failure gating, remote mode). No reason to adopt reference's. |

---

## 4. CPU-mode considerations

- **Find today is torch-first** → on CPU it loads full PyTorch CLIP + InsightFace + (optionally) Florence-2, which is memory-heavy and slow. `USE_GPU=False` just flips device strings; there is no ONNX/quantized path.
- **Reference is ONNX-first** and already solves CPU well:
  - Automatic provider selection = intersection of `SUPPORTED_PROVIDERS` and available (`ort.py:109-113`) → **CUDA→CPU fallback is automatic**, never crashes when CUDA absent.
  - CPU-specific thread tuning (`inter_op=1`, `intra_op=2`, arena strategy) — `ort.py:181-203`.
  - CPU-light model variants ready: **`buffalo_s`** (face), **`ViT-B-32__openai`** (CLIP), **`PP-OCRv5_mobile`** (OCR).
  - Extra CPU/NPU formats (ARMNN, RKNN) auto-selected for ARM/Rockchip hardware — `base.py:161-176`.
- **Recommended CPU default stack for Find:** ORT CPU EP + `ViT-B-32` (or SigLIP-B-16) CLIP ONNX + `buffalo_s` face ONNX. This is the single biggest latency/memory win and the top adopt candidate.

## 5. License notes (flags)

- **InsightFace models** (`antelopev2`, `buffalo_*`): **non-commercial / research-only** — already a risk in Find today (it ships `antelopev2`), not introduced by adoption. Worth flagging for an AGPL open-source app; an Apache/MIT face model may be preferable long-term.
- **Ultralytics YOLO** (`yolo26n.pt`, `yolov10b.pt`): **AGPL-3.0** — consistent with Find's relicense to AGPL-3.0 (commit 639b6ec). OK in-repo; downstream redistributors inherit AGPL.
- **CLIP weights:** OpenAI CLIP = MIT; OpenCLIP/SigLIP webli = Apache-2.0 (verify per checkpoint). Low risk.
- **PaddleOCR / PP-OCR:** Apache-2.0. Low risk.
- **Florence-2:** MIT. Low risk.
- **ONNX Runtime:** MIT/Apache-2.0. Low risk.

## 6. Effort estimates

| Adoption | Size | Notes |
|---|---|---|
| ORT session wrapper + EP fallback (port `OrtSession` concept, not verbatim) into Find's ModelManager | **M** | New session abstraction + provider selection; integrate with existing `use_model`/`config_key`. |
| CLIP → ONNX (SigLIP B-16 and/or ViT-B-32 CPU default) | **M** | Export/obtain ONNX + preprocess_cfg; re-embed library (migration). Embedding dim change = full re-index. |
| Face → `buffalo_s` ONNX (CPU) with antelopev2 GPU fallback | **M** | Both ArcFace 512-d; swap detector/recognizer to ONNX; re-index face vectors. |
| OCR → PP-OCRv5_mobile ONNX | **S–M** | Same engine; lower priority (Defer). |
| Keep YOLO / Florence-2 / ModelManager | **S** (no-op) | No change. |

**Cross-cutting risk:** any embedding model swap forces a re-embed/re-index of existing photos and faces; sequence behind a migration plan.

## 7. Measuring current footprint

Actual on-disk sizes, loaded state, and device for each model currently in
Find are measured by
[`model_footprint_report.py`](../../guides/model-footprint.md), not
estimated by hand — run it before proposing pack sizes or installer
download budgets.
