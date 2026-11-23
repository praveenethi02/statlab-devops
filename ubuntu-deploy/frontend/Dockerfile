FROM node:22-alpine AS assets
WORKDIR /build
COPY package.json package-lock.json ./
COPY scripts/vendor.mjs scripts/vendor.mjs
RUN npm ci --omit=dev

FROM nginx:alpine
COPY index.html /usr/share/nginx/html/index.html
COPY static/ /usr/share/nginx/html/static/
COPY --from=assets /build/static/vendor/ /usr/share/nginx/html/static/vendor/
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
