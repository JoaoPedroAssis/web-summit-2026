# Perfil e critérios de triagem — Web Summit Lisboa 2026

Este arquivo é lido pelo `triage.py`. Edite o texto em português à vontade:
tudo aqui vira contexto (state) para a Jev avaliar cada pessoa. Não há mais
pesos de dimensões: a classificação é **por tipo de conexão**, e o bloco
JSON no fim guarda só configuração.

## Quem sou

Engenheiro de Computação, fundador da Switch Dreams (software house/SaaS):
comecei em devops/Kubernetes e fullstack, e depois migrei para comercial,
growth marketing e PM/scrum master. Construí o Synkrony (synkrony.ai), SaaS
de execução de projetos para times de humanos + agentes de IA. Meu
interesse final é uma mudança de carreira: quero crescer, ampliar horizontes
e, na prática, encontrar pessoas que possam me contratar ou abrir portas —
mas de forma orgânica: primeiro relação e aprendizado, oportunidade como
consequência, nunca como pedido direto. Mira principal em vagas remotas
pagas em dólar, mas aberto a qualquer oportunidade interessante
(parcerias, indicações, clientes).

## O que quero desta triagem

Quero me conectar com **vários tipos de pessoas**, e cada tipo serve a um
propósito diferente. Para cada candidato, identifique o tipo principal de
conexão:

- **par** — trajetória parecida com a minha: engenharia → growth/produto,
  fundador em estágio inicial, construiu o próprio SaaS/software. Conversa
  de igual para igual; são as relações mais fáceis de começar e as que
  mais rendem surpresas, inclusive profissionais.
- **referencia** — já fez com sucesso o caminho que eu quero trilhar, em
  escala maior: líderes de growth para software, founders que escalaram ou
  venderam empresa, pessoas que saíram de engenharia e chegaram longe em
  produto/comercial. Quero aprender com elas.
- **porta** — pode, de forma realista, gerar uma oportunidade de emprego
  para mim: hiring manager, founder contratando, recrutador, VC com
  portfólio contratando, ou pessoa em empresa que contrata remoto.
  Remoto/pago em dólar é preferência, não filtro. Também vale quem pode me
  apresentar essas pessoas.
- **contexto** — a conexão vale pelo conteúdo: IA aplicada a times de
  software, produto, execução de projetos, temas das talks. Sem interesse
  comercial; é gente com quem a conversa técnica/produto flui.

Nenhum tipo é melhor que outro. A nota de prioridade mede só uma coisa:
**quanto vale o esforço de procurar essa pessoa no evento**, considerando
o tipo dela e a acessibilidade.

## Como avaliar acessibilidade

Dou preferência a perfis parecidos com o meu (fundadores em estágio inicial,
IC sênior, gente que migrou de engenharia), porque a conversa flui de par a
par, não como fã pedindo emprego. Keynotes lotados e executivos de
megacorporação são conversas mais difíceis; speakers de palcos pequenos
(Masterclasses, Meetup) e participantes de meetup são mais acessíveis.

## Sessões e meetups

Pessoas que participam de meetups são mais fáceis de abordar presencialmente.
Palestras em palcos pequenos (Masterclasses, Meetup) valem mais que keynotes
lotados para efeito de contato.

## Configuração

```json
{
  "confianca_min": 0.5,
  "top_por_tipo": 15
}
```
