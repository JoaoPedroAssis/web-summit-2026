#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gera o relatório completo do evento em HTML autossuficiente:
data/relatorio.html

Seções:
  1. Resumo (hero numbers da run)
  2. As 4 listas de conexão (par / referencia / porta / contexto) com
     bio, onde encontrar e rascunho de mensagem por pessoa
  3. Roteiro por dia — palestras prioridade (com conflitos), meetups,
     conexões presentes no dia
  4. Analytics da run — distribuições de tipo, prioridade, confiança e
     gating; top sessões; tokens consumidos
  5. Metodologia e limitações (estabilidade, falsos positivos conhecidos)

Não consome API. Uso:
  python3 gera_relatorio.py [--log CAMINHO_DO_LOG_DA_RUN]
"""

import argparse
import html
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from roteiro import rascunho  # mesmo texto das mensagens do dossiê

DIAS = [
    ("2026-11-09", "Segunda 9/11"),
    ("2026-11-10", "Terça 10/11"),
    ("2026-11-11", "Quarta 11/11"),
    ("2026-11-12", "Quinta 12/11"),
]
TIPO_ROTULO = {
    "par": "Par — trajetória parecida",
    "referencia": "Referência — aprender com quem já fez",
    "porta": "Porta — pode gerar oportunidade",
    "contexto": "Contexto — conexão pelo conteúdo",
}
TIPO_COR = {"par": 1, "referencia": 2, "porta": 3, "contexto": 4}
GANCHO_ROTULO = {
    "trajetoria": "trajetória parecida",
    "growth": "growth/comercial",
    "carreira": "carreira/mercado",
    "conteudo": "conteúdo da palestra",
    "contratacao": "times e vagas",
}


def esc(s):
    return html.escape(str(s if s is not None else ""))


def hhmm(iso):
    return (iso or "")[11:16]


def sobrepoe(a, b):
    return a["starts_at"] < b["ends_at"] and b["starts_at"] < a["ends_at"]


# ---------------------------------------------------------------- SVG charts

def barra_h(valores, cor_var, largura=640, espaco_label=240, altura_barra=20,
            fmt="{:.0f}"):
    """Barras horizontais (magnitude, um tom). valores = [(label, v)]."""
    maxv = max((v for _, v in valores), default=1) or 1
    n = len(valores)
    h = n * (altura_barra + 10) + 6
    out = ['<svg viewBox="0 0 {} {}" class="chart" role="img">'.format(
        espaco_label + largura + 60, h)]
    for i, (label, v) in enumerate(valores):
        y = i * (altura_barra + 10) + 3
        w = max(2.0, (v / maxv) * largura)
        out.append(
            '<text x="{}" y="{}" class="clabel">{}</text>'.format(
                espaco_label - 8, y + altura_barra / 2 + 4, esc(label)))
        out.append(
            '<rect x="{}" y="{}" width="{:.1f}" height="{}" rx="4" '
            'class="bar" fill="var({})"><title>{}: {}</title></rect>'
            .format(espaco_label, y, w, altura_barra, cor_var,
                    esc(label), fmt.format(v)))
        out.append(
            '<text x="{}" y="{}" class="cval">{}</text>'.format(
                espaco_label + w + 8, y + altura_barra / 2 + 4,
                fmt.format(v)))
    out.append("</svg>")
    return "\n".join(out)


def histograma(bins, series, largura=640, altura=180):
    """Colunas. series = [(nome, cor_var, [contagens])] — 1 ou 2 séries
    agrupadas por bin; bins = [rótulo]."""
    n_bins = len(bins)
    n_s = len(series)
    margem = {"e": 36, "d": 12, "t": 10, "b": 24}
    pl = largura - margem["e"] - margem["d"]
    ph = altura - margem["t"] - margem["b"]
    maxv = max(max(cs) for _, _, cs in series) or 1
    grupo = pl / n_bins
    passo = min(24, max(6, int(grupo / (n_s + 0.8))))
    out = ['<svg viewBox="0 0 {} {}" class="chart" role="img">'.format(
        largura, altura)]
    for g in (0, maxv // 2, maxv):
        y = margem["t"] + ph - (g / maxv) * ph
        out.append('<line x1="{}" y1="{:.0f}" x2="{}" y2="{:.0f}" '
                   'class="grid"/>'.format(margem["e"], y,
                                           largura - margem["d"], y))
        out.append('<text x="{}" y="{:.0f}" class="tick" text-anchor="end">'
                   "{:.0f}</text>".format(margem["e"] - 5, y + 3, g))
    base = margem["t"] + ph
    out.append('<line x1="{}" y1="{}" x2="{}" y2="{}" class="axis"/>'.format(
        margem["e"], base, largura - margem["d"], base))
    for bi, blabel in enumerate(bins):
        x0 = margem["e"] + bi * grupo
        for si, (nome, cor, conts) in enumerate(series):
            v = conts[bi]
            if not v:
                continue
            w = passo
            x = x0 + (grupo - (n_s * (passo + 2))) / 2 + si * (passo + 2)
            h = max(1.5, (v / maxv) * ph)
            out.append(
                '<rect x="{:.1f}" y="{:.1f}" width="{}" height="{:.1f}" '
                'rx="2" class="bar" fill="var({})"><title>{} — {}: {}'
                "</title></rect>".format(
                    x, base - h, w, h, cor, esc(blabel), esc(nome), v))
        if n_bins <= 16 or bi % 2 == 0:
            out.append('<text x="{:.1f}" y="{}" class="tick" '
                       'text-anchor="middle">{}</text>'.format(
                           x0 + grupo / 2, altura - 8, esc(blabel)))
    if n_s > 1:
        lx = margem["e"]
        ly = 9
        for nome, cor, _ in series:
            out.append('<rect x="{}" y="{}" width="9" height="9" rx="2" '
                       'fill="var({})"/>'.format(lx, ly - 8, cor))
            out.append('<text x="{}" y="{}" class="tick">{}</text>'.format(
                lx + 13, ly, esc(nome)))
            lx += 13 + 7 * len(nome) + 18
    out.append("</svg>")
    return "\n".join(out)


def colunas_simples(valores, cor_var, largura=640, altura=170, fmt="{:.0f}"):
    """Colunas com rótulo direto (uma série, sem legenda)."""
    maxv = max((v for _, v in valores), default=1) or 1
    n = len(valores)
    out = ['<svg viewBox="0 0 {} {}" class="chart" role="img">'.format(
        largura, altura)]
    ph = altura - 40
    passo = largura / n
    bw = min(24, passo * 0.55)
    for i, (label, v) in enumerate(valores):
        h = max(2.0, (v / maxv) * (ph - 20))
        x = i * passo + (passo - bw) / 2
        y = ph - h
        out.append('<rect x="{:.1f}" y="{:.1f}" width="{:.1f}" '
                   'height="{:.1f}" rx="4" class="bar" fill="var({})">'
                   "<title>{}: {}</title></rect>".format(
                       x, y, bw, h, cor_var, esc(label), fmt.format(v)))
        out.append('<text x="{:.1f}" y="{:.1f}" class="cval" '
                   'text-anchor="middle">{}</text>'.format(
                       x + bw / 2, y - 5, fmt.format(v)))
        out.append('<text x="{:.1f}" y="{}" class="tick" '
                   'text-anchor="middle">{}</text>'.format(
                       x + bw / 2, altura - 8, esc(label)))
    return "\n".join(out) + "</svg>"


def tabela_dados(linha_header, linhas):
    out = ["<details><summary>ver dados</summary><table>",
           "<tr>{}</tr>".format(
               "".join("<th>{}</th>".format(esc(h)) for h in linha_header))]
    for l in linhas:
        out.append("<tr>{}</tr>".format(
            "".join("<td>{}</td>".format(esc(c)) for c in l)))
    out.append("</table></details>")
    return "\n".join(out)


# ------------------------------------------------------------------- seções

def card_pessoa(p, posicao):
    flags = []
    if p.get("revisar"):
        flags.append('<span class="flag">⚠ confiança baixa — revise à mão'
                     "</span>")
    if p.get("in_meetup"):
        flags.append('<span class="flag ok">participa de meetup</span>')
    onde = []
    for s in p.get("sessions") or []:
        onde.append("{}/{} {}h — {} ({})".format(
            s["date"][8:10], s["date"][5:7], hhmm(s["starts_at"]),
            esc(s["title"]), esc(s["location"] or "?")))
    bio = esc((p.get("bio") or "")[:220]) + ("…" if len(p.get("bio") or "")
                                             > 220 else "")
    talks = ""
    if p.get("talks"):
        t0 = esc(p["talks"][0].split(":")[0])
        talks = '<div class="talk">🗣 {}</div>'.format(t0)
    tipo = p.get("tipo") or "?"
    dot = '<span class="dot" style="background:var(--series-{});"></span>'\
        .format(TIPO_COR.get(tipo, 1))
    msg = esc(rascunho(p))
    return """
<article class="pessoa" data-busca="{busca}">
  <div class="p-topo">{dot}<strong>{pos}. {nome}</strong>
    <span class="score">{pri:.0f}</span></div>
  <div class="p-cargo">{cargo} @ {empresa}</div>
  <div class="p-meta">gancho: {gancho} · conf. {conf}{flag_html}</div>
  <div class="p-bio">{bio}</div>
  {talks}
  <details><summary>✉ rascunho de mensagem</summary>
    <blockquote>{msg}</blockquote>
    <div class="hint">Revise e personalize antes de enviar. Nunca envie sem ler.</div>
  </details>
  <details><summary>📍 onde encontrar</summary>
    <ul class="onde">{onde}</ul>
  </details>
</article>""".format(
        busca=esc("{} {} {}".format(p["name"], p["job_title"] or "",
                                    p["company_name"] or "").lower()),
        dot=dot, pos=posicao, nome=esc(p["name"]), pri=p["prioridade"],
        cargo=esc(p["job_title"] or "?"),
        empresa=esc(p["company_name"] or "?"),
        gancho=GANCHO_ROTULO.get(p.get("gancho") or "", "?"),
        conf="{:.2f}".format(p["conf_prioridade"]) if p.get("conf_prioridade")
             else "?",
        flag_html="".join('<div>{}</div>'.format(f) for f in flags),
        bio=bio, talks=talks, msg=msg,
        onde="".join("<li>{}</li>".format(o) for o in onde) or "<li>—</li>")


def secao_listas(listas):
    out = ['<section id="listas"><h2>2 · As quatro listas de conexão</h2>',
           '<p class="sub">Top {} de cada tipo, ordenado pela prioridade '
           "(0–100, bruta). Confiança baixa não penaliza a nota — só "
           "marca ⚠ para revisar à mão.</p>".format(15)]
    for tipo in TIPO_ROTULO:
        gente = listas.get(tipo) or []
        cor = TIPO_COR.get(tipo, 1)
        out.append('<h3><span class="dot" style="background:'
                   'var(--series-{})"></span> {} <span class="conta">({} '
                   "pessoas)</span></h3>".format(
                       cor, esc(TIPO_ROTULO[tipo]), len(gente)))
        if not gente:
            out.append("<p class='sub'>Ninguém caiu neste tipo na base "
                       "avaliada até agora.</p>")
        cards = "\n".join(card_pessoa(p, i + 1)
                          for i, p in enumerate(gente))
        out.append('<div class="grid-pessoas">{}</div>'.format(cards))
    out.append("</section>")
    return "\n".join(out)


def secao_roteiro(ranking, sessions):
    avaliados = [p for p in ranking if p["avaliado"]
                 and not p["no_escopo"] and p["prioridade"] > 0]
    top_by_id = {p["attendance_id"]: p for p in avaliados[:60]}
    out = ['<section id="roteiro"><h2>3 · Roteiro por dia</h2>']
    for dia, rotulo in DIAS:
        do_dia = [s for s in sessions if s["date"] == dia]
        if not do_dia:
            continue
        out.append("<h3>{}</h3>".format(rotulo))
        palestras = [s for s in do_dia if s["track"] != "Meetup"
                     and any(a in top_by_id for a in s["speaker_ids"])]
        palestras.sort(key=lambda s: (s["starts_at"],
                                      -sum(top_by_id[a]["prioridade"]
                                           for a in s["speaker_ids"]
                                           if a in top_by_id)))
        if palestras:
            out.append("<h4>Palestras com gente das minhas listas</h4>")
            out.append('<ul class="sessoes">')
            for s in palestras:
                gente = sorted(
                    (top_by_id[a] for a in s["speaker_ids"]
                     if a in top_by_id),
                    key=lambda p: -p["prioridade"])
                hi = sum(p["prioridade"] for p in gente)
                estrela = "★" if hi >= 120 else ("▸" if hi >= 60 else "·")
                conflitos = [o["title"] for o in palestras
                             if o["id"] != s["id"] and sobrepoe(s, o)]
                conf = ""
                if conflitos:
                    conf = (' <span class="flag">⚠ conflita: {}</span>'
                            .format(esc("; ".join(conflitos[:2]))))
                quem = ", ".join(
                    "{} ({:.0f}, {})".format(
                        esc(p["name"]), p["prioridade"], p["tipo"])
                    for p in gente[:4])
                out.append(
                    "<li><span class='est'>{}</span> <strong>{}–{}h</strong> "
                    "{} <span class='meta'>({},{})</span>{}"
                    "<div class='quem'>{}</div></li>".format(
                        estrela, hhmm(s["starts_at"]), hhmm(s["ends_at"]),
                        esc(s["title"]), esc(s["track"] or "sem trilha"),
                        esc(s["location"] or "?"), conf, quem))
            out.append("</ul>")
        meetups = [s for s in do_dia if s["track"] == "Meetup"]
        if meetups:
            out.append("<h4>Meetups do dia (maior canal de acesso)</h4>")
            out.append('<ul class="sessoes meetups">')
            for s in sorted(meetups, key=lambda x: x["starts_at"]):
                gente = [top_by_id[a]["name"] for a in s["speaker_ids"]
                         if a in top_by_id]
                extra = " — <em>com: {}</em>".format(
                    esc(", ".join(gente))) if gente else ""
                out.append("<li><strong>{}–{}h</strong> {} "
                           "<span class='meta'>({})</span>{}</li>".format(
                               hhmm(s["starts_at"]), hhmm(s["ends_at"]),
                               esc(s["title"]),
                               esc(s["location"] or "?"), extra))
            out.append("</ul>")
        conexoes = defaultdict(list)
        for p in avaliados[:60]:
            for s in p["sessions"]:
                if s["date"] == dia:
                    conexoes[p["attendance_id"]].append(s)
        if conexoes:
            out.append("<h4>Minhas conexões presentes no dia</h4>")
            out.append('<ul class="sessoes">')
            ordem = sorted(conexoes.items(),
                           key=lambda kv: -top_by_id[kv[0]]["prioridade"])
            for aid, sess in ordem:
                p = top_by_id[aid]
                talks = "; ".join("{}h {}".format(hhmm(s["starts_at"]),
                                                  esc(s["title"][:50]))
                                  for s in sess)
                out.append("<li><span class='dot' style='background:"
                           "var(--series-{});'></span> <strong>{}</strong> "
                           "({:.0f}, {}) — {} @ {} <div class='quem'>{}</div>"
                           "</li>".format(
                               TIPO_COR.get(p["tipo"], 1), esc(p["name"]),
                               p["prioridade"], p["tipo"],
                               esc(p["job_title"] or "?"),
                               esc(p["company_name"] or "?"), talks))
            out.append("</ul>")
    out.append("</section>")
    return "\n".join(out)


def secao_analytics(ranking, sessions, config, log_stats):
    dentro = [p for p in ranking if p["avaliado"] and not p["no_escopo"]]
    fora = [p for p in ranking if p["avaliado"] and p["no_escopo"]]
    nao_av = [p for p in ranking if not p["avaliado"]]
    tipos = Counter(p["tipo"] for p in dentro)

    out = ['<section id="analytics"><h2>4 · Analytics da run</h2>']

    # KPI row
    kpis = [
        ("Pessoas triadas", len(ranking)),
        ("Avaliadas", sum(1 for p in ranking if p["avaliado"])),
        ("Dentro do escopo", len(dentro)),
        ("Barradas pelo gating", len(fora)),
        ("Marcardas p/ revisar", sum(1 for p in ranking if p["revisar"])),
        ("Tokens (in/out)", log_stats.get("tokens_kpi", "—")),
    ]
    out.append('<div class="kpis">')
    for label, v in kpis:
        out.append('<div class="kpi"><div class="kpi-label">{}</div>'
                   '<div class="kpi-value">{}</div></div>'.format(
                       esc(label), esc(v)))
    out.append("</div>")

    # 1. pessoas por tipo (dentro) — categórica, cor segue o tipo
    out.append("<h3>Pessoas dentro do escopo, por tipo de conexão</h3>")
    vals = [(TIPO_ROTULO[t], tipos.get(t, 0)) for t in TIPO_ROTULO]
    out.append(barras_por_tipo(vals))
    out.append(tabela_dados(["tipo", "pessoas"],
                            [(TIPO_ROTULO[t], tipos.get(t, 0))
                             for t in TIPO_ROTULO]))

    # 2. histograma de prioridade (dentro) — magnitude, um tom
    bins = ["0–0.5", "0.5–1", "1–1.5", "1.5–2", "2–2.5", "2.5–3",
            "3–3.5", "3.5–4"]
    def bin_idx(x):
        return min(7, int(x / 0.5))
    cont = [0] * 8
    for p in dentro:
        cont[bin_idx(p["prioridade_crua"] or 0)] += 1
    out.append("<h3>Distribuição de prioridade (dentro do escopo)</h3>")
    out.append(histograma(bins, [("pessoas", "--seq-4", cont)]))
    out.append(tabela_dados(["faixa (0–4)", "pessoas"],
                            list(zip(bins, cont))))

    # 3. confiança da prioridade
    cbins = ["0–.1", ".1–.2", ".2–.3", ".3–.4", ".4–.5", ".5–.6",
             ".6–.7", ".7–.8", ".8–.9", ".9–1"]
    ccont = [0] * 10
    for p in ranking:
        c = p.get("conf_prioridade")
        if c is not None:
            ccont[min(9, int(c * 10))] += 1
    out.append("<h3>Confiança da Jev na nota de prioridade</h3>")
    out.append("<p class='sub'>Confiança &lt; {} → marcada ⚠ para revisão "
               "manual (não penaliza a nota).</p>".format(
                   config.get("confianca_min", 0.5)))
    out.append(histograma(cbins, [("pessoas", "--seq-4", ccont)]))
    out.append(tabela_dados(["faixa", "pessoas"], list(zip(cbins, ccont))))

    # 4. gating: probabilidade de alvo válido — dentro vs fora (2 séries)
    gbins = [".0", ".1", ".2", ".3", ".4", ".5", ".6", ".7", ".8", ".9"]
    g_d, g_f = [0] * 10, [0] * 10
    for p in ranking:
        q = p.get("prob_alvo_valido")
        if q is None:
            continue
        i = min(9, int(q * 10))
        if p["no_escopo"]:
            g_f[i] += 1
        else:
            g_d[i] += 1
    out.append("<h3>Gating: probabilidade de 'alvo válido de networking'"
               "</h3>")
    out.append("<p class='sub'>Corte em 0.5 — à esquerda os barrados, à "
               "direita os que entraram nas listas.</p>")
    out.append(histograma(gbins, [("dentro", "--series-1", g_d),
                                  ("fora", "--series-2", g_f)]))
    out.append(tabela_dados(
        ["faixa", "dentro", "fora"],
        [(gb, g_d[i], g_f[i]) for i, gb in enumerate(gbins)]))

    # 5. top sessões por prioridade agregada
    pmap = {p["attendance_id"]: p for p in dentro}
    scored = []
    for s in sessions:
        if s["track"] == "Meetup":
            continue
        gente = [pmap[a] for a in s["speaker_ids"] if a in pmap]
        if gente:
            scored.append((sum(p["prioridade"] for p in gente), s, gente))
    scored.sort(key=lambda t: -t[0])
    top_sess = scored[:12]
    out.append("<h3>As 12 melhores palestras (soma das prioridades de quem "
               "fala)</h3>")
    vals = [("{}h {}".format(hhmm(s["starts_at"]),
                             (s["title"] or "?")[:38]), tot)
            for tot, s, _ in top_sess]
    out.append(barra_h(vals, "--seq-4", largura=380, espaco_label=260))
    out.append(tabela_dados(
        ["palestra", "dia", "hora", "trilha", "quem", "soma"],
        [("{} {}h".format(s["title"], hhmm(s["starts_at"])),
          s["date"], hhmm(s["starts_at"]), s["track"] or "—",
          ", ".join(p["name"] for p in gente[:3]), "{:.0f}".format(tot))
         for tot, s, gente in top_sess]))

    # 6. conexões do top-60 por dia
    top60 = dentro[:60]
    por_dia = Counter()
    for p in top60:
        for s in p["sessions"]:
            por_dia[s["date"]] += 1
    out.append("<h3>Presença das minhas top-60 conexões por dia</h3>")
    out.append(colunas_simples(
        [(rot.split()[1], por_dia.get(d, 0)) for d, rot in DIAS],
        "--seq-4"))
    out.append(tabela_dados(["dia", "conexões"],
                            [(rot, por_dia.get(d, 0)) for d, rot in DIAS]))

    # 7. trilhas onde estão as conexões
    trilhas = Counter()
    for p in top60:
        for s in p["sessions"]:
            if s["track"] and s["track"] != "Meetup":
                trilhas[s["track"]] += 1
    top_tr = trilhas.most_common(8)
    out.append("<h3>Trilhas com mais conexões minhas (top 60)</h3>")
    out.append(barra_h([(t, n) for t, n in top_tr], "--seq-4",
                       largura=420, espaco_label=200))
    out.append(tabela_dados(["trilha", "sessões"],
                            [(t, n) for t, n in top_tr]))

    # 8. meetups
    out.append("<h3>Meetups</h3>")
    n_m = sum(1 for s in sessions if s["track"] == "Meetup")
    m_spk = sum(1 for s in sessions if s["track"] == "Meetup"
                and s["speaker_ids"])
    out.append("<p class='sub'>{} meetups no evento; só {} listam speakers "
               "na API pública — o cruzamento pessoa×meetup é limitado pela "
               "fonte de dados. Trate os meetups como canal aberto: apareça "
               "nos do seu dia.</p>".format(n_m, m_spk))
    if log_stats and "tokens" in log_stats:
        n_av_ = max(1, sum(1 for p in ranking if p["avaliado"]))
        ti = log_stats.get("_tokens_in", 0)
        out.append("<h3>Custo da run</h3>")
        out.append("<ul class='custo'>"
                   "<li>{}</li>"
                   "<li>média: {:,} tokens de entrada por pessoa</li>"
                   "<li>4 perguntas por pessoa (tipo, prioridade, gancho, "
                   "alvo válido); lotes de 10</li></ul>".format(
                       esc(log_stats["tokens"]),
                       round(ti / n_av_)))
    out.append("</section>")
    return "\n".join(out)


def barras_por_tipo(valores):
    """Barras horizontais com a cor da identidade de cada tipo
    (cor segue a entidade, ordem fixa)."""
    largura, espaco, alt = 420, 260, 20
    maxv = max((v for _, v in valores), default=1) or 1
    h = len(valores) * (alt + 10) + 6
    out = ['<svg viewBox="0 0 {} {}" class="chart" role="img">'.format(
        espaco + largura + 60, h)]
    for i, ((label, v), tipo) in enumerate(zip(valores, TIPO_ROTULO)):
        y = i * (alt + 10) + 3
        w = max(2.0, (v / maxv) * largura)
        cor = "--series-{}".format(TIPO_COR[tipo])
        out.append('<text x="{}" y="{}" class="clabel">{}</text>'.format(
            espaco - 8, y + alt / 2 + 4, esc(label)))
        out.append('<rect x="{}" y="{}" width="{:.1f}" height="{}" rx="4" '
                   'class="bar" fill="var({})"><title>{}: {}</title></rect>'
                   .format(espaco, y, w, alt, cor, esc(label), v))
        out.append('<text x="{}" y="{}" class="cval">{}</text>'.format(
            espaco + w + 8, y + alt / 2 + 4, v))
    out.append("</svg>")
    return "\n".join(out)


CSS = """
:root { color-scheme: light dark; }
body {
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  background: var(--page); color: var(--ink);
  margin: 0; padding: 2rem 1rem; line-height: 1.45;
}
:root { --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e;
  --muted:#898781; --grid:#e1e0d9; --axis:#c3c2b7; --ring:rgba(11,11,11,.10);
  --series-1:#2a78d6; --series-2:#eb6834; --series-3:#1baf7a;
  --series-4:#eda100; --seq-4:#3987e5; --flag-bg:#fdf3f2; --flag-tx:#8c2f2f;
  --ok-bg:#eef7ee; --ok-tx:#1d6b1d; }
@media (prefers-color-scheme: dark) { :root {
  --page:#0d0d0d; --surface:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7;
  --muted:#898781; --grid:#2c2c2a; --axis:#383835; --ring:rgba(255,255,255,.10);
  --series-1:#3987e5; --series-2:#d95926; --series-3:#199e70;
  --series-4:#c98500; --seq-4:#3987e5; --flag-bg:#2d1c1c; --flag-tx:#e8a5a5;
  --ok-bg:#182618; --ok-tx:#7fc47f; } }
main { max-width: 980px; margin: 0 auto; }
h1 { font-size: 1.7rem; margin: 0 0 .2rem; }
h2 { font-size: 1.3rem; margin-top: 3rem; border-bottom: 1px solid var(--grid);
  padding-bottom: .4rem; }
h3 { font-size: 1.05rem; margin-top: 2rem; }
h4 { font-size: .95rem; color: var(--ink2); margin-bottom: .4rem; }
.sub { color: var(--ink2); font-size: .9rem; }
.kpis { display: flex; flex-wrap: wrap; gap: .8rem; margin: 1.2rem 0; }
.kpi { background: var(--surface); border: 1px solid var(--ring);
  border-radius: 10px; padding: .7rem 1.1rem; min-width: 130px; }
.kpi-label { font-size: .75rem; color: var(--ink2); }
.kpi-value { font-size: 1.55rem; font-weight: 600; }
.grid-pessoas { display: grid; grid-template-columns: repeat(auto-fill,
  minmax(290px, 1fr)); gap: .9rem; }
.pessoa { background: var(--surface); border: 1px solid var(--ring);
  border-radius: 10px; padding: .85rem 1rem; font-size: .88rem; }
.p-topo { display: flex; align-items: center; gap: .45rem; }
.p-topo strong { flex: 1; }
.score { background: var(--page); border: 1px solid var(--ring);
  border-radius: 8px; padding: .05rem .5rem; font-weight: 600;
  font-variant-numeric: tabular-nums; }
.dot { display: inline-block; width: 10px; height: 10px;
  border-radius: 50%; flex: none; }
.p-cargo { color: var(--ink2); margin-top: .15rem; }
.p-meta { color: var(--muted); font-size: .78rem; margin-top: .25rem; }
.p-bio { color: var(--ink2); font-size: .82rem; margin-top: .45rem; }
.talk { font-size: .82rem; margin-top: .35rem; }
.flag { display: inline-block; background: var(--flag-bg);
  color: var(--flag-tx); border-radius: 6px; padding: .05rem .45rem;
  font-size: .74rem; margin-top: .3rem; }
.flag.ok { background: var(--ok-bg); color: var(--ok-tx); }
.pessoa details { margin-top: .5rem; }
.pessoa summary, details summary { cursor: pointer; color: var(--ink2);
  font-size: .8rem; }
blockquote { background: var(--page); border-left: 3px solid var(--axis);
  margin: .4rem 0; padding: .5rem .7rem; font-size: .82rem;
  border-radius: 0 8px 8px 0; }
.hint { color: var(--muted); font-size: .74rem; }
.onde { margin: .3rem 0; padding-left: 1.1rem; font-size: .8rem;
  color: var(--ink2); }
.sessoes { list-style: none; padding-left: 0; }
.sessoes li { padding: .45rem 0; border-bottom: 1px solid var(--grid); }
.est { color: var(--series-1); font-weight: 700; }
.meta { color: var(--muted); font-size: .8rem; }
.quem { color: var(--ink2); font-size: .8rem; margin-top: .15rem; }
.chart { width: 100%; height: auto; }
.chart .bar:hover { opacity: .82; }
.clabel { font-size: 12px; fill: var(--ink2); text-anchor: end; }
.cval { font-size: 11px; fill: var(--ink); font-weight: 600; }
.tick { font-size: 10.5px; fill: var(--muted); }
.grid { stroke: var(--grid); stroke-width: 1; }
.axis { stroke: var(--axis); stroke-width: 1; }
details table { border-collapse: collapse; font-size: .8rem; margin: .4rem 0; }
details th, details td { border: 1px solid var(--grid); padding: .2rem .5rem;
  text-align: left; }
#busca { width: 280px; padding: .45rem .7rem; border-radius: 8px;
  border: 1px solid var(--axis); background: var(--surface); color: var(--ink);
  font-size: .9rem; }
.toc { font-size: .9rem; background: var(--surface); border: 1px solid var(--ring);
  border-radius: 10px; padding: .8rem 1.2rem; margin: 1rem 0; }
.toc a { color: var(--ink2); text-decoration: none; margin-right: 1.2rem; }
.metodo { font-size: .88rem; color: var(--ink2); }
.metodo li { margin-bottom: .35rem; }
.custo { font-size: .9rem; color: var(--ink2); }
footer { margin-top: 3rem; color: var(--muted); font-size: .78rem; }
@media print {
  .pessoa, .kpi, .toc, blockquote, .sessoes li, details table { break-inside: avoid; }
  h2, h3, h4 { break-after: avoid; }
  details summary { display: block; }
  details > *:not(summary) { display: block; }
  a { color: inherit; text-decoration: none; }
}
"""


def secao_metodo(config, stats):
    return """
<section id="metodo"><h2>5 · Metodologia e limitações</h2>
<div class="metodo"><ul>
<li><strong>Motor:</strong> Jev (TypeSafe System One), pergunta atômica
tipada por pessoa: <em>tipo</em> (choice), <em>prioridade</em> (score 0–4
com rúbrica ancorada), <em>gancho</em> (choice) e <em>alvo_válido</em>
(gating). O texto de todo o critério vem do <code>perfil.md</code>.</li>
<li><strong>Nota:</strong> prioridade bruta ×25 — confiança <em>não</em>
penaliza a nota; abaixo de {conf_min} vira flag ⚠ de revisão manual.</li>
<li><strong>Gating:</strong> probabilidade de alvo válido &lt; 0.5 tira a
pessoa das listas (imprensa, moderadores, políticos etc.). Como o gating
da Jev deixou passar imprensa no sample (editor da Fortune) e no run full
(âncora da CNN), existe um <strong>backstop determinístico</strong>: cargo
ou veículo de imprensa (regex de cargos editoriais + empresas de mídia,
com exceção para braços de investimento tipo Ventures) sai do escopo por
regra — barrou 163 pessoas nesta run.</li>
<li><strong>Estabilidade medida:</strong> 6 pessoas re-classificadas em 3
rodadas independentes — tipo idêntico em 6/6; prioridade variou no máximo
0.10 na escala 0–4.</li>
<li><strong>Falsos positivos conhecidos na amostra:</strong> 2 pessoas
entraram no escopo indevidamente (um editor de imprensa como "porta" e um
professor como "porta"). A lista de <em>portas</em> é curta e deve ser
revisada à mão por você — é o filtro do seu objetivo de emprego.</li>
<li><strong>Limitações dos dados:</strong> teto da API contornado por
subdivisão por trilha (~11 sessões sem trilha ficam fora); dias 10 e 11
podem ter até ~7 sessões não capturadas; coleta feita em 27/10 — a
programação pode ter mudado até o evento; 50 das 841 pessoas não têm
página pública (sem bio). Meetups raramente listam speakers na API.</li>
<li><strong>Privacidade:</strong> dados públicos de speakers, uso
exclusivamente pessoal de networking. Não redistribuir.</li>
</ul></div>
</section>""".format(conf_min=esc(config.get("confianca_min", 0.5)))


def parse_log(caminho):
    stats = {}
    if not caminho:
        return stats
    try:
        txt = Path(caminho).read_text("utf-8", errors="ignore")
    except OSError:
        return stats
    tot = re.findall(r"tokens in=(\d+) out=(\d+)", txt)
    if tot:
        ti, to = int(tot[-1][0]), int(tot[-1][1])
        stats["_tokens_in"] = ti
        stats["tokens"] = "tokens: {:,} de entrada / {:,} de saída".format(
            ti, to).replace(",", ".")
        stats["tokens_kpi"] = "{:.0f}k/{:.0f}k".format(ti / 1000, to / 1000)
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ranking", default="data/ranking.json")
    ap.add_argument("--sessions", default="data/sessions.json")
    ap.add_argument("--out", default="data/relatorio.html")
    ap.add_argument("--log", default="",
                    help="log da run (para analytics de tokens)")
    args = ap.parse_args()

    data = json.loads(Path(args.ranking).read_text("utf-8"))
    ranking, listas, config = data["ranking"], data["listas"], data["config"]
    sessions = json.loads(Path(args.sessions).read_text("utf-8"))
    log_stats = parse_log(args.log)

    n_av = sum(1 for p in ranking if p["avaliado"])
    n_in = sum(1 for p in ranking if p["avaliado"] and not p["no_escopo"])

    doc = []
    doc.append("<!doctype html><html lang='pt-BR'><head>"
               "<meta charset='utf-8'>"
               "<meta name='viewport' content='width=device-width, "
               "initial-scale=1'>"
               "<title>Web Summit 2026 — relatório de networking</title>"
               "<style>{}</style></head><body><main>".format(CSS))
    doc.append(
        "<h1>Web Summit Lisboa 2026 — relatório de networking</h1>"
        "<p class='sub'>Run completa: {} pessoas triadas, {} avaliadas, "
        "{} dentro do escopo. Gerado em 08/11/2026 a partir dos dados "
        "públicos do evento.</p>".format(len(ranking), n_av, n_in))
    doc.append("<nav class='toc'><a href='#listas'>As 4 listas</a>"
               "<a href='#roteiro'>Roteiro por dia</a>"
               "<a href='#analytics'>Analytics da run</a>"
               "<a href='#metodo'>Metodologia</a></nav>")
    doc.append("<input id='busca' type='search' "
               "placeholder='Filtrar pessoas por nome, cargo, empresa…'>"
               "<p class='sub'>O filtro vale para os cards das listas "
               "abaixo.</p>")

    doc.append(secao_listas(listas))
    doc.append(secao_roteiro(ranking, sessions))
    doc.append(secao_analytics(ranking, sessions, config, log_stats))
    doc.append(secao_metodo(config, log_stats))
    doc.append("<footer>Gerado por gera_relatorio.py — pipeline pessoal "
               "de networking. Rascunhos de mensagem: revise sempre antes "
               "de enviar.</footer>")
    doc.append("</main><script>"
               "document.getElementById('busca').addEventListener('input',"
               "function(){var q=this.value.toLowerCase();"
               "document.querySelectorAll('.pessoa').forEach(function(el){"
               "el.style.display=el.dataset.busca.indexOf(q)>-1?'':'none';"
               "});});</script></body></html>")

    Path(args.out).write_text("\n".join(doc), "utf-8")
    print("relatório: {} ({} bytes)".format(args.out,
                                            Path(args.out).stat().st_size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
