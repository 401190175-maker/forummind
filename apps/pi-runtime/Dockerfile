# ForumMind native Pi runtime sidecar. Dependencies are pinned by pnpm-lock.yaml.
FROM node:22.19.0-slim AS build

WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/pi-runtime/package.json apps/pi-runtime/package.json
RUN corepack enable && pnpm install --filter pi-runtime... --frozen-lockfile
COPY apps/pi-runtime apps/pi-runtime
RUN pnpm --filter pi-runtime build

FROM node:22.19.0-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/apps/pi-runtime/package.json ./apps/pi-runtime/package.json
COPY --from=build /app/apps/pi-runtime/dist ./apps/pi-runtime/dist
CMD ["node", "apps/pi-runtime/dist/src/index.js"]
