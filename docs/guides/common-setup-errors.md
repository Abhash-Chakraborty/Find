# Common Setup Errors

This guide helps contributors fix local setup problems before they start working
on Find. It is intentionally focused on beginner environment issues.

For real model, caption, OCR, embedding, or search-quality debugging, use:

- [Real ML Troubleshooting Guide](./real-ml-troubleshooting.md)

## Node.js and pnpm issues

### `pnpm: command not found`

Install pnpm:

```bash
npm install -g pnpm
```

Verify installation:

```bash
pnpm -v
```

### Node.js version mismatch

Find expects Node.js 18 or newer for the frontend.

Check your installed version:

```bash
node -v
```

If needed, install/update Node.js from:

- https://nodejs.org/

## Python and uv issues

### `uv: command not found`

Install uv from the official installer:

```bash
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Verify installation:

```bash
uv --version
```

### Python version issues

Verify Python version:

```bash
python --version
```

The project expects Python 3.12+.

## Docker issues

### Docker daemon not running

Ensure Docker Desktop or Docker Engine is running before starting containers.

Verify Docker status:

```bash
docker ps
```

Start the stack:

```bash
docker compose up --build
```

### Docker permission denied

On Linux systems, Docker may require elevated permissions.

Temporary workaround:

```bash
sudo docker compose up --build
```

Optional permanent fix:

```bash
sudo usermod -aG docker $USER
```

Log out and log back in after applying the group change.

## Service and port issues

### Port already in use

Common local ports are:

- Frontend: `3000`
- Backend API: `8000`
- PostgreSQL: `5432`
- Redis: `6379`
- MinIO API: `9200`
- MinIO console: `9201`

Check active ports:

```bash
netstat -ano
```

Stop conflicting services, or change the relevant port values in `.env`.

### Redis connection issues

Verify running services:

```bash
docker compose ps
```

Restart containers if needed:

```bash
docker compose restart
```

### MinIO service unavailable

Ensure MinIO containers are running correctly:

```bash
docker compose ps
```

Expected ports:

- MinIO API: `9200`
- MinIO Console: `9201`

## Contributor notes

Use the light Docker stack for routine contributor work:

```bash
docker compose -f docker-compose.light.yml up --build
```

- Use the full stack only when testing real ML inference, captions, OCR, search
  relevance, or model-loading behavior.
- Review the main README and CONTRIBUTING guide before opening issues or pull
  requests.
