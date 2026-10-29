FROM python:3.11-alpine

WORKDIR /tests

RUN addgroup -S tester && adduser -S -G tester tester
USER tester

COPY test_integration.py ./

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

CMD ["python", "-m", "unittest", "discover", "-v"]
