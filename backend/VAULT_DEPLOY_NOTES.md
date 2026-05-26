# Vault Deployment Notes

## Single-worker requirement
The vault session cache (`active_vault_sessions` in `crypto.py`)
is an in-process dict. Running multiple uvicorn workers
(`--workers N`) or gunicorn will cause vault sessions created
in one worker to be invisible to others, resulting in 401 errors
on stream/hide requests.

**For v1: always run with a single worker.**

    uvicorn find_api.main:app --workers 1

Multi-worker support (Redis-backed session store) is tracked
as a future enhancement.
