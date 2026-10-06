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
| `python` | `backend/Dockerfile` | Python 3.14.7, slim |
| `node` | `frontend/Dockerfile`, `frontend/Dockerfile.prod` | Node 26.10.0, Alpine |
| `nginx` | `frontend/Dockerfile.prod` | nginx 1.30.5, Alpine |

To find the digest of a tag, in case you want to add it:

```bash
docker buildx imagetools inspect python:3.12.14-slim | grep '^Digest:'
```

## Images published by AdVera

`.github/workflows/images.yml` publishes three images to `ghcr.io/ramon-balaguer/`, each for
`linux/amd64` and `linux/arm64`, on every merge to `main` (`release.yml`, which also creates the
version tag) and on every tag `vX.Y.Z` pushed by hand:

| Image | Contents |
|---|---|
| `advera-api` | API, migrations and the summary worker (no ML libraries) |
| `advera-worker-nvidia` | transcription and Brain workers (`asr,brain`); CUDA runs on amd64 only, because PyTorch for arm64 on PyPI is CPU-only. About 13 GB |
| `advera-frontend` | the built site behind nginx, which forwards `/api` and `/ws` to the API |

Tags: `main` (follows the branch), `sha-<commit>`, and for each release `X.Y.Z`, `X.Y` and
`latest`. To stay on a version, set `ADVERA_TAG=0.1.0`. The CI builds the same images (amd64)
on every pull request and runs a smoke test on each, so a Dockerfile or base-image change is
proven before it is merged.

`docker/compose.images-nvidia.yml` runs them without building, and without cloning the repository
(the README has the `curl` that downloads just that file). Other hardware (AMD, CPU only)
gets its own worker image and Compose file when we make it.

The first time an image is published, GitHub creates the package as private: make it public in
the package settings (Package settings -> Change visibility) so anyone can pull it.
A Dependabot bump of the `python` or `node` image is built by the CI like any other change, so
a version the ML libraries do not support is caught before it is merged.
