"""
K360 Crawler — Configuração Central
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Supabase ─────────────────────────────────────────────────────────────────
SUPABASE_URL  = os.getenv("SUPABASE_URL",  "https://sahmtglrposdarcusgrq.supabase.co")
SUPABASE_KEY  = os.getenv("SUPABASE_SERVICE_KEY", "")   # service_role key — bypassa RLS

# ── Scheduler ────────────────────────────────────────────────────────────────
CRON_HOUR     = int(os.getenv("CRON_HOUR",   "0"))    # 00:00 Lisboa
CRON_MINUTE   = int(os.getenv("CRON_MINUTE", "0"))
TIMEZONE      = "Europe/Lisbon"

# ── Crawler ───────────────────────────────────────────────────────────────────
CRAWLER = {
    "delay_min":    2.5,
    "delay_max":    5.5,
    "timeout":      25,
    "retry":        2,
    "max_pages":    10,
    "max_leads":    500,
    "headless":     True,
}

# ── User-Agents rotativos ────────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]

# ── Keywords de urgência (score +25) ────────────────────────────────────────
KEYWORDS_URGENCIA = [
    "urgente", "urgência", "vendo urgente", "venda urgente",
    "emigro", "emigra", "emigrando", "emigração", "emigrar", "emigrante",
    "liquidação", "liquido", "a liquidar",
    "divórcio", "divorcio", "separação",
    "herança", "heranca", "sucessão",
    "motivos pessoais", "motivos de saúde", "razões pessoais",
    "mudança de país", "mudança país", "mudar de país",
    "preciso de vender", "necessito vender", "preciso vender",
    "aceito propostas", "aceito ofertas", "todas as ofertas",
    "preço negociável", "negociável", "negociavel",
    "abaixo do valor", "abaixo de mercado",
    "vendo rápido", "venda rápida", "vender rapidamente",
]

# ── Regiões Portugal ─────────────────────────────────────────────────────────
REGIOES_PT = {
    "Lisboa":   ["Lisboa", "Sintra", "Cascais", "Oeiras", "Amadora", "Loures", "Vila Franca de Xira", "Mafra", "Odivelas"],
    "Faro":     ["Faro", "Loulé", "Portimão", "Lagos", "Albufeira", "Silves", "Olhão", "Tavira", "Lagos", "Aljezur", "Castro Marim"],
    "Setubal":  ["Setúbal", "Palmela", "Sesimbra", "Alcochete", "Montijo", "Almada", "Seixal", "Barreiro", "Moita", "Grândola"],
    "Cascais":  ["Cascais"],
    "Porto":    ["Porto", "Gaia", "Matosinhos", "Maia", "Gondomar", "Valongo", "Espinho"],
    "Braga":    ["Braga", "Guimarães", "Barcelos", "Famalicão", "Póvoa de Varzim"],
    "Coimbra":  ["Coimbra", "Figueira da Foz", "Lousã", "Condeixa"],
    "Aveiro":   ["Aveiro", "Ílhavo", "Águeda", "Oliveira de Azeméis"],
    "Leiria":   ["Leiria", "Marinha Grande", "Nazaré", "Alcobaça"],
}

# ── Regiões Espanha (preparado) ──────────────────────────────────────────────
REGIOES_ES = {
    "Madrid":    ["Madrid", "Alcalá de Henares", "Getafe", "Alcobendas"],
    "Barcelona": ["Barcelona", "Hospitalet", "Badalona", "Sabadell"],
    "Valencia":  ["Valencia", "Alicante", "Castellón"],
    "Malaga":    ["Málaga", "Marbella", "Torremolinos", "Benalmádena"],
}

# ── Tipos de imóvel ───────────────────────────────────────────────────────────
TIPOS_IMOVEL = ["apartamento", "moradia", "terreno", "comercial", "rural"]

# ── API ───────────────────────────────────────────────────────────────────────
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("PORT", os.getenv("API_PORT", "8000")))
API_KEY  = os.getenv("API_KEY", "k360-api-key-change-me")

# ── Logs ──────────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE  = "logs/k360_crawler.log"
