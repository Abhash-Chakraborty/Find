# Contributing to Find

First off, thanks for taking the time to contribute! 🎉

We love your input! We want to make contributing to this project as easy and transparent as possible, whether it's:

- Reporting a bug
- Discussing the current state of the code
- Submitting a fix
- Proposing new features
- Becoming a maintainer

## Development Process

We use GitHub to host code, to track issues and feature requests, and to accept pull requests.

1.  Fork the repo and create your branch from `master`.
2.  If you've added code that should be tested, add tests.
3.  If you've changed APIs, update the documentation.
4.  Ensure the test suite passes.
5.  Make sure your code lints.
6.  Issue that pull request!

## Getting Started

### Prerequisites

- **Node.js** (v18+) & **pnpm**
- **Python** (3.10+) & **pip**
- **Docker** & **Docker Compose**
- **PostgreSQL** (with `pgvector` extension)
- **Redis**
- **MinIO** (or S3 compatible storage)

### Local Setup

#### 1. Clone the repository

```bash
git clone https://github.com/AbhashChakraborty/Find.git
cd Find
```

#### 2. Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
pip install -r requirements.txt
```

**Environment Variables:**
Copy `.env.example` to `.env` and configure your database, Redis, and MinIO credentials.

**Run the Server:**
```bash
uvicorn app.main:app --reload
```

**Run the Worker:**
```bash
python -m app.workers.main
```

#### 3. Frontend Setup

```bash
cd frontend
pnpm install
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

## Code Quality

### Frontend (Biome)

We use [Biome](https://biomejs.dev/) for linting and formatting.

```bash
cd frontend
pnpm lint      # Check for issues
pnpm format    # Format code
```

### Backend (Ruff & Black)

We use `ruff` for linting and formatting (compatible with Black).

```bash
cd backend
ruff check .   # Check for lint errors
ruff format .  # Format code
```

## Pull Request Process

1.  Update the `README.md` with details of changes to the interface, this includes new environment variables, exposed ports, useful file locations and container parameters.
2.  Increase the version numbers in any examples files and the README.md to the new version that this Pull Request would represent.
3.  You may merge the Pull Request in once you have the sign-off of two other developers, or if you do not have permission to do that, you may request the second reviewer to merge it for you.

## License

By contributing, you agree that your contributions will be licensed under its MIT License.
