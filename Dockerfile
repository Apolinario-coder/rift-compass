FROM python:3.13-slim
ARG SERVICE
WORKDIR /app
COPY shared /app/shared
COPY ${SERVICE} /app/service
RUN pip install --no-cache-dir ./shared ./service && useradd --create-home appuser
USER appuser
EXPOSE 8000
