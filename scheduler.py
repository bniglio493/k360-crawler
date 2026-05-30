"""
K360 — Scheduler Automático
Executa a busca todos os dias às 00:00 hora de Lisboa.
Lê a configuração directamente da Supabase — sem restart para alterar.
"""
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron       import CronTrigger
from config import CRON_HOUR, CRON_MINUTE, TIMEZONE

logger = logging.getLogger("k360.scheduler")


def run_daily_job():
    """
    Função executada pelo cron.
    Lê configuração da DB → executa todos os scrapers → distribui leads novas.
    """
    logger.info("=" * 60)
    logger.info("🕛 BUSCA AUTOMÁTICA DIÁRIA INICIADA")
    logger.info("=" * 60)

    try:
        from database       import get_scrape_config, get_active_portals
        from scrapers.runner import run_all_scrapers

        config = get_scrape_config()
        if not config:
            logger.warning("Nenhuma configuração activa na Supabase — abortando")
            return

        districts    = config.get("districts", ["Lisboa", "Faro", "Setubal"])
        portals      = config.get("portals_enabled", ["olx_pt", "imovirtual_pt"])
        tipos        = config.get("property_types", ["apartamento"])
        max_pages    = config.get("max_pages", 10)
        country_code = config.get("country_code", "PT")

        logger.info(f"  Distritos:  {districts}")
        logger.info(f"  Portais:    {portals}")
        logger.info(f"  Tipos:      {tipos}")
        logger.info(f"  Pág/portal: {max_pages}")

        result = run_all_scrapers(
            districts    = districts,
            portals      = portals,
            tipos        = tipos,
            max_pages    = max_pages,
            country_code = country_code,
        )

        logger.info("─" * 60)
        logger.info(f"  📊 Encontrados:  {result['encontrados']}")
        logger.info(f"  🆕 Novos:        {result['novos']}")
        logger.info(f"  🔁 Duplicados:   {result['duplicados']}")
        logger.info(f"  👤 Distribuídos: {result['distribuidos']}")
        logger.info("✅ Busca automática concluída")

    except Exception as e:
        logger.error(f"❌ Erro na busca automática: {e}", exc_info=True)


def start_scheduler():
    """Inicia o scheduler bloqueante — usa como processo dedicado."""
    _setup_logging()

    scheduler = BlockingScheduler(timezone=TIMEZONE)

    # Cron: todos os dias às 00:00 Lisboa
    trigger = CronTrigger(
        hour     = CRON_HOUR,
        minute   = CRON_MINUTE,
        timezone = TIMEZONE,
    )

    scheduler.add_job(
        run_daily_job,
        trigger  = trigger,
        id       = "k360_daily_scrape",
        name     = "K360 Busca Diária de Proprietários",
        max_instances = 1,            # Nunca corre em paralelo
        misfire_grace_time = 3600,    # Se arrancar com atraso, ainda corre (1h)
        replace_existing = True,
    )

    logger.info(f"⏰ Scheduler activo — busca todos os dias às {CRON_HOUR:02d}:{CRON_MINUTE:02d} {TIMEZONE}")
    logger.info("   (Ctrl+C para parar)")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Scheduler parado")
        scheduler.shutdown()


def get_background_scheduler():
    """
    Versão não-bloqueante para usar dentro da FastAPI.
    Não usa BlockingScheduler mas BackgroundScheduler.
    """
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler(timezone=TIMEZONE)

    trigger = CronTrigger(
        hour     = CRON_HOUR,
        minute   = CRON_MINUTE,
        timezone = TIMEZONE,
    )

    scheduler.add_job(
        run_daily_job,
        trigger           = trigger,
        id                = "k360_daily_scrape",
        name              = "K360 Busca Diária",
        max_instances     = 1,
        misfire_grace_time= 3600,
        replace_existing  = True,
    )

    return scheduler


def _setup_logging():
    import os
    os.makedirs("logs", exist_ok=True)
    logging.basicConfig(
        level   = logging.INFO,
        format  = "%(asctime)s [%(name)s] %(levelname)s — %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/k360_crawler.log", encoding="utf-8"),
        ],
    )


if __name__ == "__main__":
    _setup_logging()
    # Opção: correr imediatamente antes de agendar
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--now", action="store_true", help="Corre a busca agora e aguarda o próximo cron")
    args = parser.parse_args()

    if args.now:
        logger.info("▶️  Executando busca imediata antes do cron...")
        run_daily_job()

    start_scheduler()
