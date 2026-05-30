"""
K360 — Motor de Scraping via Firecrawl
Usa a API do Firecrawl para ultrapassar bloqueios em todos os portais.
Extrai dados estruturados com LLM — sem parsers manuais por site.
"""
import os
import time
import logging
import requests
from config import KEYWORDS_URGENCIA

logger = logging.getLogger("k360.firecrawl")

FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")
FIRECRAWL_BASE    = "https://api.firecrawl.dev/v1"

# ── Schema de extracção — o que queremos de cada anúncio ─────────────────────
LEAD_SCHEMA = {
    "type": "object",
    "properties": {
        "anuncios": {
            "type": "array",
            "description": "Lista de todos os anúncios imobiliários encontrados na página",
            "items": {
                "type": "object",
                "properties": {
                    "titulo":            {"type": "string",  "description": "Título completo do anúncio"},
                    "preco":             {"type": "string",  "description": "Preço do imóvel (ex: 185.000 €)"},
                    "tipologia":         {"type": "string",  "description": "Tipologia: T1, T2, T3, T4, V3, etc."},
                    "area_m2":           {"type": "string",  "description": "Área em metros quadrados"},
                    "tipo_imovel":       {"type": "string",  "description": "Apartamento, Moradia, Terreno, Comercial"},
                    "nome_proprietario": {"type": "string",  "description": "Nome do vendedor/proprietário se visível"},
                    "telefone":          {"type": "string",  "description": "Número de telefone do proprietário se visível"},
                    "email":             {"type": "string",  "description": "Email do proprietário se visível"},
                    "tipo_vendedor":     {"type": "string",  "description": "Particular ou Agência"},
                    "localizacao":       {"type": "string",  "description": "Localização completa do imóvel"},
                    "distrito":          {"type": "string",  "description": "Distrito (ex: Lisboa, Faro, Setúbal)"},
                    "concelho":          {"type": "string",  "description": "Concelho (ex: Cascais, Loulé, Almada)"},
                    "freguesia":         {"type": "string",  "description": "Freguesia se disponível"},
                    "descricao":         {"type": "string",  "description": "Descrição do anúncio (primeiros 500 chars)"},
                    "url_anuncio":       {"type": "string",  "description": "URL completa do anúncio"},
                    "fotos":             {"type": "array",   "description": "URLs das fotos do imóvel",
                                          "items": {"type": "string"}},
                    "data_publicacao":   {"type": "string",  "description": "Data de publicação ou 'há X dias'"},
                    "dias_no_mercado":   {"type": "integer", "description": "Número estimado de dias no mercado"},
                }
            }
        }
    },
    "required": ["anuncios"]
}

EXTRACT_PROMPT = """
Extrai TODOS os anúncios imobiliários desta página de um portal português.
Para cada anúncio obtém: título, preço, tipologia (T1/T2/T3...), área m², 
localização (distrito/concelho/freguesia), telefone e email do proprietário 
se visíveis, tipo de vendedor (Particular ou Agência), descrição, URL do anúncio, 
fotos disponíveis e data de publicação.
Inclui APENAS anúncios de particulares (proprietários diretos), não de agências imobiliárias.
Responde em português.
"""


def _headers():
    return {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type":  "application/json",
    }


def scrape_page(url: str) -> str:
    """
    Usa Firecrawl /scrape para obter o conteúdo de uma página.
    Retorna markdown limpo. 1 crédito por página.
    """
    resp = requests.post(
        f"{FIRECRAWL_BASE}/scrape",
        headers=_headers(),
        json={
            "url":     url,
            "formats": ["markdown"],
            "onlyMainContent": True,
            "waitFor": 2000,
        },
        timeout=60,
    )
    if resp.status_code != 200:
        logger.warning(f"Firecrawl scrape {resp.status_code}: {url[:60]}")
        return ""
    data = resp.json()
    return data.get("data", {}).get("markdown", "") or ""


def extract_leads_from_url(url: str) -> list:
    """
    Usa Firecrawl /extract com LLM para extrair leads estruturados de uma URL.
    Retorna lista de dicts com dados dos proprietários.
    Mais poderoso — usa LLM para compreender a página.
    """
    if not FIRECRAWL_API_KEY:
        logger.error("FIRECRAWL_API_KEY não definida")
        return []

    try:
        resp = requests.post(
            f"{FIRECRAWL_BASE}/extract",
            headers=_headers(),
            json={
                "urls":   [url],
                "prompt": EXTRACT_PROMPT,
                "schema": LEAD_SCHEMA,
            },
            timeout=90,
        )

        if resp.status_code == 402:
            logger.warning("Firecrawl: créditos esgotados — a usar scrape simples")
            return _extract_from_markdown(scrape_page(url), url)

        if resp.status_code != 200:
            logger.warning(f"Firecrawl extract {resp.status_code}: {url[:60]}")
            return _extract_from_markdown(scrape_page(url), url)

        data    = resp.json()
        raw     = data.get("data", {})

        # Firecrawl pode devolver directamente ou dentro de "extract"
        anuncios = (
            raw.get("anuncios") or
            raw.get("extract", {}).get("anuncios") or
            []
        )

        logger.info(f"Firecrawl extract: {len(anuncios)} anúncios em {url[:50]}")
        return [_normalise(a) for a in anuncios if a.get("titulo")]

    except Exception as e:
        logger.error(f"Firecrawl extract erro: {e}")
        return []


def _extract_from_markdown(markdown: str, source_url: str) -> list:
    """
    Fallback: extrai dados básicos do markdown quando o extract falha.
    Usa regex para apanhar telefones, preços e títulos.
    """
    import re
    leads = []

    # Divide por blocos de anúncio (linhas com preço)
    preco_pattern = re.compile(r'(\d[\d\s.,]*)\s*[€$]')
    phone_pattern = re.compile(r'\b(9[1236]\d{7}|2\d{8})\b')
    lines = markdown.split('\n')

    current: dict = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Título (linha com ##)
        if line.startswith('##') and len(line) > 5:
            if current.get('titulo'):
                leads.append(_normalise(current))
            current = {
                'titulo':      line.lstrip('#').strip(),
                'url_anuncio': source_url,
                'tipo_vendedor': 'Particular',
            }

        # Preço
        m = preco_pattern.search(line)
        if m and '€' in line and not current.get('preco'):
            current['preco'] = line.strip()

        # Telefone
        m = phone_pattern.search(line)
        if m and not current.get('telefone'):
            current['telefone'] = m.group(0)

    if current.get('titulo'):
        leads.append(_normalise(current))

    return leads[:50]  # Máximo 50 por página


def _normalise(raw: dict) -> dict:
    """Normaliza um anúncio para o formato k360_leads."""
    from enrichment.deduplication import generate_fingerprint
    from enrichment.scoring import extract_days_on_market

    # Garante tipo_vendedor
    tipo = raw.get("tipo_vendedor", "Particular")
    if any(w in (tipo or "").lower() for w in ["agência", "agencia", "remax", "era", "century"]):
        tipo = "Agência"
    else:
        tipo = "Particular"

    # Dias no mercado
    dias = raw.get("dias_no_mercado") or extract_days_on_market(raw.get("data_publicacao", ""))

    # Preço numérico
    preco_raw = raw.get("preco", "") or ""
    preco_num = None
    import re
    m = re.sub(r"[^\d]", "", preco_raw)
    if m and len(m) >= 4:
        preco_num = float(m)

    # Área numérica
    area_raw = raw.get("area_m2", "") or ""
    area_num = None
    m2 = re.search(r"(\d+(?:[.,]\d+)?)", area_raw)
    if m2:
        area_num = float(m2.group(1).replace(",", "."))

    telefone = (raw.get("telefone") or "").replace(" ", "").replace("-", "")
    email    = (raw.get("email") or "").lower().strip()
    url      = raw.get("url_anuncio") or ""

    lead = {
        "titulo":             raw.get("titulo", "")[:300],
        "tipo_imovel":        raw.get("tipo_imovel", "Imóvel"),
        "tipo_vendedor":      tipo,
        "preco":              preco_num,
        "preco_original":     preco_num,
        "area_m2":            area_num,
        "tipologia":          raw.get("tipologia", ""),
        "nome_proprietario":  raw.get("nome_proprietario", ""),
        "telefone":           telefone,
        "email":              email,
        "localizacao":        raw.get("localizacao", ""),
        "distrito":           raw.get("distrito", ""),
        "concelho":           raw.get("concelho", ""),
        "freguesia":          raw.get("freguesia", ""),
        "descricao":          (raw.get("descricao") or "")[:600],
        "listing_url":        url,
        "fotos":              raw.get("fotos", [])[:10],
        "data_publicacao":    raw.get("data_publicacao", ""),
        "dias_no_mercado":    dias,
        "preco_reduziu":      False,
        "palavras_urgencia":  [],
        "status":             "novo",
        "pontuacao":          0,
        "temperatura":        "frio",
        "fingerprint":        generate_fingerprint(telefone, email, url),
        "country_code":       "PT",
    }

    # Filtra agências
    if tipo == "Agência":
        return {}

    return lead


# ── Runner universal Firecrawl ────────────────────────────────────────────────

PORTAL_URLS = {
    "olx_pt": {
        "name": "OLX Portugal",
        "urls_template": "https://www.olx.pt/imoveis/{regiao}/{tipo}/?owner=private&page={page}",
        "regioes": {
            "Lisboa": "lisboa", "Faro": "faro", "Setubal": "setubal",
            "Cascais": "lisboa", "Porto": "porto",
        },
        "tipos": {"apartamento": "apartamentos", "moradia": "casas", "terreno": "terrenos"},
    },
    "imovirtual_pt": {
        "name": "Imovirtual",
        "urls_template": "https://www.imovirtual.com/venda/{tipo}/{regiao}/?ownerTypeSingleSelect=PRIVATE&page={page}",
        "regioes": {
            "Lisboa": "lisboa", "Faro": "algarve", "Setubal": "setubal",
            "Cascais": "lisboa", "Porto": "porto",
        },
        "tipos": {"apartamento": "apartamento", "moradia": "moradia", "terreno": "terrenos"},
    },
    "idealista_pt": {
        "name": "Idealista PT",
        "urls_template": "https://www.idealista.pt/venda-{tipo}/{regiao}-e-municipios/?tipologia=particular&pagina={page}",
        "regioes": {
            "Lisboa": "lisboa", "Faro": "algarve", "Setubal": "setubal",
            "Cascais": "cascais", "Porto": "porto",
        },
        "tipos": {"apartamento": "apartamentos", "moradia": "moradias", "terreno": "terrenos"},
    },
    "casa_sapo_pt": {
        "name": "Casa SAPO",
        "urls_template": "https://casa.sapo.pt/venda/{tipo}/{regiao}/?pn={page}",
        "regioes": {
            "Lisboa": "lisboa", "Faro": "faro", "Setubal": "setubal",
            "Cascais": "cascais", "Porto": "porto",
        },
        "tipos": {"apartamento": "apartamentos", "moradia": "moradias"},
    },
    "supercasa_pt": {
        "name": "Supercasa",
        "urls_template": "https://supercasa.pt/comprar-{tipo}/{regiao}?tipo-anunciante=particular&pagina={page}",
        "regioes": {
            "Lisboa": "lisboa", "Faro": "faro", "Setubal": "setubal",
            "Cascais": "cascais", "Porto": "porto",
        },
        "tipos": {"apartamento": "apartamentos", "moradia": "moradias"},
    },
    "custojusto_pt": {
        "name": "Custojusto",
        "urls_template": "https://www.custojusto.pt/imoveis/{tipo}?q={regiao}&o={page}",
        "regioes": {
            "Lisboa": "lisboa", "Faro": "faro", "Setubal": "setubal",
            "Cascais": "cascais", "Porto": "porto",
        },
        "tipos": {"apartamento": "apartamentos", "moradia": "casas-moradias"},
    },
}


def scrape_portal_firecrawl(
    portal_id:  str,
    districts:  list,
    tipos:      list,
    max_pages:  int = 5,
) -> list:
    """
    Scrapa um portal usando Firecrawl.
    Funciona em todos os portais sem bloqueios.
    """
    config = PORTAL_URLS.get(portal_id)
    if not config:
        logger.warning(f"Portal {portal_id} não configurado no Firecrawl scraper")
        return []

    all_leads = []
    seen_fps  = set()

    for district in districts:
        regiao = config["regioes"].get(district, district.lower())

        for tipo_key in tipos:
            tipo_val = config["tipos"].get(tipo_key)
            if not tipo_val:
                continue

            for page in range(1, max_pages + 1):
                url = config["urls_template"].format(
                    regiao=regiao, tipo=tipo_val, page=page
                )
                logger.info(f"[{config['name']}] {district}/{tipo_key} pág {page}")

                leads = extract_leads_from_url(url)

                if not leads:
                    logger.info(f"  Sem resultados — a parar")
                    break

                # Filtra duplicados intra-sessão
                novos = []
                for lead in leads:
                    fp = lead.get("fingerprint", "")
                    if fp and fp not in seen_fps:
                        seen_fps.add(fp)
                        lead["portal_origem"] = portal_id
                        lead["distrito"]      = lead.get("distrito") or district
                        novos.append(lead)

                all_leads.extend(novos)
                logger.info(f"  +{len(novos)} leads ({len(all_leads)} total)")

                # Delay respeitoso entre requests
                time.sleep(2)

                if len(all_leads) >= 300:
                    break

    return all_leads
