FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml ./
COPY src ./src
COPY web ./web
RUN pip install --no-cache-dir .

EXPOSE 8000
ENV PORT=8000
ENV TRUECAST_WEB_DIR=/app/web
CMD ["sh", "-c", "uvicorn truecast.api.server:app --host 0.0.0.0 --port ${PORT}"]
