"""
K360 — Cliente Supabase
Todas as operações de base de dados centralizadas aqui.
Usa service_role key → bypass total de RLS.
"""
import logging
from typing import Optional
from datetime import datetime

from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger("k360.db")

_client: Optional[Client] = None


def get_client() -> Client:
    global _client
    if _client is None:
        if not SUPABASE_KEY:
            raise RuntimeError("SUPABASE_SERVICE_KEY não definida no .env")
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


# ── LEADS ─────────────────────────────────────────────────────────────────────

def upsert_lead(data: dict) -> tuple[bool, str]:
    """
    Retorna (is_new: bool, lead_id: str)
    """
    db = get_client()
    fingerprint = data.get("fingerprint")

    # Verifica se já existe
    existing = (
        db.table("k360_market_leads")
        .select("id, preco, pontuacao")
        .eq("fingerprint", fingerprint)
        .maybe_single()
        .execute()
    )

    if existing and existing.data:
        lead_id = existing.data["id"]
        # Actualiza last_seen e verifica redução de preço

        preco_novo = data.get("preco")
        preco_antigo = existing.data.get("preco")
        if preco_novo and preco_antigo and preco_novo < preco_antigo:
            # Regista no histórico de preços
            _register_price_drop(lead_id, preco_novo, preco_antigo)

        return False, lead_id

    # Lead nova — insere
    try:
        result = db.table("k360_market_leads").insert(data).execute()
        lead_id = result.data[0]["id"] if result.data else ""
        return True, lead_id
    except Exception as e:
        logger.error(f"Erro ao inserir lead (fingerprint={fingerprint}): {e}")
        return False, ""


def _register_price_drop(lead_id: str, preco_novo: float, preco_antigo: float):
    db = get_client()
    delta = round((preco_novo - preco_antigo) / preco_antigo * 100, 2)
    db.table("k360_market_price_history").insert({
        "lead_id":    lead_id,
        "preco":      preco_novo,
        "delta_pct":  delta,
    }).execute()


def assign_lead(lead_id: str, agent_id: str, job_id: str = None):
    """Atribui lead a um consultor e regista actividade."""
    db = get_client()
    db.table("k360_market_leads").update({
        "status":       "atribuido",
        "atribuido_a":  agent_id,
        "atribuido_em": datetime.utcnow().isoformat(),
    }).eq("id", lead_id).execute()

    db.table("k360_atividades_de_mercado").insert({
        "lead_id":  lead_id,
        "agent_id": agent_id,
        "action":   "atribuido_automatico",
        "notas":    f"Distribuição automática por_localização — job {job_id or ''}",
    }).execute()


def get_unassigned_leads(district: str = None, limit: int = 200) -> list:
    db = get_client()
    q = db.table("k360_market_leads").select("*").eq("status", "novo").order("pontuacao", desc=True)
    if district:
        q = q.ilike("distrito", f"%{district}%")
    return (q.limit(limit).execute()).data or []


def get_leads(filters: dict = None, limit: int = 100, offset: int = 0) -> list:
    db = get_client()
    q = db.table("k360_market_leads").select("*, perfis(nome, email, telefone, avatar_url, zona_atuacao)")
    if filters:
        if filters.get("status"):       q = q.eq("status", filters["status"])
        if filters.get("atribuido_a"):  q = q.eq("atribuido_a", filters["atribuido_a"])
        if filters.get("distrito"):     q = q.ilike("distrito", f"%{filters['distrito']}%")
        if filters.get("temperatura"):  q = q.eq("temperatura", filters["temperatura"])
        if filters.get("portal"):       q = q.eq("portal_origem", filters["portal"])
        if filters.get("hoje"):
            hoje = datetime.utcnow().strftime("%Y-%m-%d")
            q = q.gte("criado_em", f"{hoje}T00:00:00")
    return (q.order("pontuacao", desc=True).range(offset, offset + limit - 1).execute()).data or []


def get_lead_by_id(lead_id: str) -> Optional[dict]:
    db = get_client()
    result = (
        db.table("k360_market_leads")
        .select("*, perfis(nome, email, avatar_url), k360_price_history(*), k360_lead_activities(*)")
        .eq("id", lead_id)
        .maybe_single()
        .execute()
    )
    return result.data


def update_lead_status(lead_id: str, status: str, agent_id: str, notas: str = ""):
    db = get_client()
    db.table("k360_market_leads").update({"status": status}).eq("id", lead_id).execute()
    db.table("k360_atividades_de_mercado").insert({
        "lead_id":  lead_id,
        "agent_id": agent_id,
        "action":   f"status_{status}",
        "notas":    notas,
    }).execute()


# ── AGENTES / PERFIS ─────────────────────────────────────────────────────────

def get_active_agents() -> list:
    """Busca consultores activos com zona de actuação definida."""
    try:
        db = get_client()
        result = (
            db.table("perfis")
            .select("id, nome, email, zona_atuacao, agencia")
            .not_.is_("zona_atuacao", "null")
            .execute()
        )
        return result.data or []
    except Exception:
        return []


def get_agent_lead_counts() -> dict:
    try:
        db = get_client()
        result = (
            db.table("k360_market_leads")
            .select("atribuido_a")
            .in_("status", ["atribuido", "em_contacto", "negociacao"])
            .execute()
        )
        counts = {}
        for row in (result.data or []):
            aid = row.get("atribuido_a")
            if aid:
                counts[aid] = counts.get(aid, 0) + 1
        return counts
    except Exception:
        return {}


# ── CONFIGURAÇÃO ──────────────────────────────────────────────────────────────

def get_scrape_config() -> Optional[dict]:
    try:
        db = get_client()
        result = db.table("k360_market_scrape_config").select("*").limit(1).execute()
        return result.data[0] if result.data else None
    except Exception:
        return None


def get_active_portals(country_code: str = "PT") -> list:
    db = get_client()
    result = (
        db.table("k360_market_portal_configs")
        .select("*")
        .eq("country_code", country_code)
        .eq("enabled", True)
        .execute()
    )
    return result.data or []


# ── JOBS ──────────────────────────────────────────────────────────────────────

def create_job(country_code: str, districts: list, portals: list, config: dict) -> str:
    db = get_client()
    result = db.table("k360_market_scrape_jobs").insert({
        "country_code":    country_code,
        "districts":       districts,
        "portals":         portals,
        "status":          "running",
        "config_snapshot": config,
    }).execute()
    return result.data[0]["id"] if result.data else ""


def finish_job(job_id: str, totals: dict, status: str = "completed", error: str = None):
    db = get_client()
    db.table("k360_market_scrape_jobs").update({
        "terminado_em":      datetime.utcnow().isoformat(),
        "status":            status,
        "total_encontrados": totals.get("encontrados", 0),
        "total_novos":       totals.get("novos", 0),
        "total_duplicados":  totals.get("duplicados", 0),
        "total_distribuidos":totals.get("distribuidos", 0),
        "error_log":         error,
    }).eq("id", job_id).execute()


def get_recent_jobs(limit: int = 20) -> list:
    db = get_client()
    return (
        db.table("k360_market_scrape_jobs")
        .select("*")
        .order("iniciado_em", desc=True)
        .limit(limit)
        .execute()
    ).data or []


# ── STATS ─────────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    db = get_client()

    def count(table, filters=None):
        q = db.table(table).select("id", count="exact")
        if filters:
            for k, v in filters.items():
                q = q.eq(k, v)
        return (q.execute()).count or 0

    hoje = datetime.utcnow().strftime("%Y-%m-%d")

    total         = count("k360_market_leads")
    novos         = count("k360_market_leads", {"status": "novo"})
    atribuidos    = count("k360_market_leads", {"status": "atribuido"})
    angariados    = count("k360_market_leads", {"status": "angariado"})
    quentes       = count("k360_market_leads", {"temperatura": "quente"})

    hoje_result = (
        db.table("k360_market_leads").select("id", count="exact")
        .gte("criado_em", f"{hoje}T00:00:00").execute()
    )
    hoje_novos = hoje_result.count or 0

    # Por distrito
    por_distrito = {}
    dist_result = db.table("k360_market_leads").select("distrito").not_.is_("distrito","null").execute()
    for row in (dist_result.data or []):
        d = row["distrito"]
        por_distrito[d] = por_distrito.get(d, 0) + 1

    # Por portal
    por_portal = {}
    portal_result = db.table("k360_market_leads").select("portal_origem").execute()
    for row in (portal_result.data or []):
        p = row["portal_origem"]
        por_portal[p] = por_portal.get(p, 0) + 1

    return {
        "total":        total,
        "novos":        novos,
        "atribuidos":   atribuidos,
        "angariados":   angariados,
        "quentes":      quentes,
        "hoje_novos":   hoje_novos,
        "por_distrito": dict(sorted(por_distrito.items(), key=lambda x: -x[1])[:10]),
        "por_portal":   dict(sorted(por_portal.items(), key=lambda x: -x[1])),
    }
