# SelaVoice — site (Next.js) em contêiner. Gera a versão "standalone" (pequena e sem node_modules inteiro).
# IMPORTANTE: NEXT_PUBLIC_API_URL é lido na HORA DO BUILD (vira parte do site e da política de segurança CSP).
# No Easypanel: Build Args -> NEXT_PUBLIC_API_URL=https://api.seudominio.com
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0 NEXT_TELEMETRY_DISABLED=1
# usuário sem privilégios (princípio do menor privilégio)
RUN addgroup -S app && adduser -S app -G app
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
USER app
EXPOSE 3000
HEALTHCHECK CMD wget -qO- http://127.0.0.1:3000/ >/dev/null || exit 1
CMD ["node", "server.js"]
