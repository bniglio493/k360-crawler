-- ============================================================
-- K360 CRAWLER — Migration SQL
-- Projeto Supabase: sahmtglrposdarcusgrq
-- Colar e executar no Supabase SQL Editor
-- ============================================================

-- 1. PORTAIS CONFIGURADOS (multi-país)
CREATE TABLE IF NOT EXISTS k360_portal_configs (
    id            uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    portal_id     text UNIQUE NOT NULL,
    country_code  text NOT NULL DEFAULT 'PT',
    portal_name   text NOT NULL,
    base_url      text NOT NULL,
    search_url    text,
    private_param text DEFAULT '',
    enabled       boolean DEFAULT true,
    criado_em     timestamptz DEFAULT now()
);

-- 2. CONFIGURAÇÃO DE SCRAPING (admin edita aqui)
CREATE TABLE IF NOT EXISTS k360_scrape_config (
    id               uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    country_code     text NOT NULL DEFAULT 'PT',
    districts        text[] NOT NULL DEFAULT '{"Lisboa","Faro","Setubal"}',
    portals_enabled  text[] NOT NULL DEFAULT '{"olx_pt","imovirtual_pt","idealista_pt"}',
    property_types   text[] NOT NULL DEFAULT '{"apartamento","moradia"}',
    cron_schedule    text NOT NULL DEFAULT '0 0 * * *',
    max_pages        integer DEFAULT 10,
    only_private     boolean DEFAULT true,
    active           boolean DEFAULT true,
    criado_em        timestamptz DEFAULT now(),
    atualizado_em    timestamptz DEFAULT now()
);

-- 3. LEADS — tabela principal
CREATE TABLE IF NOT EXISTS k360_leads (
    id                   uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    fingerprint          text UNIQUE NOT NULL,

    -- Status & atribuição
    status               text NOT NULL DEFAULT 'novo'
                         CHECK (status IN ('novo','atribuido','em_contacto','negociacao','angariado','perdido','bloqueado')),
    atribuido_a          uuid REFERENCES perfis(id) ON DELETE SET NULL,
    atribuido_em         timestamptz,

    -- Score
    pontuacao            integer DEFAULT 0 CHECK (pontuacao BETWEEN 0 AND 100),
    pontuacao_detalhe    jsonb DEFAULT '{}',
    temperatura          text DEFAULT 'frio'
                         CHECK (temperatura IN ('quente','morno','frio')),

    -- Origem
    portal_origem        text NOT NULL,
    country_code         text NOT NULL DEFAULT 'PT',
    listing_url          text,

    -- Proprietário
    nome_proprietario    text,
    telefone             text,
    telefone_valido      boolean DEFAULT false,
    email                text,
    tipo_vendedor        text DEFAULT 'Particular',

    -- Imóvel
    titulo               text,
    tipo_imovel          text,
    preco                numeric,
    preco_original       numeric,
    area_m2              numeric,
    tipologia            text,
    wc                   text,
    descricao            text,

    -- Localização
    localizacao          text,
    distrito             text,
    concelho             text,
    freguesia            text,
    latitude             numeric,
    longitude            numeric,

    -- Sinais de mercado
    dias_no_mercado      integer DEFAULT 0,
    preco_reduziu        boolean DEFAULT false,
    palavras_urgencia    text[] DEFAULT '{}',
    data_publicacao      text,

    -- Timestamps
    criado_em            timestamptz DEFAULT now(),
    atualizado_em        timestamptz DEFAULT now(),
    last_seen_em         timestamptz DEFAULT now()
);

-- 4. HISTÓRICO DE PREÇOS
CREATE TABLE IF NOT EXISTS k360_price_history (
    id           uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    lead_id      uuid NOT NULL REFERENCES k360_leads(id) ON DELETE CASCADE,
    preco        numeric NOT NULL,
    delta_pct    numeric,
    detected_at  timestamptz DEFAULT now()
);

-- 5. ACTIVIDADES / LOG CRM
CREATE TABLE IF NOT EXISTS k360_lead_activities (
    id         uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    lead_id    uuid NOT NULL REFERENCES k360_leads(id) ON DELETE CASCADE,
    agent_id   uuid REFERENCES perfis(id) ON DELETE SET NULL,
    action     text NOT NULL,
    notas      text,
    criado_em  timestamptz DEFAULT now()
);

-- 6. LOG DE JOBS DE SCRAPING
CREATE TABLE IF NOT EXISTS k360_scrape_jobs (
    id                  uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    iniciado_em         timestamptz DEFAULT now(),
    terminado_em        timestamptz,
    country_code        text DEFAULT 'PT',
    districts           text[],
    portals             text[],
    total_encontrados   integer DEFAULT 0,
    total_novos         integer DEFAULT 0,
    total_duplicados    integer DEFAULT 0,
    total_distribuidos  integer DEFAULT 0,
    status              text DEFAULT 'running'
                        CHECK (status IN ('running','completed','failed')),
    error_log           text,
    config_snapshot     jsonb
);

-- ÍNDICES
CREATE INDEX IF NOT EXISTS idx_k360_leads_status       ON k360_leads(status);
CREATE INDEX IF NOT EXISTS idx_k360_leads_atribuido_a  ON k360_leads(atribuido_a);
CREATE INDEX IF NOT EXISTS idx_k360_leads_distrito     ON k360_leads(distrito);
CREATE INDEX IF NOT EXISTS idx_k360_leads_pontuacao    ON k360_leads(pontuacao DESC);
CREATE INDEX IF NOT EXISTS idx_k360_leads_criado_em    ON k360_leads(criado_em DESC);
CREATE INDEX IF NOT EXISTS idx_k360_leads_temperatura  ON k360_leads(temperatura);
CREATE INDEX IF NOT EXISTS idx_k360_leads_concelho     ON k360_leads(concelho);
CREATE INDEX IF NOT EXISTS idx_k360_leads_fingerprint  ON k360_leads(fingerprint);

-- TRIGGER: atualiza atualizado_em automaticamente
CREATE OR REPLACE FUNCTION k360_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_k360_leads_updated ON k360_leads;
CREATE TRIGGER trg_k360_leads_updated
    BEFORE UPDATE ON k360_leads
    FOR EACH ROW EXECUTE FUNCTION k360_update_timestamp();

-- ROW LEVEL SECURITY
ALTER TABLE k360_leads            ENABLE ROW LEVEL SECURITY;
ALTER TABLE k360_lead_activities  ENABLE ROW LEVEL SECURITY;
ALTER TABLE k360_price_history    ENABLE ROW LEVEL SECURITY;
ALTER TABLE k360_scrape_jobs      ENABLE ROW LEVEL SECURITY;
ALTER TABLE k360_scrape_config    ENABLE ROW LEVEL SECURITY;
ALTER TABLE k360_portal_configs   ENABLE ROW LEVEL SECURITY;

-- Consultor vê apenas as suas leads atribuídas
CREATE POLICY "consultor_ver_proprias_leads"
    ON k360_leads FOR SELECT
    USING (atribuido_a = auth.uid());

-- Consultor pode actualizar status/notas das suas leads
CREATE POLICY "consultor_atualizar_proprias_leads"
    ON k360_leads FOR UPDATE
    USING (atribuido_a = auth.uid())
    WITH CHECK (atribuido_a = auth.uid());

-- Actividades: consultor vê as suas
CREATE POLICY "consultor_ver_proprias_atividades"
    ON k360_lead_activities FOR ALL
    USING (agent_id = auth.uid());

-- Histórico de preços: consultor vê das suas leads
CREATE POLICY "consultor_ver_price_history"
    ON k360_price_history FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM k360_leads
            WHERE id = lead_id AND atribuido_a = auth.uid()
        )
    );

-- NOTA: O backend usa service_role key → bypass total do RLS
-- O admin no Lovable deve usar service_role ou ter role='admin' em perfis

-- REALTIME: activa para o Lovable receber updates sem polling
ALTER PUBLICATION supabase_realtime ADD TABLE k360_leads;
ALTER PUBLICATION supabase_realtime ADD TABLE k360_scrape_jobs;

-- DADOS INICIAIS: portais
INSERT INTO k360_portal_configs
    (portal_id, country_code, portal_name, base_url, search_url, private_param, enabled)
VALUES
    ('olx_pt',        'PT', 'OLX Portugal',       'https://www.olx.pt',            'https://www.olx.pt/imoveis/',                    'owner=private',                     true),
    ('imovirtual_pt', 'PT', 'Imovirtual',          'https://www.imovirtual.com',     'https://www.imovirtual.com/venda/apartamento/',  'ownerTypeSingleSelect=PRIVATE',     true),
    ('idealista_pt',  'PT', 'Idealista Portugal',  'https://www.idealista.pt',       'https://www.idealista.pt/venda-habitacoes/',     'tipologia=particular',              true),
    ('casa_sapo_pt',  'PT', 'Casa SAPO',           'https://casa.sapo.pt',           'https://casa.sapo.pt/venda/',                    '',                                  true),
    ('supercasa_pt',  'PT', 'Supercasa',           'https://supercasa.pt',           'https://supercasa.pt/comprar/',                  'tipo-anunciante=particular',        true),
    ('custojusto_pt', 'PT', 'Custojusto',          'https://www.custojusto.pt',      'https://www.custojusto.pt/imoveis/',             '',                                  true),
    ('idealista_es',  'ES', 'Idealista España',    'https://www.idealista.com',      'https://www.idealista.com/venta-viviendas/',     'tipologia=particular',              false),
    ('fotocasa_es',   'ES', 'Fotocasa',            'https://www.fotocasa.es',        'https://www.fotocasa.es/es/comprar/viviendas/',  '',                                  false),
    ('leboncoin_fr',  'FR', 'Leboncoin',           'https://www.leboncoin.fr',       'https://www.leboncoin.fr/recherche?category=9', 'owner_type=private',                false),
    ('rightmove_uk',  'UK', 'Rightmove',           'https://www.rightmove.co.uk',    'https://www.rightmove.co.uk/property-for-sale/','',                                  false)
ON CONFLICT (portal_id) DO NOTHING;

-- Configuração inicial: Algarve, Lisboa, Cascais, Setúbal — cron 00:00
INSERT INTO k360_scrape_config
    (country_code, districts, portals_enabled, property_types, cron_schedule, max_pages, active)
VALUES (
    'PT',
    '{"Lisboa","Faro","Setubal","Cascais","Almada","Seixal","Barreiro","Moita"}',
    '{"olx_pt","imovirtual_pt","idealista_pt","casa_sapo_pt","supercasa_pt","custojusto_pt"}',
    '{"apartamento","moradia","terreno"}',
    '0 0 * * *',
    10,
    true
)
ON CONFLICT DO NOTHING;
