FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home athenix
COPY athenix ./athenix
COPY migrations ./migrations
COPY alembic.ini ./
USER athenix
EXPOSE 8000
CMD ["python", "-m", "athenix", "serve", "--host", "0.0.0.0", "--no-worker"]
