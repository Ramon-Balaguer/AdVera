# Pinned Docker images

Every image is pinned to an exact version tag, never to `latest` or to a moving tag such as `7`
or `pg16`, in the Compose file, the Dockerfiles and the CI. Dependabot opens a weekly pull
request when a newer version exists; CI checks it.

A tag can in principle be rebuilt by its publisher (for example to update the base system). If
you ever need byte-for-byte reproducible builds, add the digest (`tag@sha256:…`).

| Image | Where | Version |
|---|---|---|
| `pgvector/pgvector` | `docker/compose.dev.yml`, `.github/workflows/ci.yml` | pgvector 0.8.6 on PostgreSQL 16 |
| `redis` | `docker/compose.dev.yml`, `.github/workflows/ci.yml` | Redis 7.4.11 (to be replaced by Valkey, which is free software) |
| `python` | `backend/Dockerfile` | Python 3.12.14, slim |
| `node` | `frontend/Dockerfile` | Node 24.21.0, Alpine |

To find the digest of a tag, in case you want to add it:

```bash
docker buildx imagetools inspect python:3.12.14-slim | grep '^Digest:'
```
