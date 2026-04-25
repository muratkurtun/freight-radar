# Single-stage dev image.
# Designed for docker-compose with a bind mount on /app (+ anonymous
# volume on /app/node_modules) so source changes hot-reload the
# Angular dev server. Prod would be a multi-stage build that outputs
# a Nginx image — out of scope for this MVP.

FROM node:22-alpine

ENV NG_CLI_ANALYTICS=false \
    CI=true

WORKDIR /app

# Install deps first — cached until package*.json changes.
COPY package.json package-lock.json* ./
RUN npm install

# Source (overridden by bind mount in compose).
COPY . .

EXPOSE 4200

# compose overrides this for dev; this default works for a one-off run.
CMD ["npx", "ng", "serve", "--host", "0.0.0.0", "--port", "4200"]
