FROM python:3.13.3-alpine3.21

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app
COPY . .
RUN rm -rf venv
RUN rm -rf .venv
RUN rm -rf __pycache__

RUN pip install -r requirements.txt
ENTRYPOINT ["python", "device_status_service.py"]
