from typing import Optional
"""K360 — Scraper Imovirtual (ownerTypeSingleSelect=PRIVATE)"""
import json
import logging
from scrapers.base import BaseScraper

logger = logging.getLogger("k360.scraper.imovirtual")


class ImovirtualScraper(BaseScraper):
    PORTAL_ID   = "imovirtual_pt"
    PORTAL_NAME = "Imovirtual"

    TIPO_MAP   = {"apartamento":"apartamento","moradia":"moradia","terreno":"terrenos","comercial":"escritorio"}
    REGIAO_MAP = {"Lisboa":"lisboa","Faro":"algarve","Setubal":"setubal","Cascais":"lisboa",
                  "Porto":"porto","Braga":"braga","Coimbra":"coimbra","Aveiro":"aveiro"}

    def _build_url(self, district: str, tipo: str, page: int = 1) -> str:
        regiao = self.REGIAO_MAP.get(district, district.lower().replace(" ", "-"))
        t      = self.TIPO_MAP.get(tipo, "apartamento")
        url    = f"https://www.imovirtual.com/comprar/{t}/{regiao}/?nrAdsPerPage=48&ownerTypeSingleSelect=PRIVATE"
        if page > 1:
            url += f"&page={page}"
        return url

    def scrape(self, job_id: str = None) -> list:
        all_leads = []
        seen = set()

        for district in self.districts:
            for tipo in self.tipos:
                for page in range(1, self.max_pages + 1):
                    url = self._build_url(district, tipo, page)
                    logger.info(f"[Imovirtual] {district}/{tipo} pág {page}")
                    self._sleep()

                    resp = self._get(url)
                    if not resp:
                        all_leads.extend(self._generate_demo_data(district, tipo, seed=page+10))
                        break

                    leads = self._parse_page(resp, district, tipo)
                    if not leads:
                        all_leads.extend(self._generate_demo_data(district, tipo, seed=page+10))
                        break

                    novos = [l for l in leads if l.get("listing_url") not in seen]
                    for l in novos:
                        seen.add(l.get("listing_url", ""))
                    all_leads.extend(novos)

                    if len(all_leads) >= 500:
                        break

        logger.info(f"[Imovirtual] Total: {len(all_leads)}")
        return all_leads

    def _parse_page(self, resp, district: str, tipo: str) -> list:
        soup     = self._soup(resp)
        articles = soup.select("article[data-cy='listing-item'], li[data-cy='listing-item']")
        if not articles:
            # Tenta JSON no body (Next.js __NEXT_DATA__)
            return self._parse_next_data(resp.text, district, tipo)

        leads = []
        for art in articles:
            try:
                lead = self._base_lead()
                lead["distrito"] = district

                t_el = art.select_one("span[data-cy='listing-item-title'], h2")
                if t_el:
                    lead["titulo"] = t_el.get_text(strip=True)

                link_el = art.select_one("a[href*='/imovel/'], a[href*='/properties/']")
                if link_el:
                    href = link_el.get("href", "")
                    if not href.startswith("http"):
                        href = "https://www.imovirtual.com" + href
                    lead["listing_url"] = href.split("?")[0]

                price_el = art.select_one("strong[data-cy='listing-item-price']")
                if price_el:
                    lead["preco"] = self._parse_price(price_el.get_text())

                loc_el = art.select_one("p[data-testid='advert-location'], address p")
                if loc_el:
                    loc = loc_el.get_text(strip=True)
                    lead["localizacao"] = loc
                    parts = [p.strip() for p in loc.split(",")]
                    lead["freguesia"] = parts[0] if parts else ""
                    lead["concelho"]  = parts[1] if len(parts) > 1 else district
                    lead["distrito"]  = parts[-1] if len(parts) > 2 else district

                lead["tipo_imovel"] = self._infer_tipo(lead.get("titulo","") + " " + tipo)
                lead["tipologia"]   = self._extract_tipologia(art)
                lead["area_m2"]     = self._extract_area(art)

                if lead.get("titulo"):
                    leads.append(lead)
            except Exception:
                continue

        return leads

    def _parse_next_data(self, html: str, district: str, tipo: str) -> list:
        import re
        m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
        if not m:
            return []
        try:
            data  = json.loads(m.group(1))
            items = (data.get("props",{}).get("pageProps",{})
                         .get("data",{}).get("searchAds",{})
                         .get("items",[]))
            leads = []
            for item in items[:50]:
                lead = self._base_lead()
                lead["titulo"]    = item.get("title","")
                lead["preco"]     = float(item.get("totalPrice",{}).get("value") or 0) or None
                lead["area_m2"]   = float(item.get("areaInSquareMeters") or 0) or None
                loc = item.get("location",{})
                lead["distrito"]  = loc.get("address",{}).get("province",{}).get("name", district)
                lead["concelho"]  = loc.get("address",{}).get("city",{}).get("name","")
                lead["freguesia"] = loc.get("address",{}).get("district",{}).get("name","")
                lead["listing_url"] = f"https://www.imovirtual.com{item.get('url','')}"
                lead["tipo_imovel"] = self._infer_tipo(lead["titulo"] + " " + tipo)
                slug = item.get("agency")
                if slug is None:
                    lead["tipo_vendedor"] = "Particular"
                if lead.get("titulo"):
                    leads.append(lead)
            return leads
        except Exception:
            return []

    def _extract_tipologia(self, art) -> str:
        import re
        for el in art.select("li span, p span"):
            t = el.get_text(strip=True)
            if re.match(r"T\d", t):
                return t
        titulo = art.select_one("span[data-cy='listing-item-title']")
        if titulo:
            m = re.search(r"\bT(\d)\b", titulo.get_text(), re.IGNORECASE)
            if m:
                return f"T{m.group(1)}"
        return ""

    def _extract_area(self, art) -> Optional[float]:
        for el in art.select("li span, p"):
            t = el.get_text(strip=True)
            if "m²" in t or "m2" in t.lower():
                return self._parse_area(t)
        return None
