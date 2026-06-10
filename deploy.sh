#!/usr/bin/env bash
set -e

# ============================================
# EVA 一键部署脚本
# 用法: ./deploy.sh
# ============================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  EVA 智能购物决策系统 - Docker 部署${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 1. 检查 Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}[错误] 未检测到 Docker，请先安装 Docker${NC}"
    echo "  Ubuntu: sudo apt install docker.io"
    echo "  CentOS: sudo yum install -y docker"
    exit 1
fi

if ! docker compose version &> /dev/null 2>&1; then
    echo -e "${RED}[错误] 需要 Docker Compose v2+${NC}"
    exit 1
fi

echo -e "${GREEN}[✓] Docker 环境检查通过${NC}"

# 2. 检查 .env 文件
if [ ! -f .env ]; then
    echo ""
    echo -e "${YELLOW}[!] 未找到 .env 文件，正在从 .env.example 创建...${NC}"
    cp .env.example .env
    echo -e "${YELLOW}[!] 请编辑 .env 文件填入 API Keys 和密码后重新运行此脚本${NC}"
    echo -e "${YELLOW}    vim .env${NC}"
    exit 0
fi

echo -e "${GREEN}[✓] .env 配置文件已就绪${NC}"

# 3. 构建并启动
echo ""
echo -e "${GREEN}[→] 正在构建镜像并启动容器（首次构建约需 5-10 分钟）...${NC}"
docker compose up -d --build

# 4. 等待健康检查
echo ""
echo -e "${GREEN}[→] 等待服务就绪...${NC}"

MAX_WAIT=120
ELAPSED=0
while [ $ELAPSED -lt $MAX_WAIT ]; do
    if curl -sf http://localhost/health > /dev/null 2>&1; then
        echo ""
        echo -e "${GREEN}========================================${NC}"
        echo -e "${GREEN}  部署成功！${NC}"
        echo -e "${GREEN}========================================${NC}"
        echo ""
        echo -e "  访问地址: ${GREEN}http://172.17.50.63${NC}"
        echo ""
        echo -e "  默认账号:"
        echo -e "    管理员: ${YELLOW}admin@eva.com${NC} / ${YELLOW}admin123${NC}"
        echo -e "    体验用户: ${YELLOW}user@eva.com${NC} / ${YELLOW}user123${NC}"
        echo ""
        echo -e "  常用命令:"
        echo -e "    docker compose ps          查看服务状态"
        echo -e "    docker compose logs -f      查看实时日志"
        echo -e "    docker compose restart      重启所有服务"
        echo -e "    docker compose down         停止并移除容器"
        echo ""
        exit 0
    fi
    sleep 5
    ELAPSED=$((ELAPSED + 5))
    echo -n "."
done

echo ""
echo -e "${YELLOW}[!] 等待超时，请检查日志: docker compose logs backend${NC}"
echo -e "${YELLOW}[!] 当前容器状态:${NC}"
docker compose ps
exit 1
