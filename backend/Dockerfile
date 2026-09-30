FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ffmpeg converts imported media to PCM16 mono 16 kHz (ADR 0012).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, against an empty package, so code changes reuse this heavy layer.
# The transcription worker image adds the ASR runtime (`.[asr]`); the API does not.
ARG INSTALL_ASR=false
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py \
    && if [ "$INSTALL_ASR" = "true" ]; then pip install --no-cache-dir ".[asr]"; \
    else pip install --no-cache-dir .; fi \
    && pip uninstall -y advera-backend && rm -rf app build *.egg-info

COPY app ./app
RUN pip install --no-cache-dir --no-deps .

COPY alembic.ini ./
COPY migrations ./migrations

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
