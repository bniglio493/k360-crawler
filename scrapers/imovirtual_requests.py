"""
Imovirtual — scraper com requests (filtro PRIVATE funciona correctamente)
"""
import re, time, logging, requests
from bs4 import BeautifulSoup

logger = logging.getLogger("k360.imovirtual")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "pt-PT,pt;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REGIAO_MAP = {
    "Lisboa":"lisboa","Setubal":"setubal","Cascais":"lisboa",
    "Porto":"porto","Faro":"algarve","Braga":"braga",
}
TIPO_MAP = {
    "apartamento":"apartamento","moradia":"moradia","terreno":"terrenos",
}
AGENCY_INDICATORS = [
    "remax","era imob","century 21","kw ","keller","coldwell","jll ",
    "savills","engel","porta da frente","habicasas","predimed",
    "imobiliária","imobiliaria","mediação imobiliária","mediacao imobiliaria",
    "n.º ami","nº ami","numero ami","número ami"," ami ","(ami",
    "agência imobiliária","agencia imobiliaria","consultor imobiliário",
    "consultor imobiliario","mediadora","s.a.","lda.","unipessoal",
    "grupo imob","decisoes e solucoes","decisões e soluções",
    "berkshire","sotheby","christie","exp realty","c21 ",
]

SKIP_EMAIL = ["imovirtual","idealista","olx","sapo","supercasa",
              "custojusto","google","facebook","sentry","cdn"]


def scrape_imovirtual(districts, tipos, max_pages=10):
    all_leads, seen_fps = [], set()

    for district in districts:
        regiao = REGIAO_MAP.get(district, district.lower())
        for tipo_key in tipos:
            tipo_val = TIPO_MAP.get(tipo_key, "apartamento")
            for page in range(1, max_pages + 1):
                url = (f"https://www.imovirtual.com/comprar/{tipo_val}/{regiao}/"
                       f"?ownerTypeSingleSelect=PRIVATE&nrAdsPerPage=72&page={page}")
                logger.info(f"[Imovirtual] {district}/{tipo_key} pág {page}")
                try:
                    r = requests.get(url, headers=HEADERS, timeout=15)
                    if r.status_code != 200:
                        logger.info(f"  Status {r.status_code} — stop")
                        break
                    soup = BeautifulSoup(r.text, "lxml")
                    arts = soup.select("article")
                    if not arts:
                        logger.info(f"  Sem artigos — stop")
                        break

                    novos = 0
                    for art in arts:
                        lead = _parse_article(art, district, tipo_key)
                        if not lead:
                            continue
                        fp = lead["fingerprint"]
                        if fp in seen_fps:
                            continue
                        seen_fps.add(fp)
                        all_leads.append(lead)
                        novos += 1

                    logger.info(f"  +{novos} particulares ({len(all_leads)} total)")
                    time.sleep(2)
                    if len(all_leads) >= 400:
                        break
                except Exception as e:
                    logger.error(f"  Erro: {e}")
                    break

    # Visita páginas de detalhe para obter email
    _enrich_detail_pages(all_leads)
    return all_leads


def _parse_article(art, district, tipo_key):
    from enrichment.deduplication import generate_fingerprint

    # Link do anúncio
    link_el = art.select_one("a[href*='/anuncio/'], a[href*='/pt/']")
    if not link_el:
        return None
    href = link_el.get("href", "")
    if not href.startswith("http"):
        href = "https://www.imovirtual.com" + href
    link = href.split("?")[0]
    if len(link) < 20:
        return None

    # Texto completo para filtros e extracção
    text = art.get_text(separator=" ", strip=True)

    # ── Filtro de agências ────────────────────────────────────
    if _is_agency(text):
        return None

    # ── Título a partir do slug da URL ────────────────────────
    titulo = _title_from_slug(link)
    if not titulo:
        # Fallback: texto após o preço
        parts = [p.strip() for p in text.split() if len(p.strip()) > 15
                 and "€" not in p and "..." not in p and "m²" not in p]
        titulo = parts[0][:200] if parts else f"Imóvel em {district}"

    # ── Preço ─────────────────────────────────────────────────
    preco = None
    pm = re.search(r"([\d\s.]+)\s*€", text.replace("\xa0", "").replace(" ", ""))
    if pm:
        p = re.sub(r"[^\d]", "", pm.group(1))
        if 4 <= len(p) <= 9:
            preco = float(p)

    # ── Tipologia ─────────────────────────────────────────────
    tip = re.search(r"\b(T[0-6]|V[2-6])\b", titulo + " " + text, re.IGNORECASE)
    tipologia = tip.group(0).upper() if tip else ""

    # ── Área ──────────────────────────────────────────────────
    area = None
    am = re.search(r"(\d+(?:[.,]\d+)?)\s*m[²2]", text)
    if am:
        area = float(am.group(1).replace(",", "."))

    # ── Localização ───────────────────────────────────────────
    localizacao = district
    for sel in ["address", "p[class*='css']", "[class*='location']", "[class*='local']"]:
        el = art.select_one(sel)
        if el:
            t = el.get_text(strip=True)
            if len(t) > 5 and "€" not in t:
                localizacao = t[:150]
                break

    # Extrai concelho da localização
    concelho = district
    if "," in localizacao:
        parts = [p.strip() for p in localizacao.split(",")]
        if parts:
            concelho = parts[0]

    # ── Email visível no card ─────────────────────────────────
    email = _extract_email(text)

    fp = generate_fingerprint("", email, link)

    return {
        "titulo":            titulo[:300],
        "tipo_imovel":       _infer_tipo(titulo + " " + tipo_key),
        "tipo_vendedor":     "Particular",
        "preco":             preco,
        "preco_original":    preco,
        "area_m2":           area,
        "tipologia":         tipologia,
        "telefone":          "",
        "email":             email,
        "nome_proprietario": "",
        "localizacao":       localizacao,
        "distrito":          district,
        "concelho":          concelho,
        "listing_url":       link,
        "portal_origem":     "imovirtual_pt",
        "country_code":      "PT",
        "status":            "novo",
        "pontuacao":         0,
        "temperatura":       "frio",
        "preco_reduziu":     False,
        "palavras_urgencia": [],
        "fingerprint":       fp,
    }


def _enrich_detail_pages(leads):
    """Visita cada anúncio para verificar 'Particular' e obter email."""
    session = requests.Session()
    session.headers.update(HEADERS)
    confirmed, removed, emails_found = 0, 0, 0

    to_remove = []
    for i, lead in enumerate(leads):
        url = lead.get("listing_url", "")
        if not url:
            continue
        try:
            r = session.get(url, timeout=10)
            if r.status_code != 200:
                continue
            text_page = r.text

            # Verifica se é agência na página de detalhe
            if _is_agency(text_page[:5000]):
                to_remove.append(i)
                removed += 1
                continue

            confirmed += 1

            # Tenta obter email
            if not lead.get("email"):
                email = _extract_email(text_page)
                if email:
                    lead["email"] = email
                    emails_found += 1

            time.sleep(0.8)
        except Exception:
            pass

    # Remove agências encontradas nas páginas de detalhe
    for i in reversed(to_remove):
        leads.pop(i)

    logger.info(f"  ✅ Verificação: {confirmed} particulares confirmados, "
                f"{removed} agências removidas, {emails_found} emails encontrados")


def _is_agency(text):
    t = text.lower()
    return any(ind in t for ind in AGENCY_INDICATORS)


def _title_from_slug(url):
    m = re.search(r"/anuncio/([^/?#]+)", url)
    if not m:
        return ""
    slug = m.group(1)
    slug = re.sub(r"-?ID\w+$", "", slug, flags=re.IGNORECASE)
    slug = re.sub(r"-\d{5,}$", "", slug)
    title = slug.replace("-", " ").strip()
    return title[:200] if len(title) > 10 else ""


def _extract_email(text):
    emails = re.findall(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b', text)
    for e in emails:
        if not any(d in e.lower() for d in SKIP_EMAIL):
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
    return "Imóvel"
