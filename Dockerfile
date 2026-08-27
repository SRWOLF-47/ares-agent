FROM python:3.11-slim

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir google-genai edge-tts fastapi uvicorn python-multipart

ENV PORT=8080

CMD ["uvicorn", "ares_server:app", "--host", "0.0.0.0", "--port", "8080"]