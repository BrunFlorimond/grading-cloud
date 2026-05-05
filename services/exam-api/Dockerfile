FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

COPY shared /app/shared
COPY services/exam-api /app/services/exam-api

RUN pip install --no-cache-dir /app/shared /app/services/exam-api

WORKDIR /app/services/exam-api

EXPOSE 8000

CMD ["uvicorn", "exam_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
