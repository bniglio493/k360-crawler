"""
K360 — API REST (FastAPI)
Endpoints para integração com o dashboard Lovable.
"""
import logging
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import uvicorn

from config import API_KEY, API_HOST, API_PORT
from scheduler import get_background_scheduler

logger = logging.getLogger("k360.api")

app = FastAPI(
    title       = "K360 Crawler API",
    description = "Sistema de Angariação Automática de Proprietários",
    version     = "2.0.0",
    docs_url    = "/docs",
)

# ── CORS — permite Lovable (qualquer origem por default; restringir em prod) ──
app.add_middleware(
    CORSMiddleware,
    allow_origins  = ["*"],
    allow_methods  = ["*"],
    allow_headers  = ["*"],
)

# ── Auth simples por header ───────────────────────────────────────────────────
def verify_key(x_api_key: str = Query(None, alias="api_key")):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="API key inválida")

# ── Scheduler (background) ────────────────────────────────────────────────────
_scheduler = None

@app.on_event("startup")
async def startup():
    global _scheduler
    logging.basicConfig(level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s")
    _scheduler = get_background_scheduler()
    _scheduler.start()
    logger.info("⏰ Scheduler iniciado — busca às 00:00 Lisboa")

@app.on_event("shutdown")
async def shutdown():
    if _scheduler:
        _scheduler.shutdown()


# ═══════════════════════════════════════════════════════════════════════════════
# LEADS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/leads", tags=["Leads"])
async def list_leads(
    status:      Optional[str] = None,
    distrito:    Optional[str] = None,
    temperatura: Optional[str] = None,
    portal:      Optional[str] = None,
    atribuido_a: Optional[str] = None,
    hoje:        bool = False,
    limit:       int  = Query(50, le=200),
    offset:      int  = 0,
    _=Depends(verify_key),
):
    """Lista leads com filtros. Admin vê tudo; agente passa atribuido_a=uid."""
    from database import get_leads
    filters = {
        k: v for k, v in {
            "status": status, "distrito": distrito,
            "temperatura": temperatura, "portal": portal,
            "atribuido_a": atribuido_a, "hoje": hoje or None,
        }.items() if v
    }
    leads = get_leads(filters=filters, limit=limit, offset=offset)
    return {"data": leads, "total": len(leads), "offset": offset}


@app.get("/api/leads/{lead_id}", tags=["Leads"])
async def get_lead(lead_id: str, _=Depends(verify_key)):
    """Detalhe completo de uma lead (inclui histórico de preços e actividades)."""
    from database import get_lead_by_id
    lead = get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead não encontrada")
    return lead


class UpdateLeadBody(BaseModel):
    status:   str
    agent_id: str
    notas:    Optional[str] = ""

@app.put("/api/leads/{lead_id}/status", tags=["Leads"])
async def update_lead(lead_id: str, body: UpdateLeadBody, _=Depends(verify_key)):
    """Actualiza estado de uma lead (consultor ou admin)."""
    from database import update_lead_status
    update_lead_status(lead_id, body.status, body.agent_id, body.notas or "")
    return {"ok": True, "lead_id": lead_id, "status": body.status}


class AssignBody(BaseModel):
    lead_id:  str
    agent_id: str

@app.post("/api/leads/assign", tags=["Leads"])
async def assign_lead_manual(body: AssignBody, _=Depends(verify_key)):
    """Atribuição manual pelo admin."""
    from database import assign_lead
    assign_lead(body.lead_id, body.agent_id)
    return {"ok": True, "lead_id": body.lead_id, "agent_id": body.agent_id}


# ═══════════════════════════════════════════════════════════════════════════════
# STATS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/stats", tags=["Stats"])
async def dashboard_stats(_=Depends(verify_key)):
    """Métricas para o dashboard do admin."""
    from database import get_stats
    return get_stats()


@app.get("/api/stats/agente/{agent_id}", tags=["Stats"])
async def agent_stats(agent_id: str, _=Depends(verify_key)):
    """Métricas de um consultor específico."""
    from database import get_leads
    leads = get_leads(filters={"atribuido_a": agent_id}, limit=1000)
    statuses = {}
    for l in leads:
        s = l.get("status","")
        statuses[s] = statuses.get(s, 0) + 1
    return {
        "agent_id":    agent_id,
        "total":       len(leads),
        "por_status":  statuses,
        "quentes":     sum(1 for l in leads if l.get("temperatura") == "quente"),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# JOBS / SCRAPING
# ═══════════════════════════════════════════════════════════════════════════════

class SearchBody(BaseModel):
    districts:    Optional[list] = None
    portals:      Optional[list] = None
    tipos:        Optional[list] = None
    max_pages:    int             = 5
    country_code: str             = "PT"

@app.post("/api/search", tags=["Jobs"])
async def trigger_search(body: SearchBody, bg: BackgroundTasks, _=Depends(verify_key)):
    """Dispara uma busca manual imediatamente (corre em background)."""
    from database import get_scrape_config

    config    = get_scrape_config() or {}
    districts = body.districts or config.get("districts", ["Lisboa"])
    portals   = body.portals   or config.get("portals_enabled", ["olx_pt","imovirtual_pt"])
    tipos     = body.tipos     or config.get("property_types", ["apartamento"])

    def _run():
        from scrapers.runner import run_all_scrapers
        run_all_scrapers(
            districts    = districts,
            portals      = portals,
            tipos        = tipos,
            max_pages    = body.max_pages,
            country_code = body.country_code,
        )

    bg.add_task(_run)
    return {
        "ok":        True,
        "message":   "Busca iniciada em background",
        "districts": districts,
        "portals":   portals,
    }


@app.get("/api/jobs", tags=["Jobs"])
async def list_jobs(limit: int = 20, _=Depends(verify_key)):
    """Lista os últimos jobs de scraping com resultados."""
    from database import get_recent_jobs
    return {"data": get_recent_jobs(limit)}


@app.get("/api/jobs/next", tags=["Jobs"])
async def next_scheduled_run(_=Depends(verify_key)):
    """Quando corre a próxima busca automática."""
    if _scheduler:
        job = _scheduler.get_job("k360_daily_scrape")
        if job and job.next_run_time:
            return {"next_run": job.next_run_time.isoformat(), "timezone": "Europe/Lisbon"}
    return {"next_run": None}


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/config", tags=["Config"])
async def get_config(_=Depends(verify_key)):
    """Lê configuração activa de scraping."""
    from database import get_scrape_config, get_active_portals
    config  = get_scrape_config()
    portals = get_active_portals()
    return {"config": config, "portals_available": portals}


class ConfigUpdateBody(BaseModel):
    districts:       Optional[list] = None
    portals_enabled: Optional[list] = None
    property_types:  Optional[list] = None
    cron_schedule:   Optional[str]  = None
    max_pages:       Optional[int]  = None
    country_code:    Optional[str]  = None

@app.put("/api/config", tags=["Config"])
async def update_config(body: ConfigUpdateBody, _=Depends(verify_key)):
    """Admin actualiza configuração de scraping (distritos, portais, hora cron)."""
    from database import get_client
    db = get_client()
    update = {k: v for k, v in body.dict().items() if v is not None}
    if not update:
        raise HTTPException(status_code=400, detail="Nada para actualizar")
    db.table("k360_scrape_config").update(update).eq("active", True).execute()
    return {"ok": True, "updated": list(update.keys())}


# ═══════════════════════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/health", tags=["System"])
async def health():
    """Health check para Railway/Render."""
    return {"status": "ok", "service": "K360 Crawler API", "version": "2.0.0"}


if __name__ == "__main__":
    uvicorn.run("api.main:app", host=API_HOST, port=API_PORT, reload=False)
