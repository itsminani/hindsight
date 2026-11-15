# Two stages: Node builds the static files; nginx (non-root) serves them and proxies /api to the API.

# ---------- Stage 1: build ----------
FROM node:24-alpine AS build
WORKDIR /app
# Dependencies first: this layer is cached until package.json or package-lock.json changes.
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---------- Stage 2: serve ----------
# The "unprivileged" image runs nginx as a non-root user on port 8080.
FROM nginxinc/nginx-unprivileged:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --retries=3 CMD wget -qO- http://127.0.0.1:8080/ >/dev/null || exit 1
