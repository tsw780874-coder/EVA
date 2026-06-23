#!/usr/bin/env bash
set -e

# ============================================
# EVA 快速部署脚本 — 阿里云服务器
# 目标: 39.96.65.233
# ============================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SERVER="root@39.96.65.233"
REMOTE_DIR="/opt/eva"
TARBALL="eva-deploy.tar.gz"
TMP_TAR="/tmp/${TARBALL}"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  EVA 快速部署 — 阿里云${NC}"
echo -e "${GREEN}  目标: ${SERVER}${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 1. 打包（排除 .git .venv node_modules .next .idea .claude memory __pycache__）
echo -e "${GREEN}[1/5] 打包项目文件...${NC}"
tar -czf "${TMP_TAR}" \
    --exclude='.git' \
    --exclude='.venv' \
    --exclude='venv' \
    --exclude='node_modules' \
    --exclude='.next' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.idea' \
    --exclude='.claude' \
    --exclude='memory' \
    --exclude='.pytest_cache' \
    --exclude='*.tar.gz' \
    --exclude='*.zip' \
    --exclude='eva-deploy.tar.gz' \
    --exclude='backend/eva_dev.db' \
    --exclude='.env' \
    --exclude='backend/.env' \
    .

PACK_SIZE=$(du -h "${TMP_TAR}" | cut -f1)
echo -e "${GREEN}  → 打包完成: ${PACK_SIZE}${NC}"

# 2. 上传到服务器
echo ""
echo -e "${GREEN}[2/5] 上传到服务器...${NC}"
scp -o StrictHostKeyChecking=no -o ConnectTimeout=10 "${TMP_TAR}" "${SERVER}:${REMOTE_DIR}/"
echo -e "${GREEN}  → 上传完成${NC}"

# 3. 远程解压
echo ""
echo -e "${GREEN}[3/5] 服务器端解压...${NC}"
ssh -o StrictHostKeyChecking=no "${SERVER}" << 'ENDSSH'
    cd /opt/eva
    tar -xzf eva-deploy.tar.gz
    rm eva-deploy.tar.gz
    echo "  → 解压完成"
ENDSSH

# 4. 配置环境变量
echo ""
echo -e "${GREEN}[4/5] 配置环境变量...${NC}"
ssh -o StrictHostKeyChecking=no "${SERVER}" << 'ENDSSH'
    cd /opt/eva
    if [ ! -f .env ]; then
        cp .env.production .env
        echo "  → 已从 .env.production 创建 .env"
        echo ""
        echo "  ⚠️  请编辑服务器上的 .env 填入真实 API Keys:"
        echo "     ssh root@39.96.65.233"
        echo "     vim /opt/eva/.env"
        echo ""
    else
        echo "  → .env 已存在，跳过"
    fi
ENDSSH

# 5. 构建并启动
echo ""
echo -e "${GREEN}[5/5] 构建并启动 Docker 容器...${NC}"
echo -e "${YELLOW}  首次构建约需 5-10 分钟（拉取镜像 + 编译），后续更新仅需数秒${NC}"
echo ""
ssh -o StrictHostKeyChecking=no "${SERVER}" << 'ENDSSH'
    cd /opt/eva
    docker compose -f docker-compose.light.yml down --remove-orphans 2>/dev/null || true
    docker compose -f docker-compose.light.yml up -d --build

    echo ""
    echo "等待服务就绪..."
    for i in $(seq 1 30); do
        if curl -sf http://localhost/health > /dev/null 2>&1; then
            echo ""
            echo "========================================"
            echo "  ✅ EVA 部署成功！"
            echo "========================================"
            echo ""
            echo "  访问地址: http://39.96.65.233"
            echo "  健康检查: http://39.96.65.233/health"
            echo ""
            echo "  默认账号:"
            echo "    管理员: admin@eva.com / admin123"
            echo "    体验用户: user@eva.com / user123"
            echo ""
            echo "  常用命令:"
            echo "    ssh root@39.96.65.233"
            echo "    cd /opt/eva"
            echo "    docker compose ps           查看服务状态"
            echo "    docker compose logs -f       查看实时日志"
            echo "    docker compose restart       重启所有服务"
            echo "    docker compose down          停止服务"
            echo ""
            exit 0
        fi
        echo -n "."
        sleep 5
    done

    echo ""
    echo "⚠️ 等待超时，请检查日志:"
    docker compose logs --tail=50 backend
ENDSSH

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  部署流程完成${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "  ${YELLOW}重要提醒：${NC}"
echo -e "  1. 编辑服务器 .env 填入 API Keys:"
echo -e "     ${GREEN}ssh root@39.96.65.233 'vim /opt/eva/.env'${NC}"
echo -e "  2. 重启服务使配置生效:"
echo -e "     ${GREEN}ssh root@39.96.65.233 'cd /opt/eva && docker compose -f docker-compose.light.yml restart'${NC}"
echo ""
