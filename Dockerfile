FROM python:3.13-alpine

ARG VERSION
ARG BUILD_DATE

ENV VERSION="${VERSION}"
ENV PYTHONUNBUFFERED=1
ENV ISSUER_NAME=letsencrypt
ENV ISSUER_KIND=ClusterIssuer
ENV CERT_CLEANUP=false
ENV PATCH_SECRETNAME=true

RUN mkdir /app

COPY main.py /app/main.py
COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "/app/main.py"]
