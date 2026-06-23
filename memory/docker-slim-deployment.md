---
name: docker-slim-deployment
description: EVA slim Docker deployment to 4GB Alibaba Cloud ECS, with fixes for Alpine frontend build and MySQL auth
metadata:
  type: project
---

EVA deployed to 47.93.215.13 (Alibaba Cloud ECS, 4GB RAM, 50GB disk) using `docker-compose.slim.yml` (5 services).

**Why:** Full 9-service deployment requires 8GB+ RAM. Milvus/etcd/MinIO need ~3GB alone. Slim version drops these + MCP server for <4GB hosts.

**Key fixes applied:**

1. **nginx.slim.conf** — Removed MCP upstream block since slim compose has no MCP service. Nginx would fail to resolve `mcp-server` DNS otherwise.

2. **frontend/Dockerfile — Alpine permission issue:** `node_modules/.bin/next` is a shell script (not JS). On Alpine/busybox, `chmod +x` didn't work reliably. Fixed by using `sh node_modules/.bin/next build` instead of `npx next build` or `npm run build`.

3. **frontend/Dockerfile — Memory limit:** Added `ENV NODE_OPTIONS="--max-old-space-size=1024"` to prevent Next.js build OOM on 4GB server.

4. **backend/requirements.txt — cryptography:** Added `cryptography>=44.0.0` because MySQL 8.4's `caching_sha2_password` auth requires it. Without it, aiomysql fails with `RuntimeError: 'cryptography' package is required`.

**How to apply:** When deploying to similar low-memory servers, always use the slim compose. When building Next.js on Alpine node images, use `sh node_modules/.bin/next build`. Always include `cryptography` in requirements when using MySQL 8+ with aiomysql.
