FROM node:20-alpine

RUN apk add --no-cache python3 py3-pip \
    && python3 -m venv /opt/venv

WORKDIR /opt/lint

COPY lint/package*.json ./
RUN npm ci --no-audit --no-fund

COPY lint/requirements.txt ./
RUN /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

COPY lint/eslint.config.mjs lint/ruff.toml lint/run.mjs ./

WORKDIR /workspace
USER node

CMD ["node", "/opt/lint/run.mjs"]
