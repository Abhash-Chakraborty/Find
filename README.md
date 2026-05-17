# Find

**A local-first AI-powered image search engine**  
Apni photos ko **natural language** mein search karo — 100% private aur self-hosted.

<p align="center">
  <a href="https://gssoc.girlscript.org/">
    <img src="https://img.shields.io/badge/GSSoC-2026-ff4f8b?style=for-the-badge" alt="GSSoC 2026">
  </a>
  <a href="./LICENSE">
    <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License MIT">
  </a>
</p>

---

## हिंदी में (Hindi) 🇮🇳

**Find** एक **लोकल-फर्स्ट AI इमेज इंटेलिजेंस प्लेटफॉर्म** है।

आप अपनी पुरानी तस्वीरों को **प्राकृतिक भाषा** में आसानी से ढूंढ सकते हैं, जैसे:
- "family beach trip 2024"
- "birthday cake cutting photos"
- "mountain sunrise with friends"
- "office team group photo"

**सब कुछ आपके अपने कंप्यूटर पर** — कोई डेटा बाहर नहीं जाता, पूरी तरह **प्राइवेट**।

### मुख्य विशेषताएँ
- इमेज या ZIP फाइल अपलोड
- ऑटो कैप्शन, ऑब्जेक्ट डिटेक्शन, OCR & मेटाडेटा
- सिमेंटिक सर्च (मतलब समझकर)
- समान फोटोज को ऑटो क्लस्टर करना
- Rich गैलरी + Like, Delete, Details
- पूरी तरह Self-hosted

**GSSoC'26** के सभी भारतीय स्टूडेंट्स का हार्दिक स्वागत है! 🎉

---

## What it does

- Upload individual images or ZIP archives
- Extract captions, objects, OCR text, EXIF metadata
- Generate hybrid embeddings for semantic search
- Automatically cluster similar images
- Browse rich gallery with search, clusters, likes & details

## Features

| Feature                    | Status     | Description |
|---------------------------|------------|-----------|
| Natural Language Search   | ✅ Done    | Semantic search using embeddings |
| Image + ZIP Upload        | ✅ Done    | Bulk upload support |
| Auto Captioning           | ✅ Done    | Florence-2 model |
| Object Detection          | ✅ Done    | YOLOv10 |
| OCR Text Extraction       | ✅ Done    | PaddleOCR |
| Image Clustering          | ✅ Done    | HDBSCAN |
| Local-first & Private     | ✅ Done    | Everything runs locally |
| Light Mode for Contributors | ✅ Done  | Fast development |

---

## Tech Stack

- **Frontend:** Next.js 16, React 19, Tailwind CSS, React Query
- **Backend:** FastAPI, PostgreSQL + pgvector, Redis, MinIO
- **ML Pipeline:** YOLOv10, Florence-2, PaddleOCR, SigLIP, HDBSCAN

## Quick Start (Recommended for GSSoC)

```bash
# Light Mode - Sabse Fast (GSSoC ke liye best)
docker compose -f docker-compose.light.yml up --build
