import re, time, logging, requests
from bs4 import BeautifulSoup
from datetime import date as _date

logger = logging.getLogger("k360.real")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "pt-PT,pt;q=0.9",
}
AGENCY = ['remax','era imob','century 21','kw ','keller','imobiliaria','n.º ami','nº ami','mediacao','grupo re/','porta da frente','habicasas','predimed','berkshire','sotheby']
SKIP_EMAIL = ['imovirtual','olx','sapo','custojusto','google','facebook','sentry','microsoft','apple','cdn']
DISTRITOS_PT = ['Lisboa','Porto','Braga','Setúbal','Setubal','Faro','Aveiro','Coimbra','Viseu','Évora','Evora','Beja','Leiria','Santarém','Santarem','Guarda','Castelo Branco','Portalegre','Viana do Castelo','Vila Real','Bragança','Braganca','Funchal']
MESES_PT = {'janeiro':1,'fevereiro':2,'março':3,'abril':4,'maio':5,'junho':6,'julho':7,'agosto':8,'setembro':9,'outubro':10,'novembro':11,'dezembro':12}

def _parse_data_pt(s):
    if not s: return None
    m = re.search(r'(\d+)\s+de\s+(\w+)(?:\s+de\s+(\d{4}))?', s, re.IGNORECASE)
    if m:
        day = int(m.group(1))
        month = MESES_PT.get(m.group(2).lower(), 0)
        year = int(m.group(3)) if m.group(3) else _date.today().year
        if month:
            try: return _date(year, month, day)
            except: pass
    m2 = re.search(r'(\d{4})-(\d{2})-(\d{2})', s)
    if m2:
        try: return _date(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))
        except: pass
    return None

def _dias_mercado(data_str):
    d = _parse_data_pt(data_str)
    if d: return max(0, (_date.today() - d).days)
    return None

def _temperatura(dias):
    if dias is None: return "frio"
    if dias <= 15:   return "quente"
    if dias <= 90:   return "morno"
    return "frio"

PORTALS = {
    "olx_pt": {
        "name": "OLX Portugal",
        "base": "https://www.olx.pt",
        "search": "https://www.olx.pt/imoveis/{tipo}/{regiao}/?search[filter_float_price:from]=30000&page={page}",
        "regioes": {"Lisboa":"lisboa","Setubal":"setubal","Porto":"porto","Faro":"faro","Braga":"braga","Aveiro":"aveiro","Coimbra":"coimbra","Leiria":"leiria","Santarem":"santarem","Evora":"evora","Beja":"beja","Viseu":"viseu","Guarda":"guarda","Castelo Branco":"castelo-branco","Portalegre":"portalegre","Viana do Castelo":"viana-do-castelo","Vila Real":"vila-real","Braganca":"braganca","Funchal":"funchal"},
        "tipos": {"apartamento":"apartamento-casa-a-venda","moradia":"casas-moradias-para-arrendar-vender","terreno":"terrenos"},
        "get_links": lambda soup, base: list(set([(base+a.get('href','')).split('?')[0] if not a.get('href','').startswith('http') else a.get('href','').split('?')[0] for a in soup.select('a[href*="/d/anuncio/"]') if len(a.get('href',''))>20])),
        "is_particular": lambda t: bool(re.search(r'\bParticular\b', t[:60000])),
    },
    "custojusto_pt": {
        "name": "Custojusto",
        "base": "https://www.custojusto.pt",
        "search": "https://www.custojusto.pt/{regiao}/imobiliario/{tipo}/",
        "regioes": {"Lisboa":"lisboa","Setubal":"setubal","Porto":"porto","Faro":"faro","Braga":"braga","Aveiro":"aveiro","Coimbra":"coimbra","Leiria":"leiria","Santarem":"santarem","Evora":"evora","Beja":"beja","Viseu":"viseu","Guarda":"guarda","Castelo Branco":"castelo-branco","Portalegre":"portalegre","Viana do Castelo":"viana-do-castelo","Vila Real":"vila-real","Braganca":"braganca"},
        "tipos": {"apartamento":"apartamentos","moradia":"moradias","terreno":"terrenos"},
        "get_links": lambda soup, base: list(set([(base+a.get('href','')).split('?')[0] if not a.get('href','').startswith('http') else a.get('href','').split('?')[0] for a in soup.select('a[href*="/imobiliario/"]') if re.search(r'\d{6,}$', a.get('href','').split('?')[0].rstrip('/'))])),
        "is_particular": lambda t: not (bool(re.search(r'\bAMI\s*\d+', t)) or any(ag in t.lower()[:10000] for ag in AGENCY)),
    },
    "imovirtual_pt": {
        "name": "Imovirtual",
        "base": "https://www.imovirtual.com",
        "search": "https://www.imovirtual.com/comprar/{tipo}/{regiao}/?nrAdsPerPage=72&page={page}",
        "regioes": {"Lisboa":"lisboa","Setubal":"setubal","Porto":"porto","Faro":"algarve","Braga":"braga","Aveiro":"aveiro","Coimbra":"coimbra","Leiria":"leiria","Santarem":"santarem","Evora":"evora","Beja":"beja","Viseu":"viseu","Guarda":"guarda","Castelo Branco":"castelo-branco","Portalegre":"portalegre","Viana do Castelo":"viana-do-castelo","Vila Real":"vila-real","Braganca":"braganca","Funchal":"madeira"},
        "tipos": {"apartamento":"apartamento","moradia":"moradia","terreno":"terrenos"},
        "get_links": lambda soup, base: list(set([(base+a.get('href','')).split('?')[0] if not a.get('href','').startswith('http') else a.get('href','').split('?')[0] for a in soup.select('a[href*="/anuncio/"]') if len(a.get('href',''))>20 and not a.get('href','').endswith('/anuncio/')])),
        "is_particular": lambda t: bool(re.search(r'tipo de anunciante\s*[:\-]\s*particular', t.lower())),
    },
    "casa_sapo_pt": {
        "name": "Casa SAPO",
        "base": "https://casa.sapo.pt",
        "search": "https://casa.sapo.pt/comprar-{tipo}/{regiao}/?pn={page}",
        "regioes": {
            "Lisboa":"lisboa","Cascais":"cascais","Oeiras":"oeiras","Amadora":"amadora",
            "Vila Franca de Xira":"vila-franca-de-xira","Loures":"loures","Sintra":"sintra",
            "Odivelas":"odivelas","Mafra":"mafra",
            "Almada":"almada","Barreiro":"barreiro","Moita":"moita","Montijo":"montijo",
            "Seixal":"seixal","Sesimbra":"sesimbra","Setubal":"setubal","Palmela":"palmela",
            "Alcochete":"alcochete",
            "Albufeira":"albufeira","Portimao":"portimao","Lagoa":"lagoa",
            "Faro":"faro","Loule":"loule","Silves":"silves","Lagos":"lagos",
            "Tavira":"tavira","Olhao":"olhao","Vilamoura":"vilamoura",
            "Porto":"porto","Faro":"faro","Braga":"braga","Aveiro":"aveiro","Coimbra":"coimbra",
            "Leiria":"leiria","Santarem":"santarem","Evora":"evora","Beja":"beja",
            "Viseu":"viseu","Guarda":"guarda","Castelo Branco":"castelo-branco",
            "Portalegre":"portalegre","Viana do Castelo":"viana-do-castelo",
            "Vila Real":"vila-real","Braganca":"braganca","Funchal":"funchal",
        },
        "tipos": {"apartamento":"apartamentos","moradia":"moradias","terreno":"terrenos"},
        "get_links": lambda soup, base: list(set(["https://casa.sapo.pt/" + m for m in re.findall(r'comprar-[a-z0-9\-]+-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.html', soup.decode_contents() if hasattr(soup, "decode_contents") else str(soup))])),
        "is_particular": lambda t: not bool(re.search(r'Licen[çc]a AMI[:\s]', t)),
    },
}


def scrape_portal(portal_id, districts, tipos, max_pages=10):
    cfg = PORTALS.get(portal_id)
    if not cfg: return []
    all_leads, seen_urls, seen_fps = [], set(), set()
    session = requests.Session()
    session.headers.update(HEADERS)
    # Headers especiais para Casa SAPO
    if portal_id == "casa_sapo_pt":
        session.headers.update({
            "Referer": "https://casa.sapo.pt/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        time.sleep(3)  # delay inicial

    for district in districts:
        regiao = cfg["regioes"].get(district, district.lower())
        for tipo_key in tipos:
            tipo_val = cfg["tipos"].get(tipo_key, "")
            if not tipo_val: continue
            pages = range(1, 2) if portal_id == "custojusto_pt" else range(1, max_pages+1)
            for page in pages:
                url = cfg["search"].format(tipo=tipo_val, regiao=regiao, page=page)
                logger.info(f"[{cfg['name']}] {district}/{tipo_key} pág {page}")
                try:
                    r = session.get(url, timeout=15)
                    if r.status_code != 200: break
                    soup = BeautifulSoup(r.text, "lxml")
                    links = cfg["get_links"](soup, cfg["base"])
                    if not links:
                        logger.info("  Sem links — stop")
                        break
                    new_urls = [u for u in links if u not in seen_urls]
                    seen_urls.update(new_urls)
                    logger.info(f"  {len(new_urls)} anúncios para verificar")
                    for listing_url in new_urls:
                        lead = _get_lead(session, listing_url, portal_id, district, cfg["is_particular"])
                        if not lead: continue
                        fp = lead.get("fingerprint","")
                        if fp and fp not in seen_fps:
                            seen_fps.add(fp)
                            all_leads.append(lead)
                    logger.info(f"  Particulares: {len(all_leads)}")
                    time.sleep(1.5)
                    if len(all_leads) >= 400: return all_leads
                except Exception as e:
                    logger.error(f"  Erro: {e}")
                    break
    logger.info(f"[{cfg['name']}] Total: {len(all_leads)}")
    return all_leads


def _get_lead(session, url, portal_id, district, check_fn):
    from enrichment.deduplication import generate_fingerprint
    try:
        time.sleep(0.8)
        r = session.get(url, timeout=12)
        if r.status_code != 200: return None
        html_raw = r.text
        soup = BeautifulSoup(html_raw, "lxml")
        for tag in soup.select("nav,footer,header,script,style"):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)

        if not check_fn(text): return None

        lower = text.lower()
        if any(w in lower[:3000] for w in ["arrendar","arrendamento","alugar","aluguer","renda mensal"]):
            if not any(w in lower[:1000] for w in ["venda","vender","comprar","preco de venda"]):
                return None

        titulo = ""
        for sel in ["h1","h2"]:
            el = soup.select_one(sel)
            if el:
                t = el.get_text(strip=True)
                if 10 < len(t) < 300 and "€" not in t and len(t.split()) > 2:
                    titulo = t
                    break
        if not titulo: titulo = _slug(url)
        if not titulo: return None

        preco = None
        pm = re.search(r"([\d\s.]+)\s*€", text.replace("\xa0",""))
        if pm:
            p = re.sub(r"[^\d]","", pm.group(1))
            if 4 <= len(p) <= 9: preco = float(p)

        tip = re.search(r"\b(T[0-6]|V[2-6])\b", titulo+" "+text[:2000], re.IGNORECASE)
        tipologia = tip.group(0).upper() if tip else ""
        area = None
        am = re.search(r"(\d+(?:[.,]\d+)?)\s*m[²2]", text[:4000])
        if am:
            try: area = float(am.group(1).replace(",","."))
            except: pass

        emails = re.findall(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b', text)
        email = next((e for e in emails if not any(d in e.lower() for d in SKIP_EMAIL)), "")

        localizacao = district
        distrito_real = district
        concelho = district
        freguesia = ""
        nome = ""
        data_pub = ""
        descricao = ""

        if portal_id == "olx_pt":
            dm = re.search(r'Publicad[oa]\s+(\d+\s+de\s+\w+(?:\s+de\s+\d{4})?)', text, re.IGNORECASE)
            if dm: data_pub = dm.group(1).strip()
            else:
                datas = re.findall(r'"(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}', html_raw)
                hoje = _date.today()
                validas = []
                for d in datas:
                    try:
                        pts = d.split('-')
                        dt = _date(int(pts[0]),int(pts[1]),int(pts[2]))
                        if dt <= hoje: validas.append((dt,d))
                    except: pass
                if validas:
                    validas.sort(key=lambda x: x[0])
                    data_pub = validas[0][1]
            loc_m = re.search(r'Localiza[çc][aã]o\s+(.+?)\s+Ver localiza', text, re.IGNORECASE|re.DOTALL)
            if loc_m:
                loc_text = loc_m.group(1).replace("\n"," ").strip()
                localizacao = loc_text[:150]
                for d in DISTRITOS_PT:
                    if d.lower() in loc_text.lower():
                        distrito_real = d
                        break
                loc_clean = loc_text
                for d in DISTRITOS_PT:
                    loc_clean = re.sub(rf'\b{d}\b','',loc_clean,flags=re.IGNORECASE).strip().strip(",").strip()
                if "," in loc_clean:
                    parts = [p.strip() for p in loc_clean.split(",")]
                    freguesia = parts[0]
                    concelho = parts[-1] if len(parts)>1 else parts[0]
                else:
                    concelho = loc_clean.strip()
            ul = soup.select_one("a[href*='/ads/user/']")
            if ul: nome = ul.get_text(strip=True).split("No OLX")[0].strip()
            mem_m = re.search(r'No OLX desde\s+([^E]+?)(?:Esteve|$)', text, re.IGNORECASE)
            id_m = re.search(r'ID:\s*(\d+)', text)
            partes = []
            if mem_m: partes.append("No OLX desde " + mem_m.group(1).strip())
            if id_m: partes.append("ID: " + id_m.group(1))
            descricao = " | ".join(partes)

        elif portal_id == "custojusto_pt":
            if re.search(r'"companyAd"\s*:\s*true', html_raw): return None
            lt_m = re.search(r'"listTime"\s*:\s*"(\d{4}-\d{2}-\d{2})', html_raw)
            if lt_m: data_pub = lt_m.group(1)
            nome_m = re.search(r'"name"\s*:\s*"([^"]{3,50})"', html_raw)
            if nome_m: nome = nome_m.group(1).strip()
            loc_m = re.search(r'Localiza[çc][aã]o\s+([\w\s]+ - [\w\s]+ - [\w\s,]+?)(?:\s+PRO|\s+Anunciante|\s+Konsult)', text, re.IGNORECASE)
            if loc_m:
                parts = [p.strip() for p in loc_m.group(1).split(" - ")]
                if len(parts) >= 3:
                    distrito_real = parts[0]
                    concelho = parts[1]
                    freguesia = parts[2]
                    localizacao = loc_m.group(1).strip()
            else:
                cm = re.search(r'Concelho\s+([\w\s]+?)\s+Freguesia', text, re.IGNORECASE)
                fm = re.search(r'Freguesia\s+([\w\s,]+?)(?:\s+Id|\s+PRO)', text, re.IGNORECASE)
                if cm: concelho = cm.group(1).strip()
                if fm: freguesia = fm.group(1).strip()
                localizacao = " - ".join(filter(None,[distrito_real,concelho,freguesia]))

        elif portal_id == "imovirtual_pt":
            dt_m = re.search(r'"(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}', html_raw)
            if dt_m: data_pub = dt_m.group(1)
            loc_m = re.search(r'Localiza[çc][aã]o\s*[:\-]?\s*([^\n]{5,100})', text, re.IGNORECASE)
            if loc_m:
                loc_text = loc_m.group(1).strip()[:150]
                localizacao = loc_text
                for d in DISTRITOS_PT:
                    if d.lower() in loc_text.lower():
                        distrito_real = d
                        break
                parts = [p.strip() for p in loc_text.split(',')]
                if len(parts) >= 2:
                    freguesia = parts[0]
                    concelho = parts[1]

        elif portal_id == "casa_sapo_pt":
            dt_m = re.search(r'"(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}', html_raw)
            if dt_m: data_pub = dt_m.group(1)
            anunc_m = re.search(r'Anunciante\s+([\w\sÀ-ú]{3,50}?)\s+Ver', text)
            if anunc_m: nome = anunc_m.group(1).strip()
            loc_m = re.search(r'Localiza[çc][aã]o\s*[:\-]?\s*([^\n]{5,100})', text, re.IGNORECASE)
            if loc_m:
                loc_text = loc_m.group(1).strip()[:150]
                localizacao = loc_text
                for d in DISTRITOS_PT:
                    if d.lower() in loc_text.lower():
                        distrito_real = d
                        break

        dias = _dias_mercado(data_pub)

        return {
            "titulo":            titulo[:300],
            "tipo_imovel":       _tipo(titulo),
            "tipo_vendedor":     "Particular",
            "preco":             preco,
            "preco_original":    preco,
            "area_m2":           area,
            "tipologia":         tipologia,
            "telefone":          "",
            "email":             email,
            "nome_proprietario": nome,
            "localizacao":       localizacao,
            "distrito":          distrito_real,
            "concelho":          concelho,
            "freguesia":         freguesia,
            "listing_url":       url,
            "portal_origem":     portal_id,
            "data_publicacao":   data_pub,
            "dias_no_mercado":   dias if dias is not None else 0,
            "descricao":         descricao[:500],
            "country_code":      "PT",
            "status":            "novo",
            "pontuacao":         0,
            "temperatura":       _temperatura(dias) if dias is not None else "frio",
            "preco_reduziu":     False,
            "palavras_urgencia": [],
            "fingerprint":       generate_fingerprint("", email, url),
        }
    except Exception as e:
        logger.error(f"  Erro {url[:50]}: {e}")
        return None


def _slug(url):
    for pat in [r"/anuncio/([^/?#]+)",r"/d/anuncio/([^/?#]+)",r"/imobiliario/[^/]+/([^/?#]+)"]:
        m = re.search(pat, url)
        if m:
            slug = re.sub(r"-?ID\w+$","",m.group(1),flags=re.IGNORECASE)
            slug = re.sub(r"-\d{5,}$","",slug)
            t = slug.replace("-"," ").strip()
            if len(t) > 10: return t[:200]
    return ""


def _tipo(text):
    t = text.lower()
    if any(w in t for w in ["apartamento","t0","t1","t2","t3","t4","andar","duplex"]): return "Apartamento"
    if any(w in t for w in ["moradia","vivenda","villa","v3","v4","v5","quinta"]):     return "Moradia"
    if "terreno" in t: return "Terreno"
    return "Imóvel"
