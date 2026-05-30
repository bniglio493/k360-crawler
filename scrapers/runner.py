"""
K360 — Runner de Scrapers
Motor principal: Firecrawl (se API key disponível) → fallback scrapers individuais
"""
import logging
import os
from typing import Optional

from enrichment.deduplication import generate_fingerprint, deduplicate_batch
from enrichment.scoring       import enrich_lead
from database                 import upsert_lead, create_job, finish_job
from distribution.engine      import distribute_leads

logger = logging.getLogger("k360.runner")


def _use_firecrawl() -> bool:
    return bool(os.getenv("FIRECRAWL_API_KEY", ""))


def run_all_scrapers(
    districts:    list,
    portals:      list,
    tipos:        list,
    max_pages:    int  = 10,
    country_code: str  = "PT",
    job_id:       Optional[str] = None,
) -> dict:
    """
    Executa todos os scrapers.
    Usa Firecrawl se disponível (melhor qualidade, sem bloqueios).
    Fallback para scrapers individuais se não tiver Firecrawl.
    """
    if not job_id:
        job_id = create_job(country_code, districts, portals, {
            "districts": districts, "portals": portals, "tipos": tipos
        })

    motor = "Firecrawl" if _use_firecrawl() else "Scrapers directos"
    logger.info(f"🚀 Job {job_id} — Motor: {motor} | {portals} | {districts}")

    all_leads_raw = []

    from scrapers.real_scraper import scrape_portal
    for portal_id in portals:
        try:
            leads = scrape_portal(portal_id, districts, tipos, max_pages)
            logger.info(f"  [{portal_id}] {len(leads)} leads")
            all_leads_raw.extend(leads)
        except Exception as e:
            logger.error(f"  [{portal_id}] Erro: {e}")

    logger.info(f"Total bruto: {len(all_leads_raw)}")

    # ── Fingerprint ───────────────────────────────────────────────────────
    for lead in all_leads_raw:
        if not lead.get("fingerprint"):
            lead["fingerprint"] = generate_fingerprint(
                lead.get("telefone", ""),
                lead.get("email", ""),
                lead.get("listing_url", "") or lead.get("url_anuncio", ""),
            )
        # Normaliza listing_url
        if not lead.get("listing_url") and lead.get("url_anuncio"):
            lead["listing_url"] = lead["url_anuncio"]

    # ── Dedup intra-batch ─────────────────────────────────────────────────
    batch_unique = deduplicate_batch(all_leads_raw)
    batch_dups   = len(all_leads_raw) - len(batch_unique)
    logger.info(f"Após dedup: {len(batch_unique)} únicos ({batch_dups} dups)")

    # ── Scoring ───────────────────────────────────────────────────────────
    for lead in batch_unique:
        enrich_lead(lead)

    # ── Persistência ──────────────────────────────────────────────────────
    novos, db_dups, new_leads = 0, 0, []
    for lead in batch_unique:
        is_new, lead_id = upsert_lead(lead)
        if is_new:
            novos += 1
            lead["id"] = lead_id
            new_leads.append(lead)
        else:
            db_dups += 1

    logger.info(f"DB: {novos} novos, {db_dups} duplicados")

    # ── Distribuição ──────────────────────────────────────────────────────
    dist_result  = distribute_leads(new_leads, mode="por_localizacao")
    distribuidos = len(dist_result.get("distribuidos", []))

    totals = {
        "encontrados":  len(all_leads_raw),
        "novos":        novos,
        "duplicados":   batch_dups + db_dups,
        "distribuidos": distribuidos,
    }
    finish_job(job_id, totals)

    logger.info(f"✅ Job {job_id} — {novos} novos | {distribuidos} distribuídos")
    return {**totals, "job_id": job_id}


def _get_scraper_map():
    from scrapers.olx         import OLXScraper
    from scrapers.imovirtual  import ImovirtualScraper
    from scrapers.portals     import (
        IdealistaScraper, CasaSAPOScraper,
        SupercasaScraper, CustojustoScraper
    )
    return {
        "olx_pt":        OLXScraper,
        "imovirtual_pt": ImovirtualScraper,
        "casa_sapo_pt":  CasaSAPOScraper,
        "custojusto_pt": CustojustoScraper,
    }
