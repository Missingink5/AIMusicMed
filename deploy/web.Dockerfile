FROM node:22-bookworm-slim AS build

WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/.openai ./.openai
COPY web/app ./app
COPY web/build ./build
COPY web/db ./db
COPY web/examples ./examples
COPY web/public ./public
COPY web/worker ./worker
COPY web/drizzle.config.ts web/eslint.config.mjs ./
COPY web/next.config.ts web/postcss.config.mjs ./
COPY web/tsconfig.json web/vite.config.ts ./
RUN npm run build

FROM node:22-bookworm-slim AS runtime

ENV NODE_ENV=production \
    PORT=3000

WORKDIR /app
COPY --from=build --chown=node:node /app/package.json /app/package-lock.json ./
COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/dist ./dist

USER node
EXPOSE 3000
CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]
