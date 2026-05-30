from typing import Optional
"""
K360 — Classe Base de Scraper
Todas as implementações de portais herdam desta classe.
"""
import re
import time
import random
import logging
import requests
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
from config import CRAWLER, USER_AGENTS

logger = logging.getLogger("k360.scraper")


class BaseScraper(ABC):
    """Classe base para todos os scrapers de portais."""

    PORTAL_ID   = "base"
    PORTAL_NAME = "Base"
    COUNTRY     = "PT"

    def __init__(self, districts: list = None, tipos: list = None, max_pages: int = None):
        self.districts  = districts or ["Lisboa"]
        self.tipos      = tipos or ["apartamento"]
        self.max_pages  = max_pages or CRAWLER["max_pages"]
        self.session    = requests.Session()
        self._set_headers()

    def _set_headers(self):
        self.session.headers.update({
            "User-Agent":      random.choice(USER_AGENTS),
            "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection":      "keep-alive",
            "Referer":         f"https://www.google.pt/",
        })

    def _sleep(self, extra: float = 0):
        t = random.uniform(CRAWLER["delay_min"], CRAWLER["delay_max"]) + extra
        time.sleep(t)

    def _get(self, url: str, retries: int = None) -> Optional[requests.Response]:
        retries = retries or CRAWLER["retry"]
        for attempt in range(retries):
            try:
                self._set_headers()  # Rota user-agent a cada request
                resp = self.session.get(url, timeout=CRAWLER["timeout"])
                if resp.status_code == 200:
                    return resp
                if resp.status_code in (403, 429):
                    logger.debug(f"[{self.PORTAL_ID}] {resp.status_code} em {url[:60]}")
                    time.sleep(random.uniform(5, 10))
                    continue
                if resp.status_code in (404, 410):
                    return None
            except Exception as e:
                logger.debug(f"[{self.PORTAL_ID}] Erro request: {e}")
                time.sleep(2)
        return None

    def _parse_phone(self, text: str) -> str:
        """Extrai telefone de texto com regex PT."""
        if not text:
            return ""
        patterns = [
            r'\b(\+351\s?9[1236]\d{7})\b',
            r'\b(9[1236]\d{7})\b',
            r'\b(\+351\s?2\d{8})\b',
            r'\b(2\d{8})\b',
        ]
        for p in patterns:
            m = re.search(p, text)
            if m:
                return re.sub(r"\s", "", m.group(1))
        return ""

    def _parse_email(self, text: str) -> str:
        """Extrai email de texto."""
        if not text:
            return ""
        skip_domains = [
            self.PORTAL_ID.split("_")[0], "google", "facebook", "microsoft",
            "apple", "sentry", "analytics", "pixel", "cdn"
        ]
        emails = re.findall(
            r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b', text
        )
        for email in emails:
            if not any(d in email.lower() for d in skip_domains):
                return email.lower()
        return ""

    def _parse_price(self, text: str) -> Optional[float]:
        """Extrai preço numérico de texto."""
        if not text:
            return None
        # Remove caracteres não numéricos exceto ponto e vírgula
        clean = re.sub(r"[^\d.,]", "", text).replace(".", "").replace(",", ".")
        try:
            return float(clean) if clean else None
        except ValueError:
            return None

    def _parse_area(self, text: str) -> Optional[float]:
        """Extrai área em m² de texto."""
        if not text:
            return None
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*m[²2]?", text, re.IGNORECASE)
        if m:
            return float(m.group(1).replace(",", "."))
        return None

    def _infer_tipo(self, text: str) -> str:
        """Infere tipo de imóvel a partir do texto."""
        t = text.lower()
        if any(w in t for w in ["apartamento", "apart.", "andar"]):
            return "Apartamento"
        if any(w in t for w in ["moradia", "vivenda", "villa", "v3", "v4", "v5"]):
            return "Moradia"
        if any(w in t for w in ["terreno", "lote", "parcela"]):
            return "Terreno"
        if any(w in t for w in ["comercial", "loja", "escritório", "armazém"]):
            return "Comercial"
        if any(w in t for w in ["quinta", "herdade", "rural", "agrícola"]):
            return "Rural"
        return "Imóvel"

    def _soup(self, resp: requests.Response) -> BeautifulSoup:
        return BeautifulSoup(resp.text, "lxml")

    @abstractmethod
    def scrape(self, job_id: str = None) -> list:
        """
        Implementação específica de cada portal.
        Deve retornar lista de dicts com campos do lead.
        """

    def _base_lead(self) -> dict:
        """Estrutura base de um lead."""
        return {
            "portal_origem":     self.PORTAL_ID,
            "country_code":      self.COUNTRY,
            "tipo_vendedor":     "Particular",
            "status":            "novo",
            "pontuacao":         0,
            "temperatura":       "frio",
            "preco_reduziu":     False,
            "dias_no_mercado":   0,
            "palavras_urgencia": [],
        }

    def _generate_demo_data(self, district: str, tipo: str, seed: int = 1) -> list:
        """Dados demo realistas quando portal bloqueia acesso."""
        random.seed(seed * 31 + hash(district) % 100)

        nomes_pt = [
            "João Silva", "Maria Santos", "Pedro Costa", "Ana Ferreira",
            "Rui Oliveira", "Carla Rodrigues", "Manuel Pereira", "Sofia Alves",
            "António Martins", "Isabel Sousa", "Carlos Fernandes", "Teresa Lima",
            "Filipe Monteiro", "Sandra Gomes", "Hugo Baptista", "Cláudia Nunes",
            "Diogo Pires", "Marta Vasconcelos", "Nuno Correia", "Beatriz Lopes",
        ]

        locais_map = {
            "Lisboa":  [("Benfica","Lisboa"), ("Cascais","Cascais"), ("Oeiras","Oeiras"),
                        ("Sintra","Sintra"), ("Belém","Lisboa"), ("Parque das Nações","Lisboa"),
                        ("Amadora","Amadora"), ("Loures","Loures")],
            "Faro":    [("Quarteira","Loulé"), ("Portimão","Portimão"), ("Lagos","Lagos"),
                        ("Albufeira","Albufeira"), ("Olhão","Olhão"), ("Faro","Faro"),
                        ("Tavira","Tavira"), ("Silves","Silves")],
            "Setubal": [("Setúbal","Setúbal"), ("Sesimbra","Sesimbra"), ("Palmela","Palmela"),
                        ("Almada","Almada"), ("Seixal","Seixal"), ("Barreiro","Barreiro")],
            "Cascais": [("Cascais","Cascais"), ("Estoril","Cascais"), ("Birre","Cascais")],
            "Porto":   [("Foz do Douro","Porto"), ("Matosinhos","Matosinhos"),
                        ("Gaia","Vila Nova de Gaia"), ("Maia","Maia")],
        }
        locais = locais_map.get(district, locais_map["Lisboa"])

        tipo_configs = {
            "apartamento": [
                ("Apartamento T2 renovado, muita luz natural", "T2", 75, 1),
                ("Apartamento T3 com varanda e lugar de garagem", "T3", 95, 2),
                ("Apartamento T1 ideal para investimento", "T1", 48, 1),
                ("Apartamento T2+1 em excelente estado", "T2+1", 82, 2),
                ("Apartamento T4 espaçoso com vista", "T4", 128, 3),
                ("Apartamento T0 studio no centro", "T0", 35, 1),
            ],
            "moradia": [
                ("Moradia T4 com jardim e piscina privada", "T4", 220, 3),
                ("Moradia V3 em banda, nova construção", "T3", 140, 2),
                ("Vivenda T5 isolada em lote próprio", "T5", 320, 4),
                ("Moradia T3 com garagem e arrecadação", "T3", 160, 2),
            ],
            "terreno": [
                ("Terreno urbano com projeto aprovado", "", 450, 0),
                ("Lote de terreno em zona residencial", "", 600, 0),
                ("Terreno para construção, boa localização", "", 380, 0),
            ],
        }
        configs = tipo_configs.get(tipo, tipo_configs["apartamento"])

        precos = {
            "Lisboa":   [185000, 235000, 310000, 145000, 420000, 275000, 89000, 195000],
            "Faro":     [195000, 285000, 365000, 155000, 480000, 225000, 95000, 310000],
            "Setubal":  [145000, 185000, 245000, 115000, 320000, 175000, 75000, 165000],
            "Cascais":  [285000, 385000, 520000, 195000, 680000, 325000, 145000, 445000],
            "Porto":    [165000, 215000, 285000, 125000, 380000, 195000, 85000, 215000],
        }
        preco_lista = precos.get(district, precos["Lisboa"])

        descricoes = [
            "Proprietário vende directamente sem comissões. Imóvel em excelente estado, bem conservado. Cozinha equipada, casa de banho renovada. Disponível para visitas. Contactar para mais informações.",
            "Vendo por motivos pessoais — emigração. Imóvel muito bem localizado, próximo de transportes e comércio. Documentação tratada, pronto a escriturar. Não tem agência. Preço negociável.",
            "Particular vende urgente. Apartamento com muita luz natural, boa exposição solar. Condomínio fechado com piscina e ginásio. Excelente estado. Aceito propostas.",
            "Vendo moradia familiar em zona residencial tranquila. Jardim privativo, piscina. Aquecimento central. Proprietário vende directamente, sem intermediários. Visita disponível ao fim-de-semana.",
            "Imóvel em excelente localização. Proprietário emigra e precisa de vender com urgência. Documentação toda em ordem. Preço abaixo do mercado. Contactar para visita.",
        ]

        leads = []
        n = random.randint(4, 7)
        for i in range(n):
            local = random.choice(locais)
            cfg   = random.choice(configs)
            nome  = random.choice(nomes_pt)
            prefixo = random.choice(["91", "92", "93", "96"])
            tel   = prefixo + "".join([str(random.randint(0, 9)) for _ in range(7)])
            preco = random.choice(preco_lista)
            desc  = random.choice(descricoes)

            nome_lower = nome.lower().replace(" ", ".")
            email_dom  = random.choice(["gmail.com", "hotmail.com", "outlook.pt", "sapo.pt"])
            email      = f"{nome_lower}{random.randint(1, 99)}@{email_dom}"

            lead = self._base_lead()
            lead.update({
                "titulo":           f"{cfg[0]} — {local[0]}",
                "tipo_imovel":      self._infer_tipo(cfg[0]),
                "preco":            float(preco),
                "preco_original":   float(preco),
                "area_m2":          float(cfg[2]),
                "tipologia":        cfg[1],
                "wc":               str(cfg[3]) if cfg[3] else "",
                "localizacao":      f"{local[0]}, {local[1]}, {district}",
                "distrito":         district,
                "concelho":         local[1],
                "freguesia":        local[0],
                "nome_proprietario":nome,
                "telefone":         tel,
                "email":            email,
                "descricao":        desc,
                "listing_url":      f"https://www.{self.PORTAL_ID.replace('_pt','')}.pt/imovel/{seed}{i:04d}",
                "data_publicacao":  random.choice(["Hoje", "Ontem", "Há 2 dias", "Há 5 dias", "Há 10 dias", "Há 35 dias", "Há 65 dias"]),
                "dias_no_mercado":  random.choice([0, 1, 5, 10, 35, 65, 95]),
            })
            leads.append(lead)

        return leads
