# Handoff: Web Summit Lisboa 2026 — mapear speakers × programação

Contexto levado de uma conversa no claude.ai (26/10/2026). Leia este arquivo inteiro antes de agir.
O evento é 9–12/11/2026 (Lisboa). Documento de resumo: https://claude.ai/artifact/1TMxG6imdGtBg1fERj5U6g

## Objetivo do João
1. Mapear **speakers** e **programação** do evento, cruzando "quem fala quando".
2. Entender os tipos de talks e montar um **roteiro** (3 frentes: palestras, encontros marcados com antecedência, freestyle) incluindo **meetups**.
3. Triar speakers por **encaixe com o perfil dele** e priorizar os mais acessíveis (speakers menores, perfis parecidos com o dele) para **contato prévio**.
4. Classificar por encaixe, possivelmente com a "TypeSafe JEV" (o João ainda não explicou o que é; perguntar antes de usar; sem isso, usar esquema tipado simples, ex.: pydantic/JSON schema).

## Perfil do João (para a classificação de encaixe)
- Engenheiro de Computação; fundador da Switch Dreams (software house/SaaS): devops/Kubernetes e fullstack nos 2 primeiros anos, depois comercial, growth marketer e PM/scrum master.
- Construí o **Synkrony** (SaaS de execução de projetos para times de humanos + agentes de IA, foco em times de software). https://synkrony.ai
- Interesses: Meu interesse final é uma mudança de carreira e o web summit, além de ampliar meus horizontes, pode servir para encontrar de fato pessoas que possam me contratar. Minha mira são sempre vagas remotas e que paguem em dólar, mas estou aberto a oportunidades.
- Inglês: nao será um problema pro evento, mas quero que converse comigo em portugues
- Pesos da classificação (carreira × potencial para o Synkrony × vagas FDE): Esses pesos ainda não defini

Quero que a triagem seja feita utilizando a JEV AI. Leia https://github.com/typesafe-ai/skills/blob/main/skills/typesafe-ai/SKILL.md e entenda o que é e como usar. Sinta se livre pra explorar a docs

## O que já foi descoberto (páginas públicas, sem login)
- Programação: `https://websummit.com/schedule/`. Speakers: `https://websummit.com/speakers/` (~800, botão "Load More"; perfis em `/attendees/lis26/<attendance_id>/<slug>`).
- A paginação chama um endpoint JSON do próprio site:
  `GET https://websummit.com/api/list-items/?slug=schedule&typename=DefaultTemplate_Custompage_FlexibleContent_ScheduleList&page=N&date=YYYY-MM-DD&timezone=Europe/Lisbon`
  - `page` começa em 1 (0 e 1 devolvem o mesmo). 7 sessões por página. Resposta: `data.listItems`, `data.maximumPages` (32), `data.nbPages`.
  - Cada sessão: `id`, `title`, `slug`, `description`, `date`, `starts_at`, `ends_at` (UTC; em novembro Lisboa = UTC+0), `location.name` (palco), `schedule_track.name`, `timeslot_participations[]` com `attendance_id`, `name`, `job_title`, `company_name`, `avatar_urls`.
  - Filtro extra: `filters=<base64 de JSON>`. O filtro Highlights é `{"curated_tracks.name":"highlights"}`.
- **Teto da API: 32 páginas × 7 = 224 sessões por consulta.** Sem filtro, só aparecem os dias 9 e 10. Os dias 10 e 11 bateram exatamente 224 (truncados); o dia 12 não foi verificado. Por isso é preciso subdividir por **dia × trilha**.
- **Não confirmado:** a chave do filtro de trilha. Hipótese: `{"schedule_track.name": "<trilha>"}`. Confirmar pelo DevTools (marcar uma trilha no painel Filters do /schedule/ e decodificar o `filters=` do request) ou testando.
- Trilhas vistas nos dados: AI Summit, Centre Stage, Corporate Innovation Summit, Developer Summit, Energy Summit, Future of Work Summit, Investor Masterclass, Marketing Summit, Masterclasses, Meetup (59 só entre as 224 primeiras do dia 10), MoneyConf, New Media Summit, Night Summit, Policy Summit, Press Conference, Venture Summit, Women in tech; mais Commerce, Cybersecurity, Growth, Health, SaaS, Sport, Startup Masterclass, Creative no painel de filtros. Seis sessões têm trilha vazia (não alcançáveis por filtro de trilha).
- Meetups são sessões da trilha/formato "Meetup" (ex.: "First timers at Web Summit", "Product people meetup", 10/11).
- Candidatos iniciais vistos: Samar Abbas (CEO, Temporal; "Bet on the foundation, not the framework", AI Summit, 10/11 11h35) e Michele Catasta (President & Head of AI, Replit; ainda não cruzado com a programação).

## Estado do código
`websummit_schedule.py` (neste mesmo diretório): stdlib Python 3.8+. Faz consulta por dia; se bater no teto, subdivide por trilha (descobrindo trilhas novas nos dados) e valida a chave do filtro (aborta com `FilterKeyError` se a API ignorar o filtro). Gera `saida/sessions.json`, `sessions.csv`, `participants.csv`, `speakers.csv`. Foi testado só contra uma API simulada; **nunca rodou contra o site real**.

## Próximos passos sugeridos
1. Rodar `python3 websummit_schedule.py` (rede liberada na máquina do João); se `FilterKeyError`, descobrir a chave certa e ajustar `TRACK_KEY`. Conferir os avisos de teto por dia × trilha e o total por dia.
2. Extrair também `/speakers/` (e `/featured-attendees/`) pelo mesmo padrão `/api/list-items/` (capturar `slug` e `typename` no DevTools do "Load More"), para bio e tema.
3. Cruzar tudo em uma base única (speaker × sessão) e classificar por encaixe com o perfil acima.
4. Montar roteiro por dia (apontando conflitos de horário entre palcos) e lista de quem contatar antes, com **rascunho** de mensagem (em inglês) para cada pessoa.

## Limites (respeitar)
- Só páginas e endpoints **públicos**. `lisbon.cilabs.com` e `attend.websummit.com` são o app logado: **não** raspar nem contornar login. A lista completa de attendees fica lá; se necessário, quem entra é o João, com a conta dele.
- Pausa de ~0,4 s entre requests; são poucas centenas de chamadas.
- Nunca enviar mensagens em nome do João; só preparar rascunhos para ele revisar e enviar.
- Dados de pessoas: usar só para o planejamento pessoal de networking dele.