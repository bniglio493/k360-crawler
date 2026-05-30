from typing import Optional
"""
K360 — Motor de Distribuição de Leads
Modo activo: por_localização
Lógica: match lead.concelho/freguesia → perfis.zona_atuacao
Load balancing: consultor com menos leads activas recebe primeiro.
"""
import logging
from enrichment.deduplication import normalize_text

logger = logging.getLogger("k360.distribuicao")


def match_agent_by_location(lead: dict, agents: list, lead_counts: dict) -> Optional[str]:
    """
    Encontra o consultor ideal para um lead baseado em zona de actuação.
    
    Args:
        lead:        dict com 'concelho', 'freguesia', 'distrito'
        agents:      lista de dicts com 'id', 'nome', 'zona_atuacao'
        lead_counts: {agent_id: nr_leads_activas} para load balancing
    
    Returns:
        agent_id (str) ou None se nenhum match
    """
    # Texto de localização do lead para comparar
    lead_location = normalize_text(
        f"{lead.get('concelho', '')} {lead.get('freguesia', '')} {lead.get('distrito', '')}"
    )

    if not lead_location.strip():
        logger.debug("Lead sem localização — vai para pool")
        return None

    matching_agents = []

    for agent in agents:
        zona_raw = agent.get("zona_atuacao") or ""
        if not zona_raw:
            continue

        zona = normalize_text(zona_raw)

        # Split por vírgulas, ponto e vírgula, nova linha
        import re
        zonas = [z.strip() for z in re.split(r"[,;\n/]", zona) if z.strip()]

        for zona_part in zonas:
            # Verifica se a zona do consultor está no texto do lead
            # Usa correspondência parcial para cobrir "Lisboa" → "Lisboa Norte"
            if zona_part and (zona_part in lead_location or lead_location.find(zona_part) != -1):
                matching_agents.append(agent)
                break

        # Segunda passagem: verifica se alguma palavra do lead está na zona
        if agent not in matching_agents:
            lead_words = [w for w in lead_location.split() if len(w) > 3]
            for word in lead_words:
                if word in zona:
                    matching_agents.append(agent)
                    break

    if not matching_agents:
        logger.debug(f"Nenhum consultor para '{lead.get('concelho')}' — pool")
        return None

    # Load balancing: escolhe o consultor com MENOS leads activas
    def agent_load(agent):
        return lead_counts.get(agent["id"], 0)

    best_agent = min(matching_agents, key=agent_load)

    logger.info(
        f"Lead '{lead.get('concelho')}' → {best_agent.get('nome')} "
        f"(carga: {agent_load(best_agent)} leads)"
    )
    return best_agent["id"]


def distribute_leads(leads: list, mode: str = "por_localizacao") -> dict:
    """
    Distribui um batch de leads pelos consultores.
    
    Returns:
        {
            "distribuidos": [(lead_id, agent_id), ...],
            "pool":         [lead_id, ...],  # sem match
        }
    """
    from database import get_active_agents, get_agent_lead_counts, assign_lead

    if not leads:
        return {"distribuidos": [], "pool": []}

    agents      = get_active_agents()
    lead_counts = get_agent_lead_counts()

    if not agents:
        logger.warning("Sem consultores activos — todas as leads vão para pool")
        return {
            "distribuidos": [],
            "pool": [l["id"] for l in leads if l.get("id")],
        }

    distribuidos = []
    pool         = []

    for lead in leads:
        lead_id = lead.get("id")
        if not lead_id:
            continue

        if mode == "por_localizacao":
            agent_id = match_agent_by_location(lead, agents, lead_counts)
        elif mode == "rodada":
            agent_id = _round_robin(agents, lead_counts)
        else:
            agent_id = None  # Manual: admin distribui

        if agent_id:
            assign_lead(lead_id, agent_id)
            # Actualiza contagem local para o próximo lead desta sessão
            lead_counts[agent_id] = lead_counts.get(agent_id, 0) + 1
            distribuidos.append((lead_id, agent_id))
        else:
            pool.append(lead_id)

    logger.info(
        f"Distribuição concluída: {len(distribuidos)} atribuídos, "
        f"{len(pool)} no pool"
    )

    return {"distribuidos": distribuidos, "pool": pool}


def _round_robin(agents: list, lead_counts: dict) -> Optional[str]:
    """Distribui em rodada — consultor com menos leads vai primeiro."""
    if not agents:
        return None
    return min(agents, key=lambda a: lead_counts.get(a["id"], 0))["id"]
