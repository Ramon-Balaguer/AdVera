# Pinned Docker images

Every base image is pinned to an exact version **and** its digest, so a build today and a build
in a year use the same bytes (the tag alone can be moved by its publisher). Dependabot opens a
weekly pull request when a newer one exists; CI checks it.

| Image | Where | Version |
|---|---|---|
| `pgvector/pgvector` | `docker/compose.dev.yml`, `.github/workflows/ci.yml` | pgvector 0.8.6 on PostgreSQL 16 |
| `redis` | `docker/compose.dev.yml`, `.github/workflows/ci.yml` | Redis 7.4.11 (to be replaced by Valkey, which is free software) |
| `python` | `backend/Dockerfile` | Python 3.12.14, slim |
| `node` | `frontend/Dockerfile` | Node 24.21.0, Alpine |

To update one by hand, read the digest of the new tag and replace both the tag and the digest:

```bash
docker buildx imagetools inspect python:3.12.15-slim | grep '^Digest:'
```
