FROM apify/actor-python:3.11

# Upgrade pip first to avoid stale-pip build warnings
RUN python -m pip install --no-cache-dir --upgrade pip

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

# Pre-download the sentence-transformers model during build so it's baked into
# the image and doesn't need to be fetched on every cold start (~90MB download).
# Then clean up pip/torch caches to keep the image lean.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')" \
    && rm -rf /root/.cache/pip /tmp/*

COPY . .

CMD ["python", "-m", "src"]
