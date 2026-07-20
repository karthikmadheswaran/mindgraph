# Deploy note (2026-07-20): the src-only push 77df89b did not trigger a Railway
# rebuild of this service — its watch scope apparently excludes src/ (config
# lives in the Railway dashboard, not the repo; see docs/STATE.md P3). Touching
# this Dockerfile is the in-repo way to force a frontend rebuild.
FROM node:20-slim AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine

ENV PORT=3000

COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY railway-listen.envsh /docker-entrypoint.d/15-railway-listen.envsh
RUN chmod +x /docker-entrypoint.d/15-railway-listen.envsh
COPY --from=build /app/build /usr/share/nginx/html

EXPOSE 80 3000

CMD ["nginx", "-g", "daemon off;"]
