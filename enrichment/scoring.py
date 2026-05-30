"""
K360 — Motor de Scoring de Leads (0 a 100 pontos)
Detecta vendedores motivados automaticamente.
"""
import re
from config import KEYWORDS_URGENCIA
from enrichment.deduplication import normalize_text


# ── Pesos do scoring ─────────────────────────────────────────────────────────
PESOS = {
    "urgencia_keywords":    25,   # Palavras de urgência na descrição/título
    "dias_mercado_90":      25,   # > 90 dias sem vender
    "dias_mercado_60":      18,   # > 60 dias
    "dias_mercado_30":      10,   # > 30 dias
    "preco_reduziu":        15,   # Preço baixou desde 1ª publicação
    "proprietario_direto":  10,   # Filtrado como particular (garantido)
    "telefone_valido":       8,   # Telefone validado
    "email_disponivel":      4,   # Email encontrado
    "descricao_longa":       3,   # Descrição detalhada = proprietário engajado
}


def score_lead(lead: dict) -> tuple[int, dict, str]:
    """
    Calcula pontuação 0-100 para um lead.
    
    Returns:
        (pontuacao: int, detalhe: dict, temperatura: str)
    """
    pontos = 0
    detalhe = {}

    texto = normalize_text(
        f"{lead.get('titulo', '')} {lead.get('descricao', '')}"
    )

    # 1. Palavras-chave de urgência
    encontradas = [kw for kw in KEYWORDS_URGENCIA if kw in texto]
    if encontradas:
        p = PESOS["urgencia_keywords"]
        pontos += p
        detalhe["urgencia"] = {"pontos": p, "palavras": encontradas[:5]}

    # 2. Dias no mercado
    dias = lead.get("dias_no_mercado", 0) or 0
    if dias > 90:
        p = PESOS["dias_mercado_90"]
        pontos += p
        detalhe["dias_mercado"] = {"pontos": p, "dias": dias, "nivel": "crítico"}
    elif dias > 60:
        p = PESOS["dias_mercado_60"]
        pontos += p
        detalhe["dias_mercado"] = {"pontos": p, "dias": dias, "nivel": "alto"}
    elif dias > 30:
        p = PESOS["dias_mercado_30"]
        pontos += p
        detalhe["dias_mercado"] = {"pontos": p, "dias": dias, "nivel": "médio"}

    # 3. Redução de preço
    if lead.get("preco_reduziu"):
        p = PESOS["preco_reduziu"]
        pontos += p
        detalhe["preco_reduziu"] = {"pontos": p}

    # 4. Proprietário direto (este sistema só capta particulares)
    p = PESOS["proprietario_direto"]
    pontos += p
    detalhe["proprietario_direto"] = {"pontos": p}

    # 5. Telefone válido
    tel = lead.get("telefone", "")
    if tel and _is_valid_pt_phone(tel):
        p = PESOS["telefone_valido"]
        pontos += p
        detalhe["telefone_valido"] = {"pontos": p}

    # 6. Email disponível
    if lead.get("email") and "@" in lead.get("email", ""):
        p = PESOS["email_disponivel"]
        pontos += p
        detalhe["email_disponivel"] = {"pontos": p}

    # 7. Descrição longa (proprietário mais engajado)
    desc = lead.get("descricao", "") or ""
    if len(desc) > 200:
        p = PESOS["descricao_longa"]
        pontos += p
        detalhe["descricao_longa"] = {"pontos": p, "chars": len(desc)}

    # Garante 0–100
    pontuacao = min(100, max(0, pontos))

    # Temperatura
    if pontuacao >= 70:
        temperatura = "quente"
    elif pontuacao >= 40:
        temperatura = "morno"
    else:
        temperatura = "frio"

    return pontuacao, detalhe, temperatura


def _is_valid_pt_phone(tel: str) -> bool:
    """Valida formato de telefone português."""
    digits = re.sub(r"\D", "", tel)
    if digits.startswith("351"):
        digits = digits[3:]
    # Telemóvel PT: 9x com 9 dígitos
    # Fixo PT: 2x com 9 dígitos
    return len(digits) == 9 and digits[0] in ("9", "2")


def extract_days_on_market(date_text: str) -> int:
    """
    Tenta extrair dias no mercado a partir do texto de data.
    Ex: "há 45 dias", "45 dias atrás", "publicado há 2 meses"
    """
    if not date_text:
        return 0

    text = normalize_text(date_text)

    # "há X dias"
    m = re.search(r"ha?\s+(\d+)\s+dias?", text)
    if m:
        return int(m.group(1))

    # "há X meses"
    m = re.search(r"ha?\s+(\d+)\s+mes(?:es)?", text)
    if m:
        return int(m.group(1)) * 30

    # "há X semanas"
    m = re.search(r"ha?\s+(\d+)\s+semanas?", text)
    if m:
        return int(m.group(1)) * 7

    # "hoje" / "ontem"
    if "hoje" in text:
        return 0
    if "ontem" in text:
        return 1

    return 0


def enrich_lead(lead: dict) -> dict:
    """
    Enriquece um lead com score, temperatura e palavras de urgência.
    Modifica e devolve o dict.
    """
    # Extrai dias no mercado se não calculado
    if not lead.get("dias_no_mercado") and lead.get("data_publicacao"):
        lead["dias_no_mercado"] = extract_days_on_market(lead["data_publicacao"])

    # Calcula score
    pontuacao, detalhe, temperatura = score_lead(lead)

    lead["pontuacao"]          = pontuacao
    lead["pontuacao_detalhe"]  = detalhe
    lead["temperatura"]        = temperatura

    # Extrai palavras de urgência encontradas
    texto = normalize_text(f"{lead.get('titulo','')} {lead.get('descricao','')}")
    lead["palavras_urgencia"] = [kw for kw in KEYWORDS_URGENCIA if kw in texto][:10]

    return lead
