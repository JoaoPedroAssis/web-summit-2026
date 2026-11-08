#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pipeline "Services as Software" (AI-Native Services) — tema, não substitui
o pipeline principal; cruza com ele.

Tese (Sequoia "Services: The New Software" + Emergence "AI-Native
Services"): empresas de software que VENDEM O TRABALHO/outcome com
agentes de IA em vez de vender ferramenta — "copilot vende a ferramenta,
autopilot vende o trabalho"; pricing por outcome; a cunha é a tarefa
outsourced e intelligence-heavy; verticais: contabilidade/fiscal, jurídico
transacional, seguros/claims, revenue cycle de saúde, TI gerenciada,
procurement/supply chain, recrutamento/staffing, consultoria,
engenharia de software.

Camadas:
  1. Scan determinístico (regex) de conceito + verticais + empresas-cânon
     sobre cargo/empresa/bio/industry/palestras de pessoas e título/
     descrição de sessões -> data/services_scan.json
  2. Classificação Jev só dos candidatos (encaixe 0-4, papel, vertical)
     com cache próprio -> data/services_cache.json
  3. Relatório autossuficiente -> data/services_software.html

Uso:
  python3 services_software.py            # tudo (scan + Jev + HTML)
  python3 services_software.py --no-jev   # só scan + HTML determinístico
"""

import argparse
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = None

sys.path.insert(0, str(Path(__file__).parent))
from triage import http_post_json, ler_dotenv, MODEL  # noqa: E402
from gera_relatorio import (CSS, esc, hhmm, DIAS, tabela_dados)  # noqa: E402

API_URL = "https://api.typesafe.ai/v1/systemone"
BATCH = 10
PAUSE = 0.3

# ------------------------------------------------------------------ tese

TESE_PT = """## Tese: Services as Software (AI-Native Services)

Fontes: Sequoia Capital, "Services: The New Software"
(https://sequoiacap.com/article/services-the-new-software) e Emergence
Capital, "AI-Native Services" (https://www.emcap.com/ai-native-services).

A ideia central: empresas de software que VENDEM O TRABALHO (o outcome)
em vez de vender ferramenta. Frases-chave da tese:
- "Copilots sell the tool. Autopilots sell the work."
- "The next $1T company will be a software company masquerading as a
  services firm."
- "The service IS the outcome" (Emergence).
- Pricing por outcome em vez de seat/license ("sell outcomes, not seats").
- Para cada $1 de software gasto, $6 vão para serviços — o TAM é o
  orçamento de trabalho (labor budget) de uma categoria.
- A cunha certa: tarefas JÁ OUTSOURCED e intelligence-heavy (troca de
  fornecedor, não reorg). Intelligence (regras complexas mas regras:
  código, formulários, tradução, triagem) automatiza antes que judgement
  (experiência, gosto, decisão).
- Transição copilot -> autopilot em 2026.

Verticais do opportunity map da Sequoia (com TAM de serviços):
corretagem/seguros, contabilidade e auditoria, revenue cycle de saúde e
medical coding, ajuste de claims, consultoria tributária, jurídico
transacional (contratos, NDAs, filings), TI gerenciada (MSP),
procurement/supply chain, recrutamento e staffing, consultoria de gestão,
e engenharia de software (o primeiro vertical onde agentes já executam a
maior parte do trabalho).

Empresas-cânon citadas nos artigos: Harvey, Crosby, Lawhive, Rogo,
WithCoverage, Harper, Rillet, Basis, Anterior, Pace, Strala, TaxGPT,
Skalar, Ravical, Edra, Serval, Magentic, AskLio, Tacto, Juicebox,
Mercor."""

# regex de conceito (forte) — o vocabulário da tese em inglês
CONCEITO_RE = [
    r"services?[- ]as[- ]a?[- ]?software", r"ai[- ]native services?",
    r"\bautopilots?\b", r"\bautonomous? (agents?|workflows?|services?)\b",
    r"sell(?:ing)? the (?:work|outcome|service)", r"sells? (?:the )?outcomes?",
    r"outcome[- ]based (?:pricing|model)", r"results[- ]based pricing",
    r"(?:labor|labour|work) budget", r"sell(?:ing)? outcomes?, not seats",
    r"end of (?:seats|saas)", r"seat[- ]based pricing",
    r"\bBPO\b", r"business process outsourc",
    r"(?:replac\w+|augment\w+) (?:the )?(?:consultants?|accountants?|"
    r"lawyers?|attorneys?|paralegals?|bookkeepers?|recruiters?|agents?|"
    r"agencies?|brokers?|adjusters?|engineers?|developers?|teams?|"
    r"headcount|humans?|workers?|employees?|workforce)",
    r"agents? (?:doing|delivering|performing|handling) the work",
    r"agentic (?:services?|workforce|labor|labour|economy|outsourcing)",
    r"human[- ](?:agent|AI) (?:team|workforce|collaboration)",
    r"software(?:-| )as(?:-| )a(?:-| )service is dead",
    r"(?:AI|agents?) (?:does|do|handles?|runs?|closes?|drafts?|settles?|"
    r"files?|books?|codes?) the work",
]
CONCEITO = [re.compile(p, re.I) for p in CONCEITO_RE]

# verticais da tese (sinal médio — vertical sem IA-agente é só periférico)
VERTICAIS = {
    "engenharia_software": [
        r"software (?:engineering|development) (?:as a )?service",
        r"(?:agents?|AI) (?:that )?(?:writes?|ships?|tests?|reviews?|"
        r"maintains?|fixes?) (?:code|software|PRs?|bugs?)",
        r"AI (?:software )?engineer", r"autonomous (?:coding|software)",
    ],
    "juridico": [
        r"legal(?:tech)?", r"\bcontracts? (?:AI|automation|drafting)\b",
        r"\bNDA", r"contract (?:review|analysis|lifecycle)",
        r"regulatory filings?", r"\bcounsel\b.*(?:AI|automat)",
    ],
    "contabilidade_fiscal": [
        r"accounting", r"bookkeep", r"\bbooks? clos", r"close the books",
        r"\baudit", r"\btax (?:AI|advis\w+|preparation|automation)\b",
        r"\bCPA\b", r"\bERP\b", r"financial close",
    ],
    "seguros_claims": [
        r"insurance (?:broker|AI|automation|tech)", r"insurtech",
        r"claims? (?:processing|adjust\w+|automation|handling)",
        r"underwrit", r"policy (?:shopping|binding)",
    ],
    "saude_revenue_cycle": [
        r"revenue cycle", r"medical coding", r"\bICD", r"billing.*health",
        r"health(?:care)? (?:billing|back office|admin)",
    ],
    "ti_gerenciado": [
        r"managed services", r"\bMSP\b", r"IT (?:support|ops|managed)",
        r"help ?desk (?:AI|automation)", r"service ?desk",
    ],
    "procurement_supply": [
        r"procure", r"supply chain (?:AI|automation)",
        r"purchase[- ]?to[- ]?pay", r"contract leakage",
    ],
    "recrutamento_staffing": [
        r"recruit", r"staffing", r"talent (?:matching|acquisition) "
        r"(?:AI|agent)", r"hiring (?:agent|AI|automation)",
        r"screening (?:AI|agents?)",
    ],
    "consultoria": [
        r"management consulting", r"consultanc", r"consulting (?:firm|AI)",
        r"strategy (?:consult|work)", r"professional services",
    ],
}
VERTICAL_RES = {k: [re.compile(p, re.I) for p in ps]
                for k, ps in VERTICAIS.items()}
VERTICAL_ROTULO = {
    "engenharia_software": "Engenharia de software",
    "juridico": "Jurídico transacional",
    "contabilidade_fiscal": "Contabilidade e fiscal",
    "seguros_claims": "Seguros e claims",
    "saude_revenue_cycle": "Saúde / revenue cycle",
    "ti_gerenciado": "TI gerenciada (MSP)",
    "procurement_supply": "Procurement e supply chain",
    "recrutamento_staffing": "Recrutamento e staffing",
    "consultoria": "Consultoria",
}

# empresas-cânon citadas nos dois artigos — SÓ nomes distintivos (sem
# "harvey"/"pace"/"crosby"/"basis"/"cursor": colidem com pessoas e marcas
# comuns — Harvey Nash, Julie Pace, Nicky Crosby, Eclipse Cursor…)
CANONICAS = [
    "lawhive", "withcoverage", "taxgpt", "skalar", "ravical", "rillet",
    "magentic", "asklio", "juicebox", "mercor", "lawhive", "anterior",
]

# sinal fraco (chamada pra Jev decidir): discurso de agentes + palavra de
# vertical da tese no mesmo texto
FRACO_RE = re.compile(
    r"\b(?:agent\w*|agentic|copilot|autopilot|AI)\b", re.I)
VERTICAL_FRACO_RE = re.compile(
    r"\b(?:service|services|consult\w*|legal|law|account\w*|bookkeep\w*|"
    r"tax|audit\w*|insurance|claims?|broker\w*|procure\w*|supply chain|"
    r"recruit\w*|staffing|managed (?:services|IT)|MSP|billing|back ?office|"
    r"outsourc\w*|BPO|professional services|operations?|support)\b", re.I)

# rubrica de encaixe na tese 0-4
ENCAIXE = [
    "Nada a ver com a tese Services as Software",
    "Menção genérica a IA; nada sobre vender serviços/outcomes com agentes",
    "Periférico: automação de um vertical da tese sem agentes executando "
    "trabalho, ou fala da tese só de passagem",
    "Forte: constrói, financia ou adota agentes que executam trabalho de "
    "serviços (copilot ou autopilot) num dos verticais da tese",
    "Personificação da tese: fundador/exec de empresa que vende o "
    "trabalho/outcome com IA (autopilot, AI-native services), ou "
    "referência direta em services-as-software",
]

PAPÉIS = {
    "constroi": "Founder/exec de empresa AI-native services (vende o trabalho/outcome com IA)",
    "financia": "VC/investidor apostando na tese",
    "opera": "Exec de empresa de serviços tradicional (BPO, consultoria, MSP, advocacia) em transição",
    "adopta": "Exec de empresa cliente comprando/adotando agentes para executar trabalho interno",
    "divulga": "Analista, imprensa, criador de conteúdo sobre a tese",
}


# ------------------------------------------------------------------ scan

def ler_ranking(path):
    p = Path(path)
    if not p.exists():
        return []
    return json.loads(p.read_text("utf-8"))["ranking"]


def texto_pessoa(r, prof):
    """Todo o texto de uma pessoa para o scan."""
    det = (prof or {}).get("details") or {}
    partes = [r["name"], r["job_title"] or "", r["company_name"] or "",
              det.get("industry") or "", det.get("hashtags") or "",
              r.get("bio") or ""]
    for t in r.get("talks") or []:
        partes.append(t)
    return "\n".join(x for x in partes if x)


def scan_texto(txt):
    """(conceitos, verticais, canonicas) encontrados num texto."""
    conceitos = [m.group(0) for pat in CONCEITO for m in [pat.search(txt)]
                 if m]
    verticais = [k for k, pats in VERTICAL_RES.items()
                 if any(p.search(txt) for p in pats)]
    low = txt.lower()
    canonicas = [c for c in CANONICAS
                 if re.search(r"\b{}\b".format(re.escape(c)), low)]
    return conceitos, verticais, canonicas


def scan_pessoas(ranking, profiles_dir):
    out = []
    for r in ranking:
        f = Path(profiles_dir) / "{}.json".format(r["attendance_id"])
        prof = json.loads(f.read_text("utf-8")) if f.exists() else {}
        txt = texto_pessoa(r, prof)
        conceitos, verticais, canonicas = scan_texto(txt)
        forte = bool(conceitos or canonicas)
        # sinal fraco: discurso de agentes + palavra de vertical da tese
        fraco = (not forte and bool(FRACO_RE.search(txt))
                 and bool(VERTICAL_FRACO_RE.search(txt)))
        if not (forte or fraco):
            continue
        score = 2 * len(conceitos) + 3 * len(canonicas) + len(verticais)
        if fraco:
            score = max(score, 1)
        out.append({
            "attendance_id": r["attendance_id"], "name": r["name"],
            "job_title": r["job_title"], "company_name": r["company_name"],
            "conceitos": conceitos[:6], "verticais": verticais,
            "canonicas": canonicas, "scan_score": score,
            "prioridade_main": r["prioridade"],
            "tipo_main": r["tipo"], "no_escopo_main": r["no_escopo"],
            "revisar_main": r["revisar"],
            "bio": (r.get("bio") or "")[:300],
            "talks": r.get("talks") or [],
            "sessions": r.get("sessions") or [],
            "in_meetup": r.get("in_meetup"),
        })
    out.sort(key=lambda x: -x["scan_score"])
    return out


def scan_sessoes(sessions, ranking, profiles_dir):
    """Título + descrição (as descrições vêm dos perfis) de cada sessão."""
    # descrição por session id a partir dos perfis
    desc = {}
    for f in Path(profiles_dir).glob("*.json"):
        try:
            prof = json.loads(f.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for s in prof.get("sessions") or []:
            if s.get("id") and s.get("description"):
                desc[s["id"]] = s["description"]
    out = []
    nome = {p["attendance_id"]: p["name"] for p in ranking}
    for s in sessions:
        txt = "\n".join([s.get("title") or "", desc.get(s["id"], "")])
        conceitos, verticais, canonicas = scan_texto(txt)
        forte = bool(conceitos or canonicas)
        fraco = (not forte and bool(FRACO_RE.search(txt))
                 and bool(VERTICAL_FRACO_RE.search(txt)))
        if not (forte or fraco):
            continue
        score = 2 * len(conceitos) + 3 * len(canonicas) + len(verticais)
        if fraco:
            score = max(score, 1)
        out.append({
            "id": s["id"], "title": s.get("title"), "date": s.get("date"),
            "starts_at": s.get("starts_at"), "ends_at": s.get("ends_at"),
            "track": s.get("track"), "location": s.get("location"),
            "speakers": [nome.get(a, a) for a in s.get("speaker_ids") or []],
            "conceitos": conceitos[:6], "verticais": verticais,
            "canonicas": canonicas, "scan_score": score,
            "tem_descricao": s["id"] in desc,
        })
    out.sort(key=lambda x: -x["scan_score"])
    return out


# -------------------------------------------------------------------- jev

def montar_request(people_batch, sessions_batch):
    candidatos = [{
        "indice": i,
        "nome": c["name"], "cargo": c["job_title"],
        "empresa": c["company_name"], "bio": c["bio"] or "sem bio",
        "palestras": [t[:180] for t in (c.get("talks") or [])[:3]],
    } for i, c in enumerate(people_batch)]
    sessoes = [{
        "indice": 100 + j,
        "titulo": s["title"], "trilha": s["track"] or "?",
        "descricao": "", "speakers": s["speakers"][:4],
    } for j, s in enumerate(sessions_batch)]
    state = {"tese_services_as_software": TESE_PT,
             "candidatos": candidatos, "sessoes": sessoes}
    perguntas = {}
    for i in range(len(people_batch)):
        perguntas["p{}_encaixe".format(i)] = {
            "type": "score",
            "instructions": (
                "Quão central é `candidatos[{}]` ({}) para a tese "
                "services-as-software descrita no state, considerando "
                "cargo, empresa, bio e palestras?".format(
                    i, people_batch[i]["name"])),
            "criteria": ENCAIXE,
        }
        perguntas["p{}_papel".format(i)] = {
            "type": "choice",
            "instructions": (
                "Qual o papel de `candidatos[{}]` ({}) em relação à "
                "tese?".format(i, people_batch[i]["name"])),
            "criteria": PAPÉIS,
        }
        perguntas["p{}_vertical".format(i)] = {
            "type": "choice",
            "instructions": (
                "Se `candidatos[{}]` ({}) se encaixa na tese, qual o "
                "vertical principal? Senão escolha nenhum.".format(
                    i, people_batch[i]["name"])),
            "criteria": {k: VERTICAL_ROTULO[k] for k in VERTICAL_ROTULO},
        }
    for j in range(len(sessions_batch)):
        k = 100 + j
        perguntas["s{}_encaixe".format(k)] = {
            "type": "score",
            "instructions": (
                "A sessão `sessoes[{}]` ('{}') trata da tese "
                "services-as-software descrita no state?".format(
                    k, (sessions_batch[j]["title"] or "")[:120])),
            "criteria": ENCAIXE,
        }
        perguntas["s{}_vertical".format(k)] = {
            "type": "choice",
            "instructions": (
                "Se `sessoes[{}]` trata da tese, qual o vertical? "
                "Senão, nenhum.".format(k)),
            "criteria": {k2: VERTICAL_ROTULO[k2] for k2 in VERTICAL_ROTULO},
        }
    return {"model": MODEL, "state": state, "questions": perguntas}


def classificar_jev(pessoas, sessoes, cache, api_key, cpath):
    """Lotes combinando pessoas + sessões por request."""
    pend = [(c, None) for c in pessoas] + [(None, s) for s in sessoes]
    pend = [x for x in pend
            if (x[0] and x[0]["attendance_id"] not in cache)
            or (x[1] and x[1]["id"] not in cache)]
    print("a classificar na Jev: {} itens".format(len(pend)))
    tot_in = tot_out = 0
    for b in range(0, len(pend), BATCH):
        lote = pend[b:b + BATCH]
        pb = [x[0] for x in lote if x[0]]
        sb = [x[1] for x in lote if x[1]]
        payload = montar_request(pb, sb)
        for attempt in range(1, 4):
            try:
                resp = http_post_json(API_URL, payload, api_key)
                break
            except (urllib.error.HTTPError, urllib.error.URLError,
                    TimeoutError) as e:
                if attempt == 3:
                    print("  falha no lote: {}".format(e))
                    resp = None
                    break
                time.sleep(3 * attempt)
        if resp is None:
            continue
        respostas = resp.get("answers") or {}
        uso = resp.get("usage") or {}
        tot_in += uso.get("input_tokens") or 0
        tot_out += uso.get("output_tokens") or 0
        for i, c in enumerate(pb):
            cache[c["attendance_id"]] = {
                "encaixe": respostas.get("p{}_encaixe".format(i)),
                "papel": respostas.get("p{}_papel".format(i)),
                "vertical": respostas.get("p{}_vertical".format(i)),
            }
        for j, s in enumerate(sb):
            cache[s["id"]] = {
                "encaixe": respostas.get("s{}_encaixe".format(100 + j)),
                "vertical": respostas.get("s{}_vertical".format(100 + j)),
            }
        cpath.write_text(json.dumps(cache, ensure_ascii=False), "utf-8")
        print("  {}/{} (tokens in={} out={})".format(
            min(b + BATCH, len(pend)), len(pend), tot_in, tot_out))
        time.sleep(PAUSE)
    return cache


# ------------------------------------------------------------------ html

def nota_encaixe(cache, aid, alt_id=None):
    r = cache.get(aid) or (cache.get(alt_id) if alt_id else None) or {}
    e = (r.get("encaixe") or {})
    return e.get("score"), e.get("confidence")


def card_pessoa_sas(c, jev, pos, main_by_id, score_fallback):
    score, conf = (jev.get("encaixe") or {}).get("score"), \
        (jev.get("encaixe") or {}).get("confidence")
    if score is None:
        score, conf = score_fallback, None
    papel = (jev.get("papel") or {}).get("choice")
    vertical = (jev.get("vertical") or {}).get("choice")
    m = main_by_id.get(c["attendance_id"]) or {}
    evid = []
    for t in (c.get("conceitos") or [])[:3]:
        evid.append("“{}”".format(t))
    if c.get("canonicas"):
        evid.append("cita: " + ", ".join(c["canonicas"][:4]))
    onde = ["{}/{} {}h — {} ({})".format(
        s["date"][8:10], s["date"][5:7], hhmm(s["starts_at"]),
        esc(s["title"]), esc(s["track"] or "?"))
        for s in (c.get("sessions") or [])]
    main_score = m.get("prioridade")
    main_html = ""
    if m and not m.get("no_escopo"):
        main_html = ('<span class="score">rede: {:.0f} · {}</span>'
                     .format(main_score, m.get("tipo") or "?"))
    return """
<article class="pessoa">
  <div class="p-topo"><span class="dot" style="background:var(--series-2)"></span>
    <strong>{}. {}</strong> <span class="score">{:.0f}/4</span></div>
  <div class="p-cargo">{}</div>
  <div class="p-meta">papel: {} · vertical: {} · conf. {} {}</div>
  <div class="p-meta">evidência: {}</div>
  <div class="p-bio">{}</div>
  <details><summary>📍 onde encontrar</summary><ul class="onde">{}</ul></details>
</article>""".format(
        pos, esc(c["name"]), score or 0,
        esc("{} @ {}".format(c["job_title"] or "?",
                             c["company_name"] or "?")),
        PAPÉIS.get(papel, papel or "?"),
        VERTICAL_ROTULO.get(vertical, vertical or "?"),
        "{:.2f}".format(conf) if conf else "?",
        main_html,
        esc("; ".join(evid) or "—"),
        esc(c.get("bio") or "")[:220],
        "".join("<li>{}</li>".format(o) for o in onde) or "<li>—</li>")


def gerar_html(pessoas, sessoes, cache, ranking, out_path, usou_jev):
    main_by_id = {p["attendance_id"]: p for p in ranking}

    # encaixe JEV (ou scan_score normalizado quando sem JEV)
    def encaixe_p(c):
        s, _ = nota_encaixe(cache, c["attendance_id"])
        return s if s is not None else min(4.0, c["scan_score"] / 3.0)

    def encaixe_s(s):
        r = cache.get(s["id"]) or {}
        v = (r.get("encaixe") or {}).get("score")
        return v if v is not None else min(4.0, s["scan_score"] / 3.0)

    pessoas_ok = [c for c in pessoas if encaixe_p(c) >= 2.0
                  and not c["no_escopo_main"]]
    pessoas_ok.sort(key=lambda c: -encaixe_p(c))
    sessoes_ok = [s for s in sessoes if encaixe_s(s) >= 1.0]
    sessoes_ok.sort(key=lambda x: -encaixe_s(x))

    doc = ["<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>",
           "<meta name='viewport' content='width=device-width, "
           "initial-scale=1'>",
           "<title>Web Summit 2026 — Services as Software</title>",
           "<style>{}</style></head><body><main>".format(CSS)]
    doc.append("<h1>Services as Software — pessoas e eventos</h1>")
    doc.append("<p class='sub'>Cruzamento do evento com a tese "
               "<em>services-as-software / AI-native services</em> "
               "(<a href='https://sequoiacap.com/article/"
               "services-the-new-software'>Sequoia</a> + <a href="
               "'https://www.emcap.com/ai-native-services'>Emergence "
               "Capital</a>): empresas que vendem o <strong>trabalho</strong>"
               " (outcome) com agentes de IA em vez de vender ferramenta. "
               "{} pessoas e {} sessões passaram do scan; {} pessoas "
               "(encaixe ≥ 2/4) e {} sessões (≥ 1/4 — muitas julgadas só "
               "pelo título) entraram no relatório{}.</p>".format(
                   len(pessoas), len(sessoes), len(pessoas_ok),
                   len(sessoes_ok),
                   " (classificação Jev)" if usou_jev
                   else " (só scan determinístico — sem Jev)"))
    doc.append("<blockquote>" + esc(
        "Copilots sell the tool. Autopilots sell the work. — Sequoia") +
        "</blockquote>")

    doc.append("<h2>1 · Pessoas ({})</h2>".format(len(pessoas_ok)))
    doc.append("<p class='sub'>Ordenadas pelo encaixe na tese (0–4): "
               "≥ 3 personifica a tese; 2–2.5 é relacionada. O selo "
               "'rede: N · tipo' é a prioridade da triagem principal — "
               "quanto maior, mais fácil de conectar.</p>")
    for i, c in enumerate(pessoas_ok, 1):
        doc.append(card_pessoa_sas(
            c, cache.get(c["attendance_id"]) or {}, i,
            main_by_id, encaixe_p(c)))

    doc.append("<h2>2 · Eventos e sessões</h2>")
    doc.append("<p class='sub'>Sessões que tocam a tese, da mais alinhada "
               "para a menos. ★ = encaixe ≥ 2 (on-tese); as outras são "
               "adjacentes — a maioria foi julgada só pelo título porque "
               "a API pública não expõe a descrição de todas as "
               "sessões.</p>")
    doc.append("<ul class='sessoes'>")
    for s in sessoes_ok:
        star = "★" if encaixe_s(s) >= 2.0 else "·"
        rv = cache.get(s["id"]) or {}
        vert = (rv.get("vertical") or {}).get("choice")
        extra = " · {}".format(VERTICAL_ROTULO.get(vert, vert)) \
            if vert and vert != "nenhum" else ""
        doc.append(
            "<li><span class='est'>{}</span> <strong>{} {}–{}h</strong> "
            "{} <span class='meta'>({},{}){}</span>"
            "<div class='quem'>{}</div></li>".format(
                star, s["date"][8:10], hhmm(s["starts_at"]),
                hhmm(s["ends_at"]),
                esc(s["title"]), esc(s["track"] or "sem trilha"),
                esc(s["location"] or "?"), extra,
                esc(", ".join(s["speakers"][:5]) or "—")))
    doc.append("</ul>")

    # mini-analytics
    doc.append("<h2>3 · Panorama</h2>")
    papel_c = Counter((cache.get(c["attendance_id"]) or {})
                      .get("papel", {}).get("choice")
                      for c in pessoas_ok)
    vert_c = Counter((cache.get(c["attendance_id"]) or {})
                     .get("vertical", {}).get("choice")
                     for c in pessoas_ok)
    doc.append("<h3>Pessoas por papel na tese</h3>")
    doc.append(tabela_dados(
        ["papel", "pessoas"],
        [(PAPÉIS.get(k, k or "?"), v) for k, v in papel_c.most_common()]))
    doc.append("<h3>Pessoas por vertical</h3>")
    doc.append(tabela_dados(
        ["vertical", "pessoas"],
        [(VERTICAL_ROTULO.get(k, k or "?"), v)
         for k, v in vert_c.most_common()]))
    doc.append("<footer>Pipeline services_software.py — scan "
               "determinístico + Jev. Dados públicos do evento, uso "
               "pessoal.</footer>")
    doc.append("</main></body></html>")
    Path(out_path).write_text("\n".join(doc), "utf-8")
    print("relatório: {} ({} bytes)".format(out_path,
                                            Path(out_path).stat().st_size))


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ranking", default="data/ranking.json")
    ap.add_argument("--sessions", default="data/sessions.json")
    ap.add_argument("--profiles", default="data/raw/profiles")
    ap.add_argument("--cache", default="data/services_cache.json")
    ap.add_argument("--scan-out", default="data/services_scan.json")
    ap.add_argument("--out", default="data/services_software.html")
    ap.add_argument("--no-jev", action="store_true")
    ap.add_argument("--max-pessoas", type=int, default=80)
    ap.add_argument("--max-sessoes", type=int, default=40)
    args = ap.parse_args()

    ranking = ler_ranking(args.ranking)
    sessions = json.loads(Path(args.sessions).read_text("utf-8"))

    pessoas = scan_pessoas(ranking, args.profiles)
    sessoes = scan_sessoes(sessions, ranking, args.profiles)
    print("scan: {} pessoas / {} sessões com sinais da tese".format(
        len(pessoas), len(sessoes)))
    Path(args.scan_out).write_text(json.dumps(
        {"pessoas": pessoas, "sessoes": sessoes},
        ensure_ascii=False, indent=1), "utf-8")

    cache = {}
    cpath = Path(args.cache)
    if cpath.exists():
        cache = json.loads(cpath.read_text("utf-8"))
    usou_jev = False
    if not args.no_jev:
        ler_dotenv()
        api_key = __import__("os").environ.get("TYPESAFE_API_KEY")
        if api_key:
            pessoas_jev = pessoas[:args.max_pessoas]
            sessoes_jev = sessoes[:args.max_sessoes]
            cache = classificar_jev(pessoas_jev, sessoes_jev, cache,
                                    api_key, cpath)
            usou_jev = True
        else:
            print("sem TYPESAFE_API_KEY — relatório só com o scan")

    gerar_html(pessoas, sessoes, cache, ranking, args.out, usou_jev)
    return 0


if __name__ == "__main__":
    sys.exit(main())
