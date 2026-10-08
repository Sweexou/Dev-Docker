FROM node:20-alpine

WORKDIR /app

RUN chown -R node:node /app

USER node

COPY --chown=node:node package*.json ./

RUN npm ci

COPY --chown=node:node . .

EXPOSE 4000

CMD ["node", "server.js"]