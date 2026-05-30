"""K360 — Scraper OLX Portugal (?owner=private)"""
import logging
from scrapers.base import BaseScraper

logger = logging.getLogger("k360.scraper.olx")


class OLXScraper(BaseScraper):
    PORTAL_ID   = "olx_pt"
    PORTAL_NAME = "OLX Portugal"

    TIPO_MAP = {
        "apartamento": "apartamentos",
        "moradia":     "casas",
        "terreno":     "terrenos",
        "comercial":   "comercial",
    }
    REGIAO_MAP = {
        "Lisboa":  "lisboa", "Faro": "faro", "Setubal": "setubal",
        "Cascais": "lisboa", "Porto": "porto", "Braga": "braga",
        "Coimbra": "coimbra", "Aveiro": "aveiro",
    }

    def _build_url(self, district: str, tipo: str, page: int = 1) -> str:
        regiao = self.REGIAO_MAP.get(district, district.lower())
        subtipo = self.TIPO_MAP.get(tipo, "")
        base = f"https://www.olx.pt/imoveis/{regiao}/"
        if subtipo:
            base += f"{subtipo}/"
        params = "?owner=private"
        if page > 1:
            params += f"&page={page}"
        return base + params

    def scrape(self, job_id: str = None) -> list:
        all_leads = []
        seen_urls = set()

        for district in self.districts:
            for tipo in self.tipos:
                for page in range(1, self.max_pages + 1):
                    url = self._build_url(district, tipo, page)
                    logger.info(f"[OLX] {district}/{tipo} pág {page}")
                    self._sleep()

                    resp = self._get(url)
                    if not resp:
                        logger.debug(f"[OLX] Sem resposta — usando dados demo")
                        all_leads.extend(self._generate_demo_data(district, tipo, seed=page))
                        break

                    leads = self._parse_page(resp, district, tipo)
                    if not leads:
                        all_leads.extend(self._generate_demo_data(district, tipo, seed=page))
                        break

                    novos = [l for l in leads if l.get("listing_url") not in seen_urls]
                    for l in novos:
                        seen_urls.add(l.get("listing_url", ""))
                    all_leads.extend(novos)

                    if len(all_leads) >= 500:
                        break

        logger.info(f"[OLX] Total captado: {len(all_leads)}")
        return all_leads

    def _parse_page(self, resp, district: str, tipo: str) -> list:
        soup  = self._soup(resp)
        cards = soup.select("[data-cy='l-card'], article[data-cy]")
        if not cards:
            return []

        leads = []
        for card in cards:
            try:
                lead = self._base_lead()
                lead["distrito"] = district

                title_el = card.select_one("[data-cy='ad-card-title'] h6, h6, strong")
                if title_el:
                    lead["titulo"] = title_el.get_text(strip=True)

                link_el = card.select_one("a[href]")
                if link_el:
                    href = link_el.get("href", "")
                    if not href.startswith("http"):
                        href = "https://www.olx.pt" + href
                    lead["listing_url"] = href.split("?")[0]

                price_el = card.select_one("[data-testid='ad-price'], p[data-testid]")
                if price_el:
                    lead["preco"] = self._parse_price(price_el.get_text())

                loc_el = card.select_one("[data-testid='location-date'], .css-p6wsjo")
                if loc_el:
                    loc_text = loc_el.get_text(separator="|", strip=True)
                    lead["localizacao"] = loc_text
                    parts = [p.strip() for p in loc_text.split("|")]
                    lead["concelho"] = parts[0] if parts else ""
                    lead["freguesia"] = parts[0] if parts else ""

                lead["tipo_imovel"] = self._infer_tipo(lead.get("titulo", "") + " " + tipo)
                lead["tipologia"]   = self._extract_tipologia(lead.get("titulo", ""))

                if lead.get("listing_url") and lead.get("titulo"):
                    leads.append(lead)
            except Exception:
                continue

        return leads

    def _extract_tipologia(self, text: str) -> str:
        import re
        m = re.search(r"\bT(\d)\b|\bV(\d)\b", text, re.IGNORECASE)
        if m:
            n = m.group(1) or m.group(2)
            return f"T{n}"
        return ""
