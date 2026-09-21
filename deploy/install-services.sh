#!/bin/bash
# =============================================================================
# Sub2API Docker Run 安装脚本
# =============================================================================
# 直接使用 docker run 命令启动 postgres:18-alpine 和 redis:8-alpine 服务，
# 然后启动 Sub2API 应用，账号密码设置好，程序可以直接连接无需修改配置。

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

# =============================================================================
# 配置项（可直接修改）
# =============================================================================
POSTGRES_IMAGE="postgres:18-alpine"
REDIS_IMAGE="redis:8-alpine"
SUB2API_IMAGE="weishaw/sub2api:latest"

POSTGRES_CONTAINER="sub2api-postgres"
REDIS_CONTAINER="sub2api-redis"
SUB2API_CONTAINER="sub2api"

POSTGRES_PORT=5432
REDIS_PORT=6379
SUB2API_PORT=8080

# 账号密码配置
POSTGRES_USER="sub2api"
POSTGRES_PASSWORD="sub2api_password_2026"
POSTGRES_DB="sub2api"
REDIS_PASSWORD=""  # Redis 留空表示无密码（默认）

# 管理员账号
ADMIN_EMAIL="admin@sub2api.local"
ADMIN_PASSWORD="admin_password_2026"  # 留空则自动生成

# JWT 密钥（生产环境建议使用 openssl rand -hex 32 生成）
JWT_SECRET="sub2api_jwt_secret_change_me_in_production_2026"
TOTP_ENCRYPTION_KEY="sub2api_totp_secret_change_me_in_production_2026"

# 数据持久化目录
DATA_DIR="./sub2api-data"
POSTGRES_DATA_DIR="./postgres-data"
REDIS_DATA_DIR="./redis-data"

# =============================================================================
# 工具函数
# =============================================================================
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

container_exists() {
    docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${1}$"
}

container_running() {
    docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${1}$"
}

# =============================================================================
# 主流程
# =============================================================================
main() {
    echo ""
    echo "=========================================="
    echo "  Sub2API Docker Run 安装脚本"
    echo "=========================================="
    echo ""

    # 检查 Docker
    if ! command_exists docker; then
        print_error "Docker 未安装，请先安装 Docker"
        exit 1
    fi

    # 创建数据目录
    print_info "创建数据持久化目录..."
    mkdir -p "$DATA_DIR" "$POSTGRES_DATA_DIR" "$REDIS_DATA_DIR"
    print_success "数据目录已创建"

    # =====================================================================
    # 1. 启动 PostgreSQL
    # =====================================================================
    if container_exists "$POSTGRES_CONTAINER"; then
        print_warning "PostgreSQL 容器 $POSTGRES_CONTAINER 已存在"
        if container_running "$POSTGRES_CONTAINER"; then
            print_info "容器已在运行，跳过启动"
        else
            print_info "启动已存在的容器..."
            docker start "$POSTGRES_CONTAINER"
        fi
    else
        print_info "创建并启动 PostgreSQL ($POSTGRES_IMAGE)..."
        docker run -d \
            --name "$POSTGRES_CONTAINER" \
            --restart unless-stopped \
            -e PGDATA=/var/lib/postgresql/data \
            -e POSTGRES_USER="$POSTGRES_USER" \
            -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
            -e POSTGRES_DB="$POSTGRES_DB" \
            -e TZ=Asia/Shanghai \
            -v "$(pwd)/$POSTGRES_DATA_DIR:/var/lib/postgresql/data" \
            --network sub2api-net \
            --ulimit nofile=100000:100000 \
            "$POSTGRES_IMAGE" \
            postgres \
                -c max_connections=1024 \
                -c shared_buffers=1GB \
                -c effective_cache_size=4GB \
                -c maintenance_work_mem=128MB
        print_success "PostgreSQL 已启动"
    fi

    # =====================================================================
    # 2. 启动 Redis
    # =====================================================================
    if container_exists "$REDIS_CONTAINER"; then
        print_warning "Redis 容器 $REDIS_CONTAINER 已存在"
        if container_running "$REDIS_CONTAINER"; then
            print_info "容器已在运行，跳过启动"
        else
            print_info "启动已存在的容器..."
            docker start "$REDIS_CONTAINER"
        fi
    else
        print_info "创建并启动 Redis ($REDIS_IMAGE)..."
        if [ -z "$REDIS_PASSWORD" ]; then
            REDIS_CMD="redis-server --save 60 1 --appendonly yes --appendfsync everysec"
        else
            REDIS_CMD="redis-server --save 60 1 --appendonly yes --appendfsync everysec --requirepass '$REDIS_PASSWORD'"
        fi
        docker run -d \
            --name "$REDIS_CONTAINER" \
            --restart unless-stopped \
            -v "$(pwd)/$REDIS_DATA_DIR:/data" \
            -e TZ=Asia/Shanghai \
            --network sub2api-net \
            --ulimit nofile=100000:100000 \
            "$REDIS_IMAGE" \
            sh -c "$REDIS_CMD"
        print_success "Redis 已启动"
    fi

    # =====================================================================
    # 3. 创建自定义网络（如不存在）
    # =====================================================================
    if ! docker network inspect sub2api-net >/dev/null 2>&1; then
        print_info "创建自定义网络 sub2api-net..."
        docker network create sub2api-net
    fi

    # =====================================================================
    # 4. 等待数据库就绪
    # =====================================================================
    print_info "等待 PostgreSQL 就绪..."
    for i in {1..30}; do
        if docker exec "$POSTGRES_CONTAINER" pg_isready -U "$POSTGRES_USER" >/dev/null 2>&1; then
            print_success "PostgreSQL 已就绪"
            break
        fi
        sleep 2
        if [ "$i" -eq 30 ]; then
            print_error "PostgreSQL 启动超时"
            exit 1
        fi
    done

    # =====================================================================
    # 5. 启动 Sub2API 应用
    # =====================================================================
    if container_exists "$SUB2API_CONTAINER"; then
        print_warning "Sub2API 容器 $SUB2API_CONTAINER 已存在"
        if container_running "$SUB2API_CONTAINER"; then
            print_info "容器已在运行，跳过启动"
        else
            print_info "启动已存在的容器..."
            docker start "$SUB2API_CONTAINER"
        fi
    else
        print_info "创建并启动 Sub2API ($SUB2API_IMAGE)..."
        docker run -d \
            --name "$SUB2API_CONTAINER" \
            --restart unless-stopped \
            --network sub2api-net \
            -p "${BIND_HOST:-0.0.0.0}:${SUB2API_PORT}:8080" \
            -v "$(pwd)/$DATA_DIR:/app/data" \
            -e AUTO_SETUP=true \
            -e SERVER_HOST=0.0.0.0 \
            -e SERVER_PORT=8080 \
            -e SERVER_MODE=release \
            -e RUN_MODE=standard \
            -e TZ=Asia/Shanghai \
            \
            -e DATABASE_HOST="$POSTGRES_CONTAINER" \
            -e DATABASE_PORT="$POSTGRES_PORT" \
            -e DATABASE_USER="$POSTGRES_USER" \
            -e DATABASE_PASSWORD="$POSTGRES_PASSWORD" \
            -e DATABASE_DBNAME="$POSTGRES_DB" \
            -e DATABASE_SSLMODE=disable \
            \
            -e REDIS_HOST="$REDIS_CONTAINER" \
            -e REDIS_PORT="$REDIS_PORT" \
            -e REDIS_USERNAME="" \
            -e REDIS_PASSWORD="$REDIS_PASSWORD" \
            -e REDIS_DB=0 \
            \
            -e ADMIN_EMAIL="$ADMIN_EMAIL" \
            -e ADMIN_PASSWORD="$ADMIN_PASSWORD" \
            \
            -e JWT_SECRET="$JWT_SECRET" \
            -e JWT_EXPIRE_HOUR=24 \
            \
            -e TOTP_ENCRYPTION_KEY="$TOTP_ENCRYPTION_KEY" \
            \
            --ulimit nofile=100000:100000 \
            --security-opt no-new-privileges:true \
            "$SUB2API_IMAGE"
        print_success "Sub2API 已启动"
    fi

    # =====================================================================
    # 完成信息
    # =====================================================================
    echo ""
    echo "=========================================="
    echo "  安装完成"
    echo "=========================================="
    echo ""
    echo "服务状态："
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "sub2api|postgres|redis"
    echo ""
    echo "连接信息："
    echo "  PostgreSQL: $POSTGRES_CONTAINER:$POSTGRES_PORT"
    echo "    用户名: $POSTGRES_USER"
    echo "    密码:   $POSTGRES_PASSWORD"
    echo "    数据库: $POSTGRES_DB"
    echo ""
    echo "  Redis:     $REDIS_CONTAINER:$REDIS_PORT"
    if [ -n "$REDIS_PASSWORD" ]; then
        echo "    密码:   $REDIS_PASSWORD"
    else
        echo "    密码:   (无)"
    fi
    echo ""
    echo "  Sub2API:   http://localhost:$SUB2API_PORT"
    echo "    管理员邮箱: $ADMIN_EMAIL"
    if [ -n "$ADMIN_PASSWORD" ]; then
        echo "    管理员密码: $ADMIN_PASSWORD"
    else
        echo "    管理员密码: (自动生成，请查看日志)"
        print_info "日志查看: docker logs $SUB2API_CONTAINER | grep -i password"
    fi
    echo ""
    echo "数据持久化目录："
    echo "  应用数据:    $(pwd)/$DATA_DIR"
    echo "  PostgreSQL:  $(pwd)/$POSTGRES_DATA_DIR"
    echo "  Redis:       $(pwd)/$REDIS_DATA_DIR"
    echo ""
    echo "常用命令："
    echo "  查看日志: docker logs -f $SUB2API_CONTAINER"
    echo "  停止服务: docker stop $SUB2API_CONTAINER $REDIS_CONTAINER $POSTGRES_CONTAINER"
    echo "  启动服务: docker start $POSTGRES_CONTAINER $REDIS_CONTAINER $SUB2API_CONTAINER"
    echo "  删除服务: docker rm -f $SUB2API_CONTAINER $REDIS_CONTAINER $POSTGRES_CONTAINER"
    echo ""
}

# 执行
main "$@"