FROM node:20-slim

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .
# cache-bust: 2026-04-16 auth-intent-guard

EXPOSE 3000

CMD ["npm", "start"]