# Build stage — compiles the Vite/TS app to static assets
FROM node:20-slim AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# VITE_API_URL is baked in at build time — Vite inlines import.meta.env.* into the bundle.
# Leave unset to keep the default "/api" (same-origin, routed by the ALB/ingress in prod).
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Serve stage — static files behind nginx
FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8081

HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://localhost:8081/healthz || exit 1
