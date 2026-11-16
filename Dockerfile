# Estágio 1: build do frontend (React/Vite)
FROM node:22-alpine AS frontend
WORKDIR /front
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Estágio 2: backend (FastAPI + worker na mesma imagem; SERVICE_ROLE decide o papel)
FROM python:3.12-slim AS backend
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /srv
COPY backend/ ./
RUN pip install -e .
COPY --from=frontend /front/dist ./app/static
RUN chmod +x entrypoint.sh
CMD ["./entrypoint.sh"]
