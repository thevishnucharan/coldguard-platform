# syntax=docker/dockerfile:1
# ---------------------------------------------------------------- build
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# Demo account buttons on the login page are hidden unless explicitly enabled at build time.
ARG VITE_SHOW_DEMO_LOGINS=false
ENV VITE_SHOW_DEMO_LOGINS=$VITE_SHOW_DEMO_LOGINS
RUN npm run build

# ---------------------------------------------------------------- runtime (non-root nginx)
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1
