"""
K360 — Scraper Playwright
Extrai: título, preço, local, tipologia, área, link, email (quando visível)
Telefone: agente clica no link do anúncio
"""
import re, time, logging, requests
from bs4 import BeautifulSoup

logger = logging.getLogger("k360.playwright")

BASE_URLS = {
    "olx_pt":        "https://www.olx.pt",
    "imovirtual_pt": "https://www.imovirtual.com",
    "idealista_pt":  "https://www.idealista.pt",
    "casa_sapo_pt":  "https://casa.sapo.pt",
    "supercasa_pt":  "https://supercasa.pt",
    "custojusto_pt": "https://www.custojusto.pt",
}

PORTAL_CONFIG = {
    "olx_pt": {
        "name": "OLX Portugal",
        "urls": [
            "https://www.olx.pt/imoveis/{regiao}/?search[filter_enum_owner][0]=private",
        ],
        "item_sel": "li[data-cy], div[data-cy='l-card'], li[class*='css-']",
        "regioes": {"Lisboa":"lisboa","Setubal":"setubal","Cascais":"lisboa"},
        "tipos": {"apartamento":"","moradia":"","terreno":""},
    },
    "imovirtual_pt": {
        "name": "Imovirtual",
        "urls": [
            "https://www.imovirtual.com/comprar/{tipo}/{regiao}/?ownerTypeSingleSelect=PRIVATE&nrAdsPerPage=72",
        ],
        "item_sel": "article",
        "regioes": {"Lisboa":"lisboa","Setubal":"setubal","Cascais":"lisboa"},
        "tipos": {"apartamento":"apartamento","moradia":"moradia","terreno":"terrenos"},
    },
    "idealista_pt": {
        "name": "Idealista Portugal",
        "urls": [
            "https://www.idealista.pt/venda-{tipo}/{regiao}-e-municipios/?tipologia=particular",
        ],
        "item_sel": "article.item",
        "regioes": {"Lisboa":"lisboa","Setubal":"setubal","Cascais":"cascais"},
        "tipos": {"apartamento":"apartamentos","moradia":"moradias","terreno":"terrenos"},
    },
    "casa_sapo_pt": {
        "name": "Casa SAPO",
        "urls": [
            "https://casa.sapo.pt/venda/{tipo}/{regiao}/",
        ],
        "item_sel": "div[class*='PropertyCard'], div[class*='property-item'], article",
        "regioes": {"Lisboa":"lisboa","Setubal":"setubal","Cascais":"cascais"},
        "tipos": {"apartamento":"apartamentos","moradia":"moradias"},
    },
    "supercasa_pt": {
        "name": "Supercasa",
        "urls": [
            "https://supercasa.pt/comprar-{tipo}/{regiao}?tipo-anunciante=particular",
        ],
        "item_sel": "article, div[class*='PropertyCard']",
        "regioes": {"Lisboa":"lisboa","Setubal":"setubal","Cascais":"cascais"},
        "tipos": {"apartamento":"apartamentos","moradia":"moradias"},
    },
    "custojusto_pt": {
        "name": "Custojusto",
        "urls": [
            "https://www.custojusto.pt/portugal/imoveis-habitacao/{tipo}/",
        ],
        "item_sel": "li[class*='tw-'], div[class*='AdCard']",
        "regioes": {"Lisboa":"lisboa","Setubal":"setubal","Cascais":"cascais"},
        "tipos": {"apartamento":"apartamentos","moradia":"casas-moradias"},
    },
}

SKIP_EMAIL_DOMAINS = ["imovirtual","idealista","olx","sapo","supercasa","custojusto",
                       "google","facebook","sentry","cdn","pixel"]

def scrape_with_playwright(portal_id, districts, tipos, max_pages=5):
    from playwright.sync_api import sync_playwright
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from enrichment.deduplication import generate_fingerprint

    config = PORTAL_CONFIG.get(portal_id)
    if not config:
        logger.warning(f"Portal {portal_id} não configurado")
        return []

    all_leads, seen_fps = [], set()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox","--disable-blink-features=AutomationControlled","--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="pt-PT",
            viewport={"width":1280,"height":900},
        )
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

        for district in districts:
            regiao = config["regioes"].get(district, district.lower())
            for tipo_key in tipos:
                tipo_val = config["tipos"].get(tipo_key, tipo_key)
                for pg in range(1, max_pages + 1):
                    url_tmpl = config["urls"][0]
                    url = url_tmpl.format(regiao=regiao, tipo=tipo_val, page=pg)
                    logger.info(f"[{config['name']}] {district}/{tipo_key} pág {pg}")
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        time.sleep(3)
                        html  = page.content()
                        soup  = BeautifulSoup(html, "lxml")
                        items = soup.select(config["item_sel"])
                        if not items:
                            logger.info(f"  Sem items — stop")
                            break
                        leads = _parse_items(items, portal_id, district, BASE_URLS.get(portal_id,""))
                        novos = 0
                        for lead in leads:
                            fp = lead.get("fingerprint","")
                            if fp and fp not in seen_fps:
                                seen_fps.add(fp)
                                all_leads.append(lead)
                                novos += 1
                        logger.info(f"  +{novos} leads ({len(all_leads)} total)")
                        time.sleep(2)
                        if len(all_leads) >= 400:
                            break
                    except Exception as e:
                        logger.error(f"  Erro pág {pg}: {e}")
                        break

        browser.close()

    # Enriquece com email das páginas de detalhe
    _enrich_emails(all_leads)
    return all_leads



AGENCY_INDICATORS = [
    'remax','era imob','century 21','kw ','keller','coldwell','jll ','savills',
    'engel','porta da frente','habicasas','predimed','imobiliária','imobiliaria',
    'mediação imobiliária','mediacao imobiliaria','ami ','n.º ami','nº ami',
    'numero ami','número ami','agência imobiliária','agencia imobiliaria',
    'consultor imobiliário','consultor imobiliario','mediadora',
    's.a.','lda.','unipessoal','real estate','properties group',
    'grupo imob','decisoes e solucoes','decisões e soluções',
    'luximos','square view','casas do barlavento','berkshire',
    'sothebys','christie','imometrics','c21 ','exp realty',
]

def _is_agency(text: str) -> bool:
    t = text.lower()
    return any(ind in t for ind in AGENCY_INDICATORS)

def _parse_items(items, portal_id, district, base_url):
    from enrichment.deduplication import generate_fingerprint
    leads = []
    for item in items:
        try:
            text = item.get_text(separator=" | ", strip=True)
            if len(text) < 20:
                continue

            # ── Filtro agências — rejeita imediatamente ───────────
            if _is_agency(text):
                continue
                continue

            # ── Link ─────────────────────────────────────────────
            link = ""
            for a in item.select("a[href]"):
                href = a.get("href","")
                if len(href) > 10 and href not in ("/",) and "javascript" not in href:
                    if not href.startswith("http"):
                        href = base_url + href
                    link = href.split("?")[0]
                    break
            if not link:
                continue

            # ── Título: tenta URL slug primeiro ──────────────────
            titulo = _title_from_url(link) or _title_from_text(text)
            if not titulo:
                continue

            # ── Preço ─────────────────────────────────────────────
            preco_num = None
            pm = re.search(r"([\d\s.]+)\s*€", text.replace("\xa0","").replace(" ",""))
            if pm:
                p = re.sub(r"[^\d]","", pm.group(1))
                if 4 <= len(p) <= 9:
                    preco_num = float(p)

            # ── Tipologia ─────────────────────────────────────────
            tip = re.search(r"\b(T[0-6]|V[2-6]|t[0-6])\b", titulo + " " + text)
            tipologia = tip.group(0).upper() if tip else ""

            # ── Área ──────────────────────────────────────────────
            area = None
            am = re.search(r"(\d+(?:[.,]\d+)?)\s*m[²2]", text)
            if am:
                area = float(am.group(1).replace(",","."))

            # ── Tipo imóvel ───────────────────────────────────────
            tipo_imovel = _infer_tipo(titulo + " " + text)

            # ── Email visível na listagem ─────────────────────────
            email = _extract_email(text)

            # ── Localização ───────────────────────────────────────
            localizacao = district
            for sel in ["[class*='location']","[class*='local']","address","[class*='cidade']","[class*='place']"]:
                el = item.select_one(sel)
                if el:
                    t = el.get_text(strip=True)
                    if len(t) > 3:
                        localizacao = t[:120]
                        break

            fp = generate_fingerprint("", email, link)
            leads.append({
                "titulo":            titulo[:300],
                "tipo_imovel":       tipo_imovel,
                "tipo_vendedor":     "Particular",
                "preco":             preco_num,
                "preco_original":    preco_num,
                "area_m2":           area,
                "tipologia":         tipologia,
                "telefone":          "",
                "email":             email,
                "nome_proprietario": "",
                "localizacao":       localizacao,
                "distrito":          district,
                "concelho":          district,
                "listing_url":       link,
                "portal_origem":     portal_id,
                "country_code":      "PT",
                "status":            "novo",
                "pontuacao":         0,
                "temperatura":       "frio",
                "preco_reduziu":     False,
                "palavras_urgencia": [],
                "fingerprint":       fp,
            })
        except Exception:
            continue
    return leads


def _enrich_emails(leads):
    """Visita cada página de detalhe para tentar encontrar email."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "pt-PT,pt;q=0.9",
    }
    enriched = 0
    for lead in leads:
        if lead.get("email") or not lead.get("listing_url"):
            continue
        try:
            r = requests.get(lead["listing_url"], headers=headers, timeout=10)
            if r.status_code == 200:
                email = _extract_email(r.text)
                if email:
                    lead["email"] = email
                    enriched += 1
            time.sleep(0.5)
        except Exception:
            pass
    if enriched:
        logger.info(f"  📧 {enriched} emails encontrados nas páginas de detalhe")


def _title_from_url(url):
    """Extrai título legível do slug da URL."""
    for pattern in [
        r"/anuncio/([^/?#]+)",
        r"/imovel/([^/?#]+)",
        r"/properties/([^/?#]+)",
        r"/([^/?#]{15,})-\d+$",
    ]:
        m = re.search(pattern, url)
        if m:
            slug = m.group(1)
            slug = re.sub(r"[-_]?ID\w+$", "", slug, flags=re.IGNORECASE)
            slug = re.sub(r"-\d{5,}$", "", slug)
            title = slug.replace("-"," ").replace("_"," ").strip()
            if len(title) > 10:
                return title[:200]
    return ""


def _title_from_text(text):
    """Extrai título a partir do texto completo do item."""
    skip = {"€","m²","m2","t0","t1","t2","t3","t4","v3","v4","...","tipologia",
            "preço","quartos","wc","área","casas","apartamentos","moradias"}
    for part in text.split("|"):
        p = part.strip()
        p_lower = p.lower()
        if (15 < len(p) < 250 and
            "€" not in p and
            "..." not in p and
            not p_lower.startswith(tuple(skip)) and
            not re.match(r"^\d+", p)):
            return p[:200]
    return ""


def _extract_email(text):
    """Extrai email do texto, filtrando domínios de sistema."""
    emails = re.findall(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b', text)
    for e in emails:
        if not any(d in e.lower() for d in SKIP_EMAIL_DOMAINS):
            return e.lower()
    return ""


def _infer_tipo(text):
    t = text.lower()
    if any(w in t for w in ["apartamento","t0","t1","t2","t3","t4","andar"]):
        return "Apartamento"
    if any(w in t for w in ["moradia","vivenda","villa","v3","v4","v5"]):
        return "Moradia"
    if "terreno" in t:
        return "Terreno"
    if any(w in t for w in ["comercial","loja","escritório"]):
        return "Comercial"
    return "Imóvel"
