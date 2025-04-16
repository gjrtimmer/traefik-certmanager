FROM python:3.13-alpine

ENV PYTHONUNBUFFERED=1 \
    ISSUER_NAME=letsencrypt \
    ISSUER_KIND=ClusterIssuer \
    CERT_CLEANUP=false \
    PATCH_SECRETNAME=true

RUN mkdir /app && \
    pip install --no-cache-dir -r requirements.txt

COPY main.py /app/main.py

CMD ["python", "/main.py"]
