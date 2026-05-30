#!/usr/bin/env python3
"""
K360 Crawler — Ponto de Entrada
Uso:
    python main.py scrape              # Corre busca com config da Supabase
    python main.py scrape --now        # Busca imediata + agenda próxima
    python main.py scheduler           # Inicia apenas o scheduler
    python main.py api                 # Inicia apenas a API
    python main.py all                 # API + Scheduler juntos (recomendado)
    python main.py demo                # Demo sem Supabase
"""
import sys, os, logging, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _setup_logging():
    os.makedirs("logs", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/k360_crawler.log", encoding="utf-8"),
        ],
    )


def cmd_scrape(args):
    """Executa busca manual agora."""
    from database       import get_scrape_config
    from scrapers.runner import run_all_scrapers

    config = get_scrape_config()
    if not config:
        print("⚠️  Sem configuração na Supabase. A usar defaults.")
        config = {}

    result = run_all_scrapers(
        districts    = args.districts or config.get("districts", ["Lisboa","Faro","Setubal"]),
        portals      = args.portals   or config.get("portals_enabled", ["olx_pt","imovirtual_pt","idealista_pt"]),
        tipos        = args.tipos     or config.get("property_types", ["apartamento","moradia"]),
        max_pages    = args.max_pages or config.get("max_pages", 10),
        country_code = args.country   or config.get("country_code", "PT"),
    )

    print(f"\n✅ Busca concluída:")
    print(f"   Encontrados:  {result['encontrados']}")
    print(f"   Novos:        {result['novos']}")
    print(f"   Duplicados:   {result['duplicados']}")
    print(f"   Distribuídos: {result['distribuidos']}")
    print(f"   Job ID:       {result['job_id']}")


def cmd_scheduler(_):
    from scheduler import start_scheduler
    start_scheduler()


def cmd_api(_):
    import uvicorn
    from config import API_HOST, API_PORT
    uvicorn.run("api.main:app", host=API_HOST, port=API_PORT, reload=False, log_level="info")


def cmd_all(_):
    """API + Scheduler em simultâneo."""
    import threading
    import uvicorn
    from config import API_HOST, API_PORT
    from scheduler import get_background_scheduler

    sched = get_background_scheduler()
    sched.start()
    logging.getLogger("k360").info("⏰ Scheduler activo")

    uvicorn.run("api.main:app", host=API_HOST, port=API_PORT, reload=False, log_level="info")


def cmd_demo(_):
    """Demo completa sem precisar de Supabase configurado."""
    print("\n🎬 MODO DEMO — K360 Crawler\n")
    from scrapers.olx        import OLXScraper
    from scrapers.imovirtual import ImovirtualScraper
    from enrichment.deduplication import generate_fingerprint, deduplicate_batch
    from enrichment.scoring  import enrich_lead

    all_leads = []
    for ScraperClass, districts, tipos in [
        (OLXScraper,        ["Lisboa","Faro"], ["apartamento","moradia"]),
        (ImovirtualScraper, ["Setubal"],       ["apartamento"]),
    ]:
        s = ScraperClass(districts=districts, tipos=tipos, max_pages=2)
        leads = s.scrape()
        print(f"  [{s.PORTAL_NAME}] {len(leads)} leads")
        all_leads.extend(leads)

    for l in all_leads:
        l["fingerprint"] = generate_fingerprint(
            l.get("telefone",""), l.get("email",""), l.get("listing_url","")
        )
    unique = deduplicate_batch(all_leads)
    for l in unique:
        enrich_lead(l)

    print(f"\n  Total: {len(all_leads)} → {len(unique)} únicos após dedup")
    quentes = [l for l in unique if l["temperatura"] == "quente"]
    mornos  = [l for l in unique if l["temperatura"] == "morno"]
    print(f"  🔴 Quentes: {len(quentes)}  🟡 Mornos: {len(mornos)}  🔵 Frios: {len(unique)-len(quentes)-len(mornos)}")

    if quentes:
        print(f"\n  Top lead quente:")
        top = max(unique, key=lambda x: x["pontuacao"])
        print(f"    Nome:       {top.get('nome_proprietario','N/A')}")
        print(f"    Tel:        {top.get('telefone','N/A')}")
        print(f"    Localização:{top.get('localizacao','N/A')}")
        print(f"    Pontuação:  {top.get('pontuacao')} / 100")
        print(f"    Temperatura:{top.get('temperatura')}")
        print(f"    Urgência:   {top.get('palavras_urgencia',[][:3])}")

    print("\n✅ Demo concluída\n")


def main():
    _setup_logging()
    parser = argparse.ArgumentParser(description="K360 Crawler — Angariação Automática")
    sub    = parser.add_subparsers(dest="command")

    # scrape
    p_scrape = sub.add_parser("scrape", help="Executa busca agora")
    p_scrape.add_argument("--districts", nargs="+")
    p_scrape.add_argument("--portals",   nargs="+")
    p_scrape.add_argument("--tipos",     nargs="+")
    p_scrape.add_argument("--max-pages", type=int, dest="max_pages")
    p_scrape.add_argument("--country",   default="PT")
    p_scrape.set_defaults(func=cmd_scrape)

    sub.add_parser("scheduler", help="Inicia scheduler").set_defaults(func=cmd_scheduler)
    sub.add_parser("api",       help="Inicia API REST").set_defaults(func=cmd_api)
    sub.add_parser("all",       help="API + Scheduler").set_defaults(func=cmd_all)
    sub.add_parser("demo",      help="Demo sem Supabase").set_defaults(func=cmd_demo)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()
