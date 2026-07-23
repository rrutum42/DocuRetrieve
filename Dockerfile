# DocuRetriever — single-image deploy. Stage 1 builds the React frontend with
# Node; stage 2 runs FastAPI on Python and serves that built frontend, so the
# whole app is one process / one Render service.

# ---- stage 1: build the React frontend ----
FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- stage 2: python runtime ----
FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install runtime deps only (not the app package) so app/ and frontend/dist/
# stay siblings — main.py resolves the built frontend at ../frontend/dist.
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app/ ./app/
COPY --from=frontend /fe/dist ./frontend/dist

# Render provides $PORT; default to 8000 for local `docker run`.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
