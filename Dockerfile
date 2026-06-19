FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# strictly require wheels (no compiler on ARM)
COPY requirements.txt .
RUN pip install --only-binary=:all: -r requirements.txt

COPY app.py .
COPY cuny_tracker/ ./cuny_tracker/

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status==200 else sys.exit(1)"

# single worker prevents duplicate APScheduler polls
CMD ["uvicorn", "cuny_tracker.main:app", "--host", "0.0.0.0", "--port", "8000"]
