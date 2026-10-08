FROM python:3.11-alpine

WORKDIR /app

RUN addgroup -S python && adduser -S -G python python \
    && mkdir -p /data \
    && chown -R python:python /app /data

USER python

COPY --chown=python:python . .

EXPOSE 5000

CMD ["python", "server.py"]
