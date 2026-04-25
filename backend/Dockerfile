# Single-stage dev image.
# Designed for docker-compose with a bind mount on /app so source changes
# hot-reload via uvicorn --reload. Prod would split this into a builder +
# slim runtime; MVP keeps one stage for debuggability.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Minimal OS packages. psycopg2-binary ships its own libpq so no build deps.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first — this layer is cached until requirements.txt changes.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Copy source (overridden by the bind mount in docker-compose for dev).
COPY . .

EXPOSE 8000

# compose overrides this for dev; kept here so `docker run backend` also works.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
