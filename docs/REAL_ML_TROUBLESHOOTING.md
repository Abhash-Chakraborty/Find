# Real ML Troubleshooting Guide

This guide helps contributors debug caption generation, OCR extraction, object detection, and search relevance issues while running Find in full ML mode.

## Full ML Mode vs Mock Mode

Find supports two processing modes:

### Mock Mode

* Uses lightweight/sample metadata
* Faster startup and testing
* Does not reflect real caption/OCR/search quality
* Useful for UI development and quick frontend testing

### Full ML Mode

* Runs real captioning, OCR, embeddings, and object detection pipelines
* Downloads and loads ML models
* Produces realistic captions and search results
* Required when debugging ML quality issues

If captions or OCR appear unrealistic or static across images, verify that the app is not running in mock mode.

---

# Starting the Full Stack

Start the backend:

```bash
cd backend
uvicorn find_api.main:app --reload
```

Start the worker process:

```bash
python -m find_api.workers.jobs
```

Start the frontend:

```bash
cd frontend
pnpm dev
```

Open the app:

```text
http://localhost:3000
```

---

# Checking Worker Logs

Most caption/OCR failures appear in worker logs.

Watch logs while uploading images:

```bash
python -m find_api.workers.jobs
```

Common failure indicators:

* model download failures
* CUDA/GPU unavailable
* OCR extraction errors
* empty caption outputs
* inference timeout errors

If the Gallery UI only shows "No caption generated yet", check worker logs first before debugging the frontend.

---

# Caption Troubleshooting

If captions are missing or incorrect:

## Verify the image processed successfully

Check:

* processing status
* worker logs
* image metadata in Gallery

## Common causes

* Florence-2 model failed to load
* empty inference response
* unsupported/corrupted image
* model download interruption

## Validation checklist

Upload:

* a landscape image
* an indoor object image
* a screenshot with text
* a people/street image

Expected behavior:

* captions should differ across images
* captions should not remain empty after indexing
* captions should improve search relevance

---

# OCR Troubleshooting

OCR issues are easiest to reproduce with:

* screenshots
* receipts
* documents
* UI images

Expected behavior:

* searchable extracted text
* text-heavy images appear in relevant searches

Common issues:

* OCR dependency missing
* low-resolution images
* unsupported text orientation
* OCR exceptions hidden in worker logs

---

# Object Detection Validation

Upload images containing:

* vehicles
* animals
* household objects
* multiple visible items

Verify:

* detected labels appear correctly
* search can find detected objects
* indexing completes without silent failure

---

# Search Quality Validation

Test searches using:

* caption phrases
* visible OCR text
* object names
* unrelated keywords

Expected behavior:

* related images rank higher
* OCR text influences search
* captions improve semantic matching

If unrelated images dominate results:

* verify embeddings completed successfully
* verify captions are non-empty
* check worker logs for failed ML stages

---

# Common GPU / Model Issues

## CUDA unavailable

The app may silently fall back to CPU mode.

Check:

```bash
nvidia-smi
```

## Slow first startup

Initial model downloads may take several minutes.

## Out-of-memory errors

Large models may fail on low-memory GPUs.

Possible fixes:

* reduce parallel workers
* retry after model cache completes
* use CPU fallback temporarily

---

# Recommended Test Images

Useful manual test set:

* landscape photo
* meme/screenshot with text
* receipt/document image
* crowded street image
* pet/animal image
* blurry low-quality image

These help validate:

* captions
* OCR
* embeddings
* search quality
* object detection

---

# Related Documentation

* README.md
* CONTRIBUTING.md
* GSSOC_CONTRIBUTOR_GUIDE.md

This guide complements the existing setup documentation with focused ML debugging workflows for contributors.
