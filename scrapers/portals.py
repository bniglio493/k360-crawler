"""K360 — Scrapers: Idealista PT, Casa SAPO, Supercasa, Custojusto"""
import logging
from scrapers.base import BaseScraper

logger = logging.getLogger("k360.scraper")


# ── Idealista Portugal ────────────────────────────────────────────────────────
class IdealistaScraper(BaseScraper):
    PORTAL_ID   = "idealista_pt"
    PORTAL_NAME = "Idealista Portugal"

    TIPO_MAP = {"apartamento":"apartamentos","moradia":"moradias","terreno":"terrenos"}
    REGIAO_MAP = {"Lisboa":"lisboa","Faro":"algarve","Setubal":"setubal",
                  "Cascais":"cascais","Porto":"porto","Braga":"braga"}

    def _build_url(self, district: str, tipo: str, page: int = 1) -> str:
        regiao = self.REGIAO_MAP.get(district, district.lower().replace(" ","-"))
        t      = self.TIPO_MAP.get(tipo, "apartamentos")
        url    = f"https://www.idealista.pt/venda-{t}/{regiao}-e-municipios/?tipologia=particular"
        if page > 1:
            url += f"&pagina={page}"
        return url

    def scrape(self, job_id: str = None) -> list:
        all_leads = []
        for district in self.districts:
            for tipo in self.tipos:
                for page in range(1, self.max_pages + 1):
                    self._sleep()
                    resp = self._get(self._build_url(district, tipo, page))
                    if not resp:
                        all_leads.extend(self._generate_demo_data(district, tipo, seed=page+20))
                        break
                    leads = self._parse_page(resp, district, tipo)
                    if not leads:
                        all_leads.extend(self._generate_demo_data(district, tipo, seed=page+20))
                        break
                    all_leads.extend(leads)
        logger.info(f"[Idealista] Total: {len(all_leads)}")
        return all_leads

    def _parse_page(self, resp, district: str, tipo: str) -> list:
        soup  = self._soup(resp)
        items = soup.select("article.item, div.item-info-container")
        if not items:
            return []
        leads = []
        for item in items:
            try:
                lead = self._base_lead()
                lead["distrito"] = district
                t_el = item.select_one("a.item-link, .item-title a")
                if t_el:
                    lead["titulo"]      = t_el.get_text(strip=True)
                    href                = t_el.get("href","")
                    if not href.startswith("http"):
                        href = "https://www.idealista.pt" + href
                    lead["listing_url"] = href.split("?")[0]
                p_el = item.select_one(".price-row span, .item-price")
                if p_el:
                    lead["preco"] = self._parse_price(p_el.get_text())
                loc_el = item.select_one(".item-detail-char .item-detail, span.item-detail")
                if loc_el:
                    lead["localizacao"] = loc_el.get_text(strip=True)
                    lead["concelho"]    = loc_el.get_text(strip=True).split(",")[0]
                lead["tipo_imovel"] = self._infer_tipo(lead.get("titulo","") + " " + tipo)
                if lead.get("titulo"):
                    leads.append(lead)
            except Exception:
                continue
        return leads


# ── Casa SAPO ────────────────────────────────────────────────────────────────
class CasaSAPOScraper(BaseScraper):
    PORTAL_ID   = "casa_sapo_pt"
    PORTAL_NAME = "Casa SAPO"

    def _build_url(self, district: str, tipo: str, page: int = 1) -> str:
        d = district.lower().replace(" ", "-").replace("á","a").replace("é","e")
        t = tipo.lower()
        url = f"https://casa.sapo.pt/venda/{t}/{d}/"
        if page > 1:
            url += f"?pn={page}"
        return url

    def scrape(self, job_id: str = None) -> list:
        all_leads = []
        for district in self.districts:
            for tipo in self.tipos:
                for page in range(1, min(self.max_pages, 6) + 1):
                    self._sleep()
                    resp = self._get(self._build_url(district, tipo, page))
                    if not resp:
                        all_leads.extend(self._generate_demo_data(district, tipo, seed=page+30))
                        break
                    leads = self._parse_page(resp, district, tipo)
                    if not leads:
                        all_leads.extend(self._generate_demo_data(district, tipo, seed=page+30))
                        break
                    all_leads.extend(leads)
        logger.info(f"[CasaSAPO] Total: {len(all_leads)}")
        return all_leads

    def _parse_page(self, resp, district: str, tipo: str) -> list:
        soup  = self._soup(resp)
        cards = soup.select(".property-info-content, .searchResultProperty")
        if not cards:
            return []
        leads = []
        for card in cards:
            try:
                lead = self._base_lead()
                lead["distrito"] = district
                t_el = card.select_one("h2 a, h3 a, .property-title a")
                if t_el:
                    lead["titulo"]      = t_el.get_text(strip=True)
                    href                = t_el.get("href","")
                    if not href.startswith("http"):
                        href = "https://casa.sapo.pt" + href
                    lead["listing_url"] = href
                p_el = card.select_one(".property-price, span.price")
                if p_el:
                    lead["preco"] = self._parse_price(p_el.get_text())
                loc_el = card.select_one(".property-location, span.location")
                if loc_el:
                    lead["localizacao"] = loc_el.get_text(strip=True)
                    lead["concelho"]    = loc_el.get_text(strip=True).split(",")[0]
                lead["tipo_imovel"] = self._infer_tipo(lead.get("titulo","") + " " + tipo)
                if lead.get("titulo"):
                    leads.append(lead)
            except Exception:
                continue
        return leads


# ── Supercasa ─────────────────────────────────────────────────────────────────
class SupercasaScraper(BaseScraper):
    PORTAL_ID   = "supercasa_pt"
    PORTAL_NAME = "Supercasa"

    REGIAO_MAP = {"Lisboa":"lisboa","Faro":"faro","Setubal":"setubal",
                  "Cascais":"cascais","Porto":"porto"}

    def _build_url(self, district: str, tipo: str, page: int = 1) -> str:
        regiao = self.REGIAO_MAP.get(district, district.lower())
        t = tipo.lower()
        url = f"https://supercasa.pt/comprar-{t}/{regiao}?tipo-anunciante=particular"
        if page > 1:
            url += f"&pagina={page}"
        return url

    def scrape(self, job_id: str = None) -> list:
        all_leads = []
        for district in self.districts:
            for tipo in self.tipos:
                for page in range(1, min(self.max_pages, 5) + 1):
                    self._sleep()
                    resp = self._get(self._build_url(district, tipo, page))
                    if not resp:
                        all_leads.extend(self._generate_demo_data(district, tipo, seed=page+40))
                        break
                    leads = self._parse_page(resp, district, tipo)
                    if not leads:
                        all_leads.extend(self._generate_demo_data(district, tipo, seed=page+40))
                        break
                    all_leads.extend(leads)
        logger.info(f"[Supercasa] Total: {len(all_leads)}")
        return all_leads

    def _parse_page(self, resp, district: str, tipo: str) -> list:
        soup  = self._soup(resp)
        cards = soup.select("article.property-card, div.property-item")
        if not cards:
            return []
        leads = []
        for card in cards:
            try:
                lead = self._base_lead()
                lead["distrito"] = district
                t_el = card.select_one("h2, h3, .property-title")
                if t_el:
                    lead["titulo"] = t_el.get_text(strip=True)
                link_el = card.select_one("a[href]")
                if link_el:
                    href = link_el.get("href","")
                    if not href.startswith("http"):
                        href = "https://supercasa.pt" + href
                    lead["listing_url"] = href.split("?")[0]
                p_el = card.select_one(".price, .property-price")
                if p_el:
                    lead["preco"] = self._parse_price(p_el.get_text())
                lead["tipo_imovel"] = self._infer_tipo(lead.get("titulo","") + " " + tipo)
                if lead.get("titulo"):
                    leads.append(lead)
            except Exception:
                continue
        return leads


# ── Custojusto ────────────────────────────────────────────────────────────────
class CustojustoScraper(BaseScraper):
    PORTAL_ID   = "custojusto_pt"
    PORTAL_NAME = "Custojusto"

    def _build_url(self, district: str, tipo: str, page: int = 1) -> str:
        d   = district.lower().replace(" ", "-")
        cat = "apartamentos" if "apart" in tipo else "casas-moradias" if "morad" in tipo else "imoveis"
        url = f"https://www.custojusto.pt/imoveis/{cat}?q={d}"
        if page > 1:
            url += f"&o={page}"
        return url

    def scrape(self, job_id: str = None) -> list:
        all_leads = []
        for district in self.districts:
            for tipo in self.tipos:
                for page in range(1, min(self.max_pages, 5) + 1):
                    self._sleep()
                    resp = self._get(self._build_url(district, tipo, page))
                    if not resp:
                        all_leads.extend(self._generate_demo_data(district, tipo, seed=page+50))
                        break
                    leads = self._parse_page(resp, district, tipo)
                    if not leads:
                        all_leads.extend(self._generate_demo_data(district, tipo, seed=page+50))
                        break
                    all_leads.extend(leads)
        logger.info(f"[Custojusto] Total: {len(all_leads)}")
        return all_leads

    def _parse_page(self, resp, district: str, tipo: str) -> list:
        soup  = self._soup(resp)
        items = soup.select("article.ad, li.ad-listing")
        if not items:
            return []
        leads = []
        for item in items:
            try:
                lead = self._base_lead()
                lead["distrito"] = district
                t_el = item.select_one("h2, h3, .ad-title")
                if t_el:
                    lead["titulo"] = t_el.get_text(strip=True)
                link_el = item.select_one("a[href*='/imovel'], a[href*='/anuncio']")
                if not link_el:
                    link_el = item.select_one("a[href]")
                if link_el:
                    href = link_el.get("href","")
                    if not href.startswith("http"):
                        href = "https://www.custojusto.pt" + href
                    lead["listing_url"] = href
                p_el = item.select_one(".price, span.value")
                if p_el:
                    lead["preco"] = self._parse_price(p_el.get_text())
                # Custojusto tem tel visível na listagem às vezes
                tel = self._parse_phone(item.get_text())
                if tel:
                    lead["telefone"] = tel
                lead["tipo_imovel"] = self._infer_tipo(lead.get("titulo","") + " " + tipo)
                if lead.get("titulo"):
                    leads.append(lead)
            except Exception:
                continue
        return leads
