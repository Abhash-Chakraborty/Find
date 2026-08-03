# CPU-Only Runtime Profile

- **Status:** Buildable and measured. Model selection is still the GPU-era set — see
  [What this profile is not](#what-this-profile-is-not).
- **Related:** Issue #339. Model-quality selection for the pack still depends on #340 (embeddings)
  and #343 (captioning), both open. #341 (OCR variants) has already reported.

A production-capable runtime between `ML_MODE=mock` and the CUDA stack. It runs real inference —
embeddings, captions, OCR, object detection, and faces — on an ordinary laptop, with no CUDA wheels
and no NVIDIA device.

```bash
docker compose -f compose.cpu.yml up --build
```

## What you get

| | No-AI | Mock (`compose.mock.yml`) | **CPU (`compose.cpu.yml`)** | GPU (`compose.yml`) |
| --- | --- | --- | --- | --- |
| ML results | None | Fabricated | **Real** | Real |
| CUDA wheels | No | No | **No** | Yes |
| NVIDIA device | Not needed | Not needed | **Not needed** | Required |
| Image size | 447 MB | 582 MB | **3.6 GB** | 12 GB |

Sizes are the container filesystem (`du -sx /`), measured the same way for every profile. Do not use
the `docker images` SIZE column to compare these: it reports compressed or uncompressed totals
depending on how the image reached the local store, and gave 1.11 GB and 4.94 GB for the *same* CPU
image on this machine. The GPU figure is from a locally built image and is indicative only.

The CPU image installs `torch==2.9.1+cpu` and `onnxruntime` (not `onnxruntime-gpu`) from
PyTorch's CPU index. Verified in the built image:

```text
torch 2.9.1+cpu   cuda_available False   torch.version.cuda None
torchvision 0.24.1+cpu
```

## Hardware minimums

Measured on the reference machine below. Treat these as the floor, not a target.

| | Minimum | Comfortable |
| --- | --- | --- |
| CPU cores | 4 | 8+ |
| RAM available to the container | 6 GB | 8 GB+ |
| Free disk (image + weights) | 8 GB | 12 GB+ |

RAM is the binding constraint, not CPU. All five stages resident in one worker process peak at
3.1–3.3 GB, and that is before Postgres, Redis, MinIO, and the Next.js frontend take their share. On
a machine with 8 GB total, run the CPU profile without the frontend container or expect swapping.

Disk needs room for the 3.6 GB image plus 3.4 GB of model weights fetched on first run, which land
in Docker volumes rather than in the image.

## Measured cost

Reference machine: 4 CPU cores, 5.8 GB available to Docker, WSL2 on Windows 11, `FIND_BUILD_PROFILE=cpu`,
`ML_MODE=full`, `ACCEL_MODE=cpu`, `torch.get_num_threads() == 3`. **Runs on different hardware are
not comparable and must not share this table.** Reproduce with:

```bash
docker compose -f compose.cpu.yml run --rm worker \
    python scripts/cpu_profile_report.py --images 10 --out cpu-profile.json
```

Three runs, 10 images each. Median across runs, with the p50 spread shown so a single-run ordering
is not mistaken for a real difference.

| Stage | Model | p50 | p50 range | p95 | RSS added | Load |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Embedding | SigLIP ViT-B-16 | 363 ms | 354–367 | 437 ms | 1351 MB | 20.1 s |
| Objects | YOLO26n | 113 ms | 113–128 | 132 ms | 81 MB | 1.7 s |
| OCR | PP-OCRv5 mobile | 3543 ms | 3362–3617 | 3828 ms | 504 MB | 2.9 s |
| Caption | BLIP base | 2333 ms | 2318–2345 | 2610 ms | 1059 MB | 0.5 s |
| Faces | antelopev2 | 137 ms | 134–137 | 147 ms | 335 MB | ~0 s |
| **All five, sequential** | | **6.5 s** | | | | |

| Memory | |
| --- | --- |
| Idle RSS (process started, no model loaded) | 68 MB |
| Peak RSS (all five stages resident) | 3.1–3.3 GB |

A fourth run was discarded rather than averaged in: it was taken while the backend test suite was
running on the same 4-core host, and embedding p50 came out at 3352 ms against 363 ms here — a 9×
inflation from CPU contention alone. On a machine this size, *anything* else running invalidates the
numbers. That is also the honest read on the table above: these are lightly-loaded figures, and a
real worker processing an upload queue will not see them.

**OCR and captioning are 91% of per-image cost** — 5876 ms of 6489 ms. Embedding, detection, and
faces together come to 613 ms, which OCR alone beats by 5.8× and captioning by 3.8×. Any CPU
optimisation effort that does not target those two stages is not worth doing.

### How to read the latency column

`p50` and `p95` are steady-state, after a warm-up pass. First-call cost is reported separately and
**includes downloading the weights**, because every loader in `find_api/ml/` is lazy — the model is
fetched on first use, not at construction. That is why `load_ms` is near zero for some stages and
`first_call_ms` is in the tens of seconds: the work moved, it did not disappear.

Inputs are synthetic 1024×1024 images with rendered shapes and text. Latency and RSS are real; the
*content* of captions and detections is not representative, so this measures cost, never quality.

## What this profile is not

**The models are the GPU-era defaults, run on CPU.** SigLIP ViT-B-16, BLIP base, YOLO26n,
PP-OCRv5-mobile, and antelopev2 were chosen for a CUDA stack. A genuinely CPU-optimised pack —
quantised ONNX variants, smaller backbones — is a separate question, tracked as `proposed_cpu` in
`find_api/core/model_footprint.py` and blocked on the model benchmarks in #340 and #343. Adopting
different defaults without those numbers would be a guess.

The practical consequence is in the table above: OCR costs 5.8× and captioning 3.8× what embedding,
detection, and faces cost combined. That is where a CPU-targeted model pack would pay off. #343 is
measuring the captioning half; #341 has already reported on OCR variants. Embedding (#340) is the
*cheapest* torch stage on CPU at 363 ms, so a smaller backbone there buys comparatively little —
worth knowing before that work is prioritised on GPU-era intuitions.

## Fallback behaviour

- **No CUDA present.** `ACCEL_MODE=cpu` and `USE_GPU=false` are set by `compose.cpu.yml`, so
  nothing probes for a device it will not find. `find_api.core.hardware` resolves the execution plan
  and `GET /api/status/models` reports the active runtime and per-process loaded models.
- **oneDNN kernels unusable.** PaddlePaddle 3.3.1 raises `NotImplementedError` from its oneDNN
  instruction path on the first prediction (`ConvertPirAttribute2RuntimeAttribute not support
  [pir::ArrayAttribute<pir::DoubleAttribute>]`), which takes down every OCR call. `OCRExtractor`
  probes once at load and reloads with `enable_mkldnn=False` when that happens; OCR is slower but
  functional. PaddlePaddle 3.2.x is unaffected, so this is a version regression rather than a
  CPU-profile quirk, and it applies to the GPU image too once that is rebuilt from the current lock.
- **A stage fails to load.** Each ML stage is loaded independently by `ModelManager`, so one
  unavailable model degrades that stage rather than the pipeline. Idle models are evicted after
  `ML_MODEL_IDLE_TTL_SECONDS` (default 300), which is what keeps steady-state RSS below the peak in
  the table.

## Model cache

Weights are fetched on first use and persisted in Docker volumes. **Three separate volumes are
required**, because two of the stacks ignore XDG cache paths:

| Volume | Path | Holds |
| --- | --- | --- |
| `model_cache` | `/root/.cache` | Hugging Face (SigLIP, BLIP), Torch hub |
| `paddlex_cache` | `/root/.paddlex` | PP-OCRv5 detection and recognition models |
| `insightface_cache` | `/root/.insightface` | antelopev2 face models |

Mounting only `/root/.cache` — which is what `compose.cpu.yml` did before this was measured — leaves
the OCR and face weights in the container's writable layer, so every `compose up` that recreates the
container re-downloads them. The symptom is that "first run is slow" never stops being true.

The effect is not marginal. First-call time for each stage, across three runs on the same machine:

| Run | `/root/.paddlex` + `/root/.insightface` | OCR first call | Faces first call |
| --- | --- | ---: | ---: |
| 1 | not mounted | 169.7 s | 154.1 s |
| 2 | mounted, empty | 28.9 s | 86.7 s |
| 3 | mounted, populated | **9.9 s** | **3.8 s** |

Run 1 is what a user hits on every container recreate without these mounts. Run 3 is what they
should hit after the first one. Weights total 3.4 GB across the three volumes: 2.7 GB in
`model_cache`, 752 MB in `insightface_cache`, 28 MB in `paddlex_cache`.

> `compose.yml` (the GPU profile) still mounts only `/root/.cache` and has the same gap. It is left
> alone here because #339 scopes to the CPU profile and requires the GPU profile stay unchanged.

Inspect what is actually cached, without downloading anything:

```bash
docker compose -f compose.cpu.yml run --rm worker \
    python scripts/model_footprint_report.py
```

## References

- `backend/scripts/cpu_profile_report.py` — the measurement tool that produced the table above
- `backend/scripts/model_footprint_report.py` — what each model downloads and caches
- `backend/src/find_api/core/hardware.py` — capability detection and execution planning
- `backend/src/find_api/core/model_footprint.py` — pack definitions, including `proposed_cpu`
- `docs/guides/hardware-acceleration.md` — acceleration modes across all profiles
