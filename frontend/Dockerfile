ARG NODE_BASE_IMAGE=docker.1ms.run/node:20-alpine
ARG NGINX_BASE_IMAGE=docker.1ms.run/nginx:1.27-alpine

FROM ${NODE_BASE_IMAGE} AS build

ARG NPM_REGISTRY_URL=https://registry.npmmirror.com

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm config set registry ${NPM_REGISTRY_URL} \
    && npm ci

COPY frontend/ ./
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

FROM ${NGINX_BASE_IMAGE} AS runtime

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
