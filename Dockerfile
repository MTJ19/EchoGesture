FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ECHOGESTURE_DEVELOPMENT_TOOLS=0 \
    ECHOGESTURE_WORD_MODEL=showcase50 \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libportaudio2 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --no-create-home --uid 10001 echogesture

COPY requirements-deploy.txt .
RUN pip install --no-cache-dir -r requirements-deploy.txt

COPY app.py .
COPY asl_lab/ asl_lab/
COPY scripts/acquire_wlasl.py scripts/extract_words.py scripts/
COPY config/showcase50.json config/
COPY templates/ templates/
COPY static/ static/
COPY models/classifier.joblib models/motion.joblib models/word81-grammar-candidate.joblib models/words20-candidate.joblib models/

USER echogesture
EXPOSE 10000
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 --timeout 120 'app:create_app()'"]
