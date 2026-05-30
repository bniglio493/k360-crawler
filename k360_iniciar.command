#!/bin/bash

# ══════════════════════════════════════════════════════
#  K360 CRAWLER — Iniciador Mac
#  Duplo clique para correr. Faz tudo automaticamente.
# ══════════════════════════════════════════════════════

# Vai para a pasta onde este ficheiro está
cd "$(dirname "$0")"

clear
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   🏠  K360 CRAWLER — A INICIAR               ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── 1. Verifica Python ────────────────────────────────
echo "⏳ A verificar Python..."

if command -v python3 &>/dev/null; then
    PYTHON=python3
    echo "✅ Python3 encontrado: $(python3 --version)"
elif command -v python &>/dev/null; then
    PYTHON=python
    echo "✅ Python encontrado: $(python --version)"
else
    echo "❌ Python não encontrado. A instalar via Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    brew install python3
    PYTHON=python3
fi

echo ""

# ── 2. Instala dependências ───────────────────────────
echo "⏳ A instalar dependências (pode demorar 1-2 min na primeira vez)..."
$PYTHON -m pip install --quiet --upgrade pip 2>/dev/null
$PYTHON -m pip install --quiet \
    supabase requests beautifulsoup4 lxml \
    python-dotenv apscheduler colorama openpyxl \
    fastapi uvicorn pydantic pytz 2>&1 | tail -3
echo "✅ Dependências prontas"
echo ""

# ── 3. Cria .env se não existir ───────────────────────
if [ ! -f ".env" ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔑 PRIMEIRA VEZ — Precisamos da tua chave Supabase"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Vai a: supabase.com → teu projeto → Settings → API"
    echo "Copia a chave 'service_role' (começa com eyJ...)"
    echo ""
    read -p "Cola aqui a chave e pressiona Enter: " SUPA_KEY
    echo ""

    cat > .env << EOF
SUPABASE_URL=https://sahmtglrposdarcusgrq.supabase.co
SUPABASE_SERVICE_KEY=${SUPA_KEY}
SUPABASE_SERVICE_ROLE_KEY=${SUPA_KEY}
API_KEY=k360-local-mac
CRON_HOUR=0
CRON_MINUTE=0
LOG_LEVEL=INFO
EOF
    echo "✅ Configuração guardada em .env"
    echo ""
fi

# ── 4. Corre o scraper ────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 A BUSCAR PROPRIETÁRIOS EM PORTUGAL..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

$PYTHON main.py scrape \
    --districts Lisboa Faro Setubal Cascais \
    --portals olx_pt imovirtual_pt idealista_pt casa_sapo_pt custojusto_pt \
    --tipos apartamento moradia \
    --max-pages 3

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ CONCLUÍDO — Abre o teu dashboard para ver os leads"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "💡 Para correr de novo: duplo clique neste ficheiro"
echo ""
read -p "Pressiona Enter para fechar..." dummy
