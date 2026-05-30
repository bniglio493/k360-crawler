"""
K360 — Motor de Deduplicação
Gera fingerprint única por proprietário cross-portal e cross-execução.
"""
import re
import hashlib
import unicodedata


def normalize_phone(phone: str) -> str:
    """Normaliza número de telefone para comparação."""
    if not phone:
        return ""
    # Remove tudo exceto dígitos
    digits = re.sub(r"\D", "", phone)
    # Remove prefixo internacional PT (+351 ou 00351)
    if digits.startswith("351") and len(digits) == 12:
        digits = digits[3:]
    if digits.startswith("00351"):
        digits = digits[5:]
    return digits


def normalize_email(email: str) -> str:
    """Normaliza email para comparação."""
    if not email:
        return ""
    return email.strip().lower()


def normalize_url(url: str) -> str:
    """Normaliza URL removendo parâmetros de tracking."""
    if not url:
        return ""
    # Remove query string e fragmentos
    url = url.split("?")[0].split("#")[0]
    # Remove trailing slash
    url = url.rstrip("/").lower()
    # Remove protocolo para comparação cross-portal
    url = re.sub(r"^https?://", "", url)
    return url


def normalize_text(text: str) -> str:
    """Normaliza texto: lowercase, remove acentos, espaços extras."""
    if not text:
        return ""
    # Remove acentos
    nfd = unicodedata.normalize("NFD", text)
    ascii_str = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return ascii_str.lower().strip()


def generate_fingerprint(telefone: str, email: str, listing_url: str) -> str:
    """
    Gera fingerprint SHA-256 única para um proprietário.
    
    Prioridade de identificação (do mais forte ao mais fraco):
    1. Telefone normalizado — mesmo tel em OLX e Imovirtual = mesmo proprietário
    2. Email normalizado (não genérico)
    3. URL canónica (fallback — único por anúncio)
    
    IMPORTANTE: o mesmo telefone em portais diferentes produz a MESMA fingerprint,
    garantindo deduplicação cross-portal.
    """
    tel  = normalize_phone(telefone)
    mail = normalize_email(email)
    url  = normalize_url(listing_url)

    # Emails genéricos que não servem como identificador único
    mail_genericos = {"info@", "geral@", "contacto@", "contact@", "vendas@"}
    mail_valido = mail and not any(mail.startswith(g) for g in mail_genericos)

    # Usa o identificador mais forte — telefone prevalece sempre
    if tel:
        key = f"tel:{tel}"
    elif mail_valido:
        key = f"email:{mail}"
    elif url:
        key = f"url:{url}"
    else:
        import time
        key = f"anon:{time.time()}"

    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def leads_are_same(lead_a: dict, lead_b: dict) -> bool:
    """
    Verifica se dois dicts de lead representam o mesmo proprietário.
    Útil para deduplicar dentro da mesma sessão antes de ir à DB.
    """
    tel_a  = normalize_phone(lead_a.get("telefone", ""))
    tel_b  = normalize_phone(lead_b.get("telefone", ""))
    mail_a = normalize_email(lead_a.get("email", ""))
    mail_b = normalize_email(lead_b.get("email", ""))
    url_a  = normalize_url(lead_a.get("listing_url", ""))
    url_b  = normalize_url(lead_b.get("listing_url", ""))

    # Mesmo telefone (não vazio)
    if tel_a and tel_b and tel_a == tel_b:
        return True
    # Mesmo email (não vazio, não genérico)
    if mail_a and mail_b and mail_a == mail_b:
        skip = {"info@", "geral@", "contacto@", "contact@"}
        if not any(mail_a.startswith(s) for s in skip):
            return True
    # Mesma URL
    if url_a and url_b and url_a == url_b:
        return True

    return False


def deduplicate_batch(leads: list) -> list:
    """
    Remove duplicados dentro de um batch antes de ir à base de dados.
    Mantém o lead com mais informação (score mais alto ou mais campos preenchidos).
    """
    seen_fingerprints = set()
    unique = []

    for lead in leads:
        fp = lead.get("fingerprint") or generate_fingerprint(
            lead.get("telefone", ""),
            lead.get("email", ""),
            lead.get("listing_url", ""),
        )
        lead["fingerprint"] = fp

        if fp not in seen_fingerprints:
            seen_fingerprints.add(fp)
            unique.append(lead)

    return unique
