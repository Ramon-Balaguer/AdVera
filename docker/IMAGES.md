# Pinned Docker images

Every image is pinned to an exact version, never to `latest` or to a moving tag such as `7` or
`pg16`. In `docker/compose.dev.yml` the pin is the tag alone, which is easy to read and to change.
The Dockerfiles and the CI add the digest (`tag@sha256:…`), so those builds use the same bytes
today and in a year, even if a publisher rebuilds a tag. Dependabot opens a weekly pull request
when a newer version exists; CI checks it.

| Image | Where | Version |
|---|---|---|
| `pgvector/pgvector` | `docker/compose.dev.yml` (tag), `.github/workflows/ci.yml` (tag and digest) | pgvector 0.8.6 on PostgreSQL 16 |
| `redis` | `docker/compose.dev.yml` (tag), `.github/workflows/ci.yml` (tag and digest) | Redis 7.4.11 (to be replaced by Valkey, which is free software) |
| `python` | `backend/Dockerfile` (tag and digest) | Python 3.12.14, slim |
| `node` | `frontend/Dockerfile` (tag and digest) | Node 24.21.0, Alpine |

To update one by hand, change the tag; where there is a digest, read the new one and replace it too:

```bash
docker buildx imagetools inspect python:3.12.15-slim | grep '^Digest:'
```
