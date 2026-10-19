FROM node:24-slim AS charts
WORKDIR /charts
COPY dashboard/components/recharts/frontend/package*.json ./
RUN npm ci --no-fund --no-audit
COPY dashboard/components/recharts/frontend ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY backend backend
COPY dashboard dashboard
COPY --from=charts /charts/dist dashboard/components/recharts/frontend/dist
COPY .streamlit .streamlit
COPY ml ml

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
