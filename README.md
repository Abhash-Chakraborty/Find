# Find — Local-First AI Image Intelligence Platform

**Find** is a privacy-first, fully local AI-powered image analysis and search platform. All processing happens on your device — no cloud storage, no external APIs.

## 🎯 Features

- **Local-First**: All data stays on your machine
- **AI-Powered Analysis**: Object detection, scene captioning, OCR, face recognition
- **Semantic Search**: Find images using natural language queries
- **Smart Clustering**: Automatically groups related images
- **Vector Embeddings**: CLIP-based image and text embeddings
- **Fast Search**: PostgreSQL with pgvector for similarity search

## 🏗️ Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│  Next.js    │─────▶│   FastAPI    │─────▶│  PostgreSQL │
│  Frontend   │      │   Backend    │      │  + pgvector │
└─────────────┘      └──────────────┘      └─────────────┘
                           │
                           ├─────▶ MinIO (Object Storage)
                           ├─────▶ Redis (Job Queue)
                           └─────▶ RQ Workers (ML Pipeline)
```

### Tech Stack

**Frontend**

- Next.js 14+ (React, TypeScript)
- TailwindCSS
- shadcn/ui
- TanStack Query
- react-force-graph (3D clustering visualization)
- Biome (Linting & Formatting)

**Backend**

- FastAPI
- SQLAlchemy + Alembic
- PostgreSQL + pgvector
- Redis + RQ
- MinIO

**ML Pipeline**

- YOLOv10 (object detection)
- Florence-2 (image captioning)
- SigLIP (embeddings)
- PaddleOCR (text extraction)
- AntelopeV2 (face recognition)
- HDBSCAN (clustering)

## 🚀 Quick Start

### Prerequisites

- Docker Desktop
- 16GB+ RAM recommended
- ~10GB disk space for models and data

### Installation

1. **Clone and navigate**

   ```bash
   cd Find
   ```

2. **Start all services**

   ```bash
   docker-compose up -d
   ```

3. **Wait for services to initialize** (~2-3 minutes for first run)

4. **Access the application**
   - Frontend: http://localhost:3000
   - API: http://localhost:8000
   - MinIO Console: http://localhost:9001

### First Time Setup

The backend will automatically:

- Download ML models on first run
- Initialize the database
- Create MinIO buckets
- Start workers

## 📖 Usage

### Upload Images

1. Navigate to http://localhost:3000/upload
2. Drag and drop images or click to browse
3. Monitor processing status in real-time

### Search

Use natural language queries:

- "sunset over mountains"
- "people smiling"
- "documents with text"
- "cats sleeping"

### View Clusters

Navigate to `/clusters` to see 3D visualization of image relationships.

## 🗂️ Project Structure

```
find/
├── frontend/              # Next.js application
│   ├── app/              # App router pages
│   ├── components/       # React components
│   ├── lib/              # Utilities and API client
│   └── public/           # Static assets
│
├── backend/              # FastAPI application
│   ├── app/
│   │   ├── main.py      # FastAPI entry point
│   │   ├── routers/     # API endpoints
│   │   ├── models/      # SQLAlchemy models
│   │   ├── workers/     # RQ job definitions
│   │   └── ml/          # ML pipeline modules
│   ├── requirements.txt
│   └── Dockerfile
│
├── docker-compose.yml    # Orchestration
└── .env.example         # Environment template
```

## 🔧 Configuration

Create a `.env` file:

```env
# Database
DATABASE_URL=postgresql://find:find123@db:5432/find

# MinIO
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=images

# Redis
REDIS_URL=redis://redis:6379

# API
API_HOST=0.0.0.0
API_PORT=8000
```

## 🧠 ML Pipeline

Each uploaded image is processed through:

1. **Object Detection** (YOLOv8) - Identifies objects and bounding boxes
2. **Captioning** (BLIP-2) - Generates natural language description
3. **OCR** (Tesseract) - Extracts text from image
4. **Face Detection** (InsightFace) - Detects and embeds faces
5. **CLIP Embedding** (OpenCLIP) - Creates semantic vector
6. **Clustering** (HDBSCAN) - Groups similar images

## 📊 Database Schema

### Media Table

```sql
CREATE TABLE media (
  id SERIAL PRIMARY KEY,
  file_hash TEXT UNIQUE,
  minio_key TEXT,
  filename TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  status TEXT,
  exif_json JSONB,
  metadata_json JSONB,
  cluster_id INT,
  vector vector(768)
);
```

### Clusters Table

```sql
CREATE TABLE clusters (
  id SERIAL PRIMARY KEY,
  cluster_type TEXT,
  centroid_vector vector(768),
  member_ids INT[],
  created_at TIMESTAMP DEFAULT NOW()
);
```

## 🔌 API Endpoints

| Method | Path                    | Description                  |
| ------ | ----------------------- | ---------------------------- |
| POST   | `/api/upload`           | Upload images for processing |
| GET    | `/api/status/{id}`      | Check processing status      |
| GET    | `/api/gallery`          | List all processed images    |
| GET    | `/api/image/{id}`       | Get image details            |
| GET    | `/api/search?q=<query>` | Semantic search              |
| GET    | `/api/clusters`         | Get cluster data             |

## 🛠️ Development

### Backend Development

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend Development

```bash
cd frontend
pnpm install
pnpm dev
```

### Database Migrations

```bash
cd backend
alembic revision --autogenerate -m "Description"
alembic upgrade head
```

## 🐛 Troubleshooting

**Models not downloading?**

- Check internet connection on first run
- Models are cached in Docker volumes

**Out of memory?**

- Reduce batch size in worker config
- Increase Docker memory allocation

**Slow processing?**

- Enable GPU support (CUDA)
- Reduce image resolution before upload

## 🔐 Privacy & Security

- **Zero Cloud Dependencies**: Everything runs locally
- **No Telemetry**: No tracking or data collection
- **Local Storage**: Images never leave your machine
- **Encrypted Storage**: Optional MinIO encryption support

## 📈 Performance

- **Lightweight Mode**: Basic metadata + CLIP embeddings (~2s/image)
- **Full Analysis**: All ML models (~10-15s/image on CPU)
- **GPU Acceleration**: 5-10x faster with CUDA-enabled GPU

## 🚧 Roadmap

- [ ] Face labeling and custom tags
- [ ] Timeline view (by EXIF date)
- [ ] Local model fine-tuning
- [ ] PWA for offline use
- [ ] Mobile app (React Native)
- [ ] Video analysis support
- [ ] Duplicate detection

## 📄 License

MIT License - See LICENSE file for details

## 🤝 Contributing

Contributions welcome! Please open an issue or PR.

---

**Built with ❤️ for privacy-conscious users**
