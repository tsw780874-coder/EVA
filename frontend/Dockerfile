FROM node:22-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ENV NEXT_TELEMETRY_DISABLED=1
ENV NEXT_PUBLIC_API_URL=
ARG NODE_OPTIONS=--max-old-space-size=1024
ENV NODE_OPTIONS=${NODE_OPTIONS}
RUN npx next build

FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ARG NODE_OPTIONS=--max-old-space-size=512
ENV NODE_OPTIONS=${NODE_OPTIONS}

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000

CMD ["node", "server.js"]
