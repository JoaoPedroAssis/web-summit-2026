# Web Summit Lisboa 2026 — triagem de speakers × programação

Pipeline pessoal de networking para o Web Summit Lisboa (9–12/11/2026):
coletar a programação e os speakers públicos do evento, cruzar quem fala
quando, e triar as pessoas por **tipo de conexão** com meu perfil — para
montar roteiro por dia e uma lista de contatos prévios, com rascunho de
mensagem para revisar antes de enviar.

## Pipeline

| Passo | Script | O que faz |
|---|---|---|
| 1 | `python3 src/fetch.py` | Baixa a programação da API pública (`/api/list-items/`), subdividindo por trilha quando o dia bate no teto de 224 sessões → `data/raw/schedule/` |
| 2 | `python3 src/consolidate.py` | Deduplica participações e agrega por pessoa → `data/people.json`, `data/sessions.json` |
| 3 | `python3 src/fetch_profiles.py` | Baixa bios públicas dos speakers (`__NEXT_DATA__` das páginas de attendee) → `data/raw/profiles/` |
| 4 | `python3 src/triage.py` | Classifica cada pessoa com a Jev (TypeSafe System One): **tipo** (par / referencia / porta / contexto), **prioridade** 0–4, **gancho** de abordagem e gating `alvo_valido`. Cache incremental em `data/triage_cache.json` → `data/ranking.json`, `data/ranking.csv` |
| 5 | `python3 src/roteiro.py` | Gera `data/roteiro.md` (plano por dia, conflitos de horário, meetups) e `data/dossie.md` (top N com rascunho de mensagem em inglês) |
| 6 | `python3 src/gera_relatorio.py` | Gera `data/relatorio.html` — relatório completo autossuficiente: as 4 listas com rascunhos, roteiro por dia, analytics da run e metodologia |
| — | `python3 src/gera_dia12_md.py` | Gera `docs/dia12_programacao.md`: programação completa do dia 12 após o cancelamento do dia 11 (tempestade Charles), com status remanejada/nova/já estava |
| — | `python3 src/services_software.py` | Pipeline temático independente: cruza o evento com a tese **Services as Software / AI-Native Services** (Sequoia + Emergence) — scan determinístico + Jev → `data/services_software.html` |

`docs/dashboard.html` é um visualizador offline dos agregados de coleta
(`data/analysis.json`, gerado pelo `fetch.py`).

## Estrutura

```
src/      scripts do pipeline (rodar sempre da raiz: python3 src/<script>.py)
docs/     Handoff, cartão de contato, dashboard e dia12_programacao.md (versionado)
backup/   versões anteriores e o raw do dia 12 pré-remanejamento
data/     saídas e raw (ignorado pelo git)
perfil.md configuração/perfil usado na triagem
```

## Configuração

- **`perfil.md`** — quem eu sou, definição dos tipos de conexão e critérios.
  Tudo vira contexto (state) para a Jev. O bloco ```json``` no fim guarda
  configuração (`confianca_min`, `top_por_tipo`).
- **`.env`** (não versionado) — `TYPESAFE_API_KEY=...`
- Python 3.8+, só stdlib (certifi opcional para SSL).

## Flags úteis do triage.py

```
python3 src/triage.py --limit 10     # teste de sanidade com 10 pessoas
python3 src/triage.py --amostra 30   # amostra estratificada
python3 src/triage.py --refazer      # descarta o cache e refaz tudo
python3 src/triage.py --agregar      # só re-agrega o ranking (não consome API)
```

## Decisões de design

- **Classificação por tipo de conexão, não soma ponderada** — a nota de
  prioridade é bruta; confiança baixa da Jev marca a pessoa para revisão
  manual em vez de penalizar a nota.
- **Sem viés comercial** — nada de Synkrony/produto na triagem nem nas
  mensagens; as portas de oportunidade são um tipo explícito (`porta`).
- **Cache por pessoa, gravado a cada lote** — rerodar pula quem já foi
  avaliado; crash no meio do run não perde nada.
- Versão anterior do sistema (4 dimensões ponderadas) está em `backup/`.

## Limites

Só páginas e endpoints **públicos** do websummit.com (sem raspar o app
logado). Dados de pessoas usados exclusivamente para planejamento pessoal
de networking — por isso `data/` não vai para o git. Mensagens nunca são
enviadas automaticamente: só rascunhos para revisão.
