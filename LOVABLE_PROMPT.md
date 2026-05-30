# K360 LEADS — Dashboard de Angariação Automática
## Prompt para Lovable (colar na íntegra)

---

Cria um dashboard profissional chamado **K360 Leads** para uma imobiliária portuguesa gerir automaticamente leads de proprietários que querem vender os seus imóveis. O sistema já tem uma tabela `perfis` com os consultores. Precisamos de construir o painel de administração e o painel dos consultores.

---

## BASE DE DADOS SUPABASE (tabelas já existentes + novas)

### Tabela existente — `perfis`
Contém os consultores/agentes. Campos relevantes:
- `id` (uuid) — chave primária, ligada a auth.users
- `nome` (text)
- `email` (text)
- `telefone` (text)
- `avatar_url` (text)
- `titulo_profissional` (text)
- `agencia` (text)
- `zona_atuacao` (text) — zona geográfica do consultor (ex: "Lisboa, Cascais, Sintra")
- `licenca_ami` (text)

### Nova tabela — `k360_leads`
A tabela principal com os leads captados automaticamente. Campos:
- `id` (uuid) — PK
- `fingerprint` (text unique) — hash anti-duplicação
- `status` (text) — valores: 'novo', 'atribuido', 'em_contacto', 'negociacao', 'angariado', 'perdido', 'bloqueado'
- `atribuido_a` (uuid) — FK para perfis.id (pode ser null = lead no pool)
- `atribuido_em` (timestamptz)
- `pontuacao` (integer 0-100) — score de motivação do vendedor
- `pontuacao_detalhe` (jsonb) — breakdown do score
- `temperatura` (text) — 'quente', 'morno', 'frio'
- `portal_origem` (text) — ex: 'olx_pt', 'imovirtual_pt', 'idealista_pt'
- `country_code` (text) — ex: 'PT'
- `listing_url` (text) — link original do anúncio
- `nome_proprietario` (text)
- `telefone` (text)
- `telefone_valido` (boolean)
- `email` (text)
- `tipo_vendedor` (text) — sempre 'Particular'
- `titulo` (text) — título do anúncio
- `tipo_imovel` (text) — 'Apartamento', 'Moradia', 'Terreno', etc.
- `preco` (numeric)
- `preco_original` (numeric)
- `area_m2` (numeric)
- `tipologia` (text) — ex: 'T2', 'T3', 'V4'
- `descricao` (text)
- `localizacao` (text)
- `distrito` (text)
- `concelho` (text)
- `freguesia` (text)
- `dias_no_mercado` (integer)
- `preco_reduziu` (boolean) — true se o preço baixou
- `palavras_urgencia` (text[]) — array de palavras detectadas
- `criado_em` (timestamptz)
- `atualizado_em` (timestamptz)
- `last_seen_em` (timestamptz)

### Nova tabela — `k360_lead_activities`
Log de todas as acções sobre cada lead:
- `id` (uuid) PK
- `lead_id` (uuid) FK k360_leads.id
- `agent_id` (uuid) FK perfis.id
- `action` (text) — ex: 'atribuido_automatico', 'status_angariado', 'nota_adicionada'
- `notas` (text)
- `criado_em` (timestamptz)

### Nova tabela — `k360_price_history`
Histórico de preços de cada lead:
- `id` (uuid) PK
- `lead_id` (uuid) FK k360_leads.id
- `preco` (numeric)
- `delta_pct` (numeric) — variação percentual
- `detected_at` (timestamptz)

### Nova tabela — `k360_scrape_jobs`
Log dos jobs de scraping automático:
- `id` (uuid) PK
- `iniciado_em` (timestamptz)
- `terminado_em` (timestamptz)
- `country_code` (text)
- `districts` (text[])
- `portals` (text[])
- `total_encontrados` (integer)
- `total_novos` (integer)
- `total_duplicados` (integer)
- `total_distribuidos` (integer)
- `status` (text) — 'running', 'completed', 'failed'
- `error_log` (text)

### Nova tabela — `k360_scrape_config`
Configuração do crawler (admin edita aqui):
- `id` (uuid) PK
- `country_code` (text) — ex: 'PT'
- `districts` (text[]) — ex: ['Lisboa','Faro','Setubal']
- `portals_enabled` (text[])
- `property_types` (text[])
- `cron_schedule` (text) — ex: '0 0 * * *'
- `max_pages` (integer)
- `active` (boolean)

### Nova tabela — `k360_portal_configs`
Portais disponíveis por país:
- `portal_id` (text) PK
- `country_code` (text)
- `portal_name` (text)
- `enabled` (boolean)

---

## AUTENTICAÇÃO E ROLES

Usa o Supabase Auth já existente. Quando o utilizador faz login:
- Se o seu `perfis.id` tem acesso admin (verificar se existe uma coluna `role = 'admin'` na tabela perfis, ou se não existir usar o primeiro utilizador como admin) → mostrar painel de Admin
- Caso contrário → mostrar painel de Consultor

---

## DESIGN E ESTILO

Design profissional e moderno para imobiliária portuguesa. Usa:
- Cores: fundo branco/cinza muito claro, primária azul escuro (#1e3a5f ou similar), acentos laranja (#e87722) para destaques e CTAs
- Tipografia limpa e legível, sans-serif
- Cards com bordas sutis, sombras leves
- Badges coloridos para temperatura: vermelho para 'quente', amarelo para 'morno', cinza para 'frio'
- Badges coloridos para status: azul='novo', laranja='atribuido', roxo='em_contacto', verde='angariado', vermelho='perdido'
- Sidebar de navegação à esquerda, conteúdo principal à direita
- Totalmente responsivo
- Header com logo "K360 Leads", nome do utilizador logado e avatar

---

## PAINEL ADMIN — Páginas e Funcionalidades

### 1. Dashboard / Overview (página inicial do admin)

Mostra em tempo real (Supabase Realtime):

**Linha de métricas no topo (cards grandes):**
- Total de Leads na DB (número grande)
- Captadas Hoje (com badge verde "NOVO" pulsante se > 0)
- No Pool (sem consultor atribuído) — badge laranja se > 0
- Leads Quentes (pontuacao >= 70) — badge vermelho
- Angariações Este Mês (status = 'angariado')

**Secção "Captados Hoje" com feed em tempo real:**
- Lista das últimas leads inseridas hoje, ordenadas por pontuação descendente
- Cada item mostra: badge temperatura (🔴🟡🔵), nome proprietário, telefone, localização (concelho, distrito), pontuação (barra visual), portal de origem, tipologia + preço, botão "Atribuir"
- Se a lista estiver vazia mostrar estado vazio animado: "A aguardar a próxima busca automática às 00:00"

**Gráfico de leads por distrito (barras horizontais simples):**
- Top 6 distritos com mais leads, usando os dados de k360_leads agrupados por distrito

**Última busca automática:**
- Card mostrando o último k360_scrape_jobs completado: data/hora de início, total encontrados, novos, distribuídos, status com ícone

**Próxima busca agendada:**
- Card simples: "Próxima busca: hoje às 00:00" com countdown

---

### 2. Pool de Leads (tab ou página separada no admin)

**Header da página:**
- Título "Pool de Leads" + contador "X leads por atribuir"
- Botão "Buscar Agora" (chama POST /api/search na API do crawler — o admin pode configurar a URL da API nas definições)
- Filtros: por Distrito (dropdown), Temperatura (todos/quente/morno/frio), Portal, Tipo de Imóvel, pesquisa por nome/telefone

**Tabela de leads (com paginação):**
Colunas: Temperatura | Pontuação | Nome Proprietário | Telefone | Email | Localização | Tipo + Tipologia | Preço | Portal | Dias no Mercado | Acções

- Temperatura: bolinha colorida 🔴🟡🔵
- Pontuação: barra de progresso colorida (verde>70, amarelo>40, cinza resto) + número
- Telefone: clicável (tel: link) com ícone de cópia
- Email: clicável (mailto: link)
- Preço: formatado em € com separador de milhares
- Dias no mercado: se >60 mostrar em vermelho, se >30 em laranja
- "Redução de preço": ícone 📉 se preco_reduziu = true
- Acções: botão "Atribuir" que abre modal + botão "Ver Detalhes"

**Modal de Atribuição:**
- Lista de consultores activos da tabela `perfis` (mostrar avatar, nome, zona_atuacao, e o número de leads activas que já têm)
- O consultor com a zona correspondente à lead deve aparecer no topo com destaque "✓ Zona compatível"
- Botão confirmar atribuição
- Ao confirmar: update k360_leads (status='atribuido', atribuido_a, atribuido_em) + insert em k360_lead_activities

**Clique em "Ver Detalhes" abre um drawer lateral (slide-in da direita) com:**
- Todos os dados da lead
- Link clicável para o anúncio original (listing_url)
- Histórico de preços (gráfico de linha simples se houver dados em k360_price_history)
- Palavras de urgência detectadas (badges vermelhos)
- Breakdown do score (pontuacao_detalhe em JSON — mostrar cada componente como linha: "Palavras urgentes: +25pts", "65 dias no mercado: +18pts", etc.)
- Timeline de actividades (k360_lead_activities)
- Botão "Atribuir" no footer do drawer

---

### 3. Todas as Leads (visão completa do admin)

Similar ao Pool mas mostra TODAS as leads de todos os estados.

Adicionar coluna "Consultor" mostrando avatar + nome do consultor atribuído (ou "— Pool" se não atribuído).

Filtros adicionais: por Consultor (dropdown com todos os perfis).

Acção adicional: "Reatribuir" para leads já atribuídas (admin pode sempre redistribuir).

---

### 4. Consultores

Lista de todos os consultores da tabela `perfis`.

Para cada consultor mostrar card com:
- Avatar circular + nome + título profissional + agência
- Zona de actuação (zona_atuacao)
- Métricas em tempo real: Total leads atribuídas | Em contacto | Angariadas este mês
- Barra de progresso "Taxa de angariação" = angariadas / total atribuídas
- Botão "Ver Leads deste Consultor" → filtra a tabela Todas as Leads

---

### 5. Configurações do Crawler

Formulário que lê e edita a tabela `k360_scrape_config`:

**Secção "Regiões e Tipos":**
- Multi-select de Distritos (opções: Lisboa, Faro, Setubal, Cascais, Porto, Braga, Coimbra, Aveiro, Leiria, Santarém, Viseu, Évora, Beja, Castelo Branco, Portalegre, Guarda, Viana do Castelo, Vila Real, Bragança, Madeira, Açores)
- Multi-select de Tipos de Imóvel (Apartamento, Moradia, Terreno, Comercial)
- Campo "Páginas por Portal" (número, 1-20)

**Secção "Portais Activos":**
- Lista de portais da tabela `k360_portal_configs` filtrado por country_code
- Toggle on/off para cada portal
- Mostrar portal_name + badge do país

**Secção "Agendamento":**
- Label explicativo: "A busca automática corre todos os dias à meia-noite (00:00) hora de Lisboa"
- Mostrar próxima execução prevista

**Secção "Preparado para múltiplos países":**
- Dropdown "País activo": Portugal 🇵🇹 | Espanha 🇪🇸 | França 🇫🇲 | Reino Unido 🇬🇧
- Nota informativa: "Seleccionar outro país activa os portais específicos desse mercado"

**Botão "Guardar Configuração"** — faz UPSERT em k360_scrape_config

**Secção "Configuração da API do Crawler":**
- Campo texto "URL do servidor" (ex: https://meu-servidor.railway.app)
- Campo texto "API Key"
- Guardar em localStorage ou tabela de configurações
- Botão "Testar ligação" → GET /health

---

### 6. Histórico de Buscas

Tabela dos últimos 50 jobs da tabela `k360_scrape_jobs` ordenados por `iniciado_em` DESC.

Colunas: Data/Hora | País | Distritos | Portais | Encontrados | 🆕 Novos | 🔁 Duplicados | 👤 Distribuídos | Duração | Status

- Status 'running': spinner animado + badge azul
- Status 'completed': badge verde com check
- Status 'failed': badge vermelho com X e tooltip com error_log

Botão "Iniciar Busca Agora" no topo — chama a API do crawler (POST /api/search) ou insere directamente na tabela para o sistema detectar.

---

## PAINEL CONSULTOR — Páginas e Funcionalidades

O consultor só vê as leads onde `atribuido_a = auth.uid()`. O RLS do Supabase garante isto.

### 1. Dashboard do Consultor

**Métricas pessoais (cards no topo):**
- As Minhas Leads (total atribuídas)
- Para Contactar (status = 'atribuido') com badge se > 0
- Em Negociação (status = 'negociacao')
- Angariadas (status = 'angariado')

**Feed "Novas Leads Atribuídas Hoje":**
- Supabase Realtime: quando uma nova lead é atribuída a este consultor aparece aqui instantaneamente com animação de entrada suave
- Toast notification: "Nova lead atribuída: [nome], [localização]"
- Se nenhuma: "Sem novas leads hoje. A próxima busca automática é às 00:00."

**Lista rápida das leads mais urgentes:**
- Top 5 leads quentes (pontuacao >= 70) com botão "Contactar Agora"

---

### 2. As Minhas Leads (Kanban Pipeline)

Vista Kanban com 5 colunas:
1. **Para Contactar** (status='atribuido')
2. **Em Contacto** (status='em_contacto')
3. **Em Negociação** (status='negociacao')
4. **Angariado** ✅ (status='angariado')
5. **Perdido** ❌ (status='perdido')

Cada card no Kanban mostra:
- Badge temperatura (🔴🟡🔵) + pontuação
- Nome do proprietário
- Tipologia + tipo imóvel (ex: "T3 Apartamento")
- Localização (concelho)
- Preço (formatado)
- Telefone com botão de cópia rápida
- Dias desde atribuição
- Se `preco_reduziu`: ícone 📉 em destaque
- Se `palavras_urgencia` não vazio: badge "URGENTE" vermelho

Arrastar card entre colunas → update status em k360_leads + insert em k360_lead_activities com action='status_[novo_status]'.

Alternativamente (se drag and drop for complexo): botões de avançar/recuar estado em cada card.

Filtros por cima do kanban: Temperatura, Distrito, Pesquisa por nome.

---

### 3. Detalhe de Lead (drawer ou página completa)

Ao clicar em qualquer lead abre o detalhe:

**Secção "Proprietário":**
- Nome, telefone (com botão "Copiar" e link tel:), email (com botão "Copiar" e link mailto:)
- Badge "Telefone validado ✓" se telefone_valido=true
- Link para anúncio original: "Ver Anúncio Original →" abre em nova tab

**Secção "Imóvel":**
- Título do anúncio
- Tipo + Tipologia + Área + WC
- Preço actual + preço original (se diferente, mostrar "↓ Baixou de X€")
- Localização completa (freguesia, concelho, distrito)
- Dias no mercado (se >60 destacar a vermelho)
- Descrição original do anúncio

**Secção "Score de Motivação":**
- Pontuação grande centralizada com cor por temperatura
- Breakdown detalhado (da pontuacao_detalhe jsonb):
  - Cada componente como linha: ícone + label + pontos ganhos
  - Ex: "🔥 Palavras de urgência detectadas: +25 pts" (lista as palavras em badges)
  - Ex: "📅 65 dias no mercado: +18 pts"
  - Ex: "📉 Preço reduziu: +15 pts"
  - Ex: "👤 Proprietário direto: +10 pts"

**Secção "Histórico de Preços":**
- Se houver dados em k360_price_history: gráfico de linha simples (chart.js ou recharts)
- Mostrar variação percentual total

**Secção "Adicionar Nota / Actividade":**
- Dropdown de tipo de acção: "Efectuei chamada" | "Enviei email" | "Visita agendada" | "Proposta enviada" | "Nota interna"
- Campo de texto para nota
- Botão "Guardar" → insert em k360_lead_activities

**Timeline de Actividades:**
- Todas as k360_lead_activities desta lead ordenadas por criado_em DESC
- Cada entrada: ícone de acção + texto + data/hora + consultor

**Footer com botões de estado:**
- Botões para mudar status: "Marcar Em Contacto" | "Em Negociação" | "Angariado 🎉" | "Perdido"
- Ao clicar "Angariado" mostrar modal de confirmação com confetti/celebração

---

### 4. As Minhas Estatísticas

P�gina simples com métricas do consultor logado:

- Gráfico de barras: leads por status
- Taxa de contacto: (em_contacto + negociacao + angariado) / total
- Taxa de angariação: angariado / total
- Tempo médio até primeiro contacto (calculado de k360_lead_activities)
- Top distritos das suas leads
- Evolução de leads recebidas por semana (últimas 8 semanas)

---

## FUNCIONALIDADES GLOBAIS

**Notificações em tempo real (Supabase Realtime):**
- Admin: subscribe a INSERT em k360_leads → toast "X novas leads captadas" quando uma busca termina
- Admin: subscribe a INSERT em k360_scrape_jobs com status='completed' → actualiza dashboard
- Consultor: subscribe a UPDATE em k360_leads WHERE atribuido_a = uid() → toast "Nova lead atribuída: [nome]"
- Sininho de notificações no header com contador de não lidas

**Header global:**
- Logo "K360 Leads" (com ícone de casa ou seta)
- Navegação lateral com ícones (se admin: Dashboard, Pool, Todas as Leads, Consultores, Configurações, Histórico / se consultor: Dashboard, Pipeline, Estatísticas)
- Avatar do utilizador + nome + dropdown (Perfil, Sair)
- Badge de notificações não lidas

**Estado de carregamento:**
- Skeletons animados em todas as listas enquanto carregam
- Spinner global quando está a fazer chamada à API

**Páginas de erro:**
- 404 com botão voltar
- Erro de ligação Supabase com retry

**Mobile responsive:**
- Em mobile a sidebar colapsa para bottom navigation
- O Kanban fica em lista vertical em mobile
- Cards adaptam para layout vertical

---

## NOTAS TÉCNICAS PARA LOVABLE

1. **Supabase já está configurado** — usar as tabelas descritas acima
2. **A tabela `perfis` já existe** — não recriar, apenas ler dela
3. **RLS activo** — os consultores só vêm as suas leads automaticamente via Supabase RLS
4. **Admin usa service_role** — para o admin ver tudo, usar uma flag no código ou verificar uma coluna na tabela perfis
5. **API externa do crawler** — guardar a URL e API Key em localStorage ou tabela de configurações. Os botões "Buscar Agora" e "Testar Ligação" chamam essa API externa
6. **Realtime** — activar subscriptions em k360_leads e k360_scrape_jobs
7. **Formatação de preços** — sempre em € com separador de milhares (pt-PT locale)
8. **Datas** — sempre em formato português: "28 de maio de 2026 às 14:30"

