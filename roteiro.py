#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gera os entregáveis para o app do Web Summit a partir do ranking:

  data/roteiro.md — plano por dia: palestras para marcar presença
                    (com conflitos de horário), meetups e conexões
                    prioridade do dia.
  data/dossie.md  — dossiê do top N com rascunho de mensagem (em
                    inglês) para revisar e enviar no app.

Não consome API — só lê ranking.json e sessions.json. Rode de novo
depois de mudar a config/re-agregar para atualizar os entregáveis.

Uso:
  python3 roteiro.py               # top 50
  python3 roteiro.py --top 30
"""

import argparse
import json
import sys
from pathlib import Path

DIAS = {
    "2026-11-09": "seg 9/11",
    "2026-11-10": "ter 10/11",
    "2026-11-11": "qua 11/11",
    "2026-11-12": "qui 12/11",
}
TIPO_ROTULO = {
    "par": "Par (trajetória parecida)",
    "referencia": "Referência (aprender com quem já fez)",
    "porta": "Porta (pode gerar oportunidade)",
    "contexto": "Contexto (conexão pelo conteúdo)",
}
# mensagens neutras: identidade, nunca pitch de produto
GANCHO_FRASE = {
    "trajetoria": (
        "our paths look surprisingly similar — I started in engineering "
        "and moved into commercial/growth while building my own SaaS"),
    "growth": (
        "I'm deep into growth for my own SaaS and would love to trade "
        "notes on {talk_topic}"),
    "carreira": (
        "I'm a founder exploring my next step and your perspective on "
        "{talk_topic} resonated with where I am"),
    "conteudo": (
        "your session '{talk_title}' is exactly why I'm coming to Lisbon"),
    "contratacao": (
        "I'm exploring what's next for me and the work your team does "
        "caught my eye — would love to hear how you think about "
        "{talk_topic}"),
}


def hhmm(iso):
    return (iso or "")[11:16]


def sobrepoe(a, b):
    return a["starts_at"] < b["ends_at"] and b["starts_at"] < a["ends_at"]


def prioridade_sessao(sess, top_by_id):
    """Soma das prioridades das pessoas do top que participam."""
    return sum(top_by_id[a]["prioridade"] for a in sess["speaker_ids"]
               if a in top_by_id)


def nomes_top(sess, top_by_id, limite=4):
    pessoas = [top_by_id[a] for a in sess["speaker_ids"]
               if a in top_by_id]
    pessoas.sort(key=lambda p: -p["prioridade"])
    return pessoas[:limite]


def montar_roteiro(ranking, sessions, top_n):
    top = [p for p in ranking[:top_n] if p["avaliado"]
           and not p["no_escopo"]]
    top_by_id = {p["attendance_id"]: p for p in top}
    linhas = ["# Roteiro — Web Summit Lisboa 2026",
              "",
              "Gerado a partir do ranking (top {}). Marcar presença nas"
              .format(top_n),
              "palestras ★ e conectar com as pessoas listadas.",
              ""]
    for dia, rotulo in DIAS.items():
        do_dia = [s for s in sessions if s["date"] == dia]
        if not do_dia:
            continue
        linhas += ["## {}".format(rotulo), ""]
        palestras = [s for s in do_dia if s["track"] != "Meetup"
                     and prioridade_sessao(s, top_by_id) > 0]
        palestras.sort(key=lambda s: (s["starts_at"],
                                      -prioridade_sessao(s, top_by_id)))
        if palestras:
            linhas += ["### Palestras com gente do top (marcar presença)",
                       ""]
            for s in palestras:
                hi = prioridade_sessao(s, top_by_id)
                estrela = "★" if hi >= 100 else (" " if hi >= 50 else "·")
                gente = ", ".join(
                    "{} ({:.0f})".format(p["name"], p["prioridade"])
                    for p in nomes_top(s, top_by_id))
                conflitos = [o["title"] for o in palestras
                             if o["id"] != s["id"] and sobrepoe(s, o)]
                conflito = " ⚠ conflita: " + "; ".join(
                    conflitos[:2]) if conflitos else ""
                linhas.append(
                    "- {} **{} {}** — {} ({}, {}){}".format(
                        estrela, hhmm(s["starts_at"]),
                        hhmm(s["ends_at"]), s["title"],
                        s["location"] or "?", s["track"] or "sem trilha",
                        conflito))
                linhas.append("  - {}".format(gente))
            linhas.append("")
        meetups = [s for s in do_dia if s["track"] == "Meetup"]
        if meetups:
            linhas += ["### Meetups do dia (canal de maior acesso)", ""]
            for s in sorted(meetups, key=lambda x: x["starts_at"]):
                linhas.append("- {} {} — {} ({})".format(
                    hhmm(s["starts_at"]), hhmm(s["ends_at"]), s["title"],
                    s["location"] or "?"))
            linhas.append("")
        conexoes = {}
        for p in top:
            for s in p["sessions"]:
                if s["date"] == dia:
                    conexoes.setdefault(p["attendance_id"], p)
        if conexoes:
            linhas += ["### Conexões prioridade presentes no dia", ""]
            for p in sorted(conexoes.values(),
                            key=lambda x: -x["prioridade"]):
                talks = ", ".join(
                    "{} {}".format(hhmm(t["starts_at"]), t["title"][:40])
                    for t in p["sessions"] if t["date"] == dia)
                linhas.append("- **{}** ({:.0f}, {}) — {} @ {} — {}".format(
                    p["name"], p["prioridade"], p["tipo"] or "?",
                    p["job_title"] or "?",
                    p["company_name"] or "?", talks))
            linhas.append("")
    return "\n".join(linhas)


def rascunho(p):
    gancho = p.get("gancho") or "conteudo"
    talk = (p.get("talks") or [""])[0]
    talk_title = talk.split(":")[0].strip() if talk else "your talk"
    talk_topic = talk_title.lower()
    corpo = GANCHO_FRASE.get(gancho, GANCHO_FRASE["conteudo"]).format(
        talk_topic=talk_topic, talk_title=talk_title)
    return ("Hi {nome}, I'll be at Web Summit in Lisbon and wanted to "
            "reach out before the rush. {corpo}. "
            "Would be great to grab a coffee between sessions — I'd "
            "love to hear how you think about {talk_topic}. "
            "Either way, enjoy the event!").format(
                nome=p["name"].split()[0], corpo=corpo,
                talk_topic=talk_topic)


def montar_dossie(ranking, top_n):
    avaliados = [p for p in ranking if p["avaliado"]
                 and not p["no_escopo"]]
    linhas = ["# Dossiê — top {} para contato prévio".format(top_n), "",
              "> Rascunhos gerados automaticamente: revise e personalize",
              "> antes de enviar no app. Nunca envie sem ler.", ""]
    # resumo por tipo de conexão
    por_tipo = {}
    for p in avaliados:
        por_tipo.setdefault(p["tipo"] or "?", []).append(p)
    linhas += ["## Resumo por tipo de conexão", ""]
    for tipo, rotulo in TIPO_ROTULO.items():
        gente = por_tipo.get(tipo, [])
        if gente:
            linhas.append("- **{}**: {}".format(
                rotulo,
                "; ".join("{} ({:.0f}{})".format(
                    p["name"], p["prioridade"],
                    " ⚠revisar" if p["revisar"] else "")
                    for p in gente[:10])))
    linhas.append("")
    for i, p in enumerate(avaliados[:top_n], 1):
        linhas += ["## {}. {} — {:.0f}/100 — {}".format(
            i, p["name"], p["prioridade"],
            TIPO_ROTULO.get(p["tipo"], p["tipo"] or "?")), ""]
        flags = []
        if p["revisar"]:
            flags.append("⚠ confiança baixa — revisar à mão")
        if p["in_meetup"]:
            flags.append("participa de meetup")
        if flags:
            linhas += ["*" + "; ".join(flags) + "*", ""]
        linhas.append("**{} @ {}** | prioridade {:.0f} (conf {}) | "
                      "gancho: {}".format(
                          p["job_title"] or "?",
                          p["company_name"] or "?",
                          p["prioridade"],
                          p["conf_prioridade"] or "?",
                          p["gancho"] or "?"))
        if p.get("bio"):
            linhas += ["", p["bio"]]
        if p.get("talks"):
            linhas += ["", "**Palestras:**"]
            for t in p["talks"]:
                linhas.append("- {}".format(t[:400]))
        if p.get("sessions"):
            linhas += ["", "**Onde encontrar:**"]
            for s in p["sessions"]:
                linhas.append("- {}/{} {}h — {} ({}, {})".format(
                    s["date"][8:10], s["date"][5:7],
                    hhmm(s["starts_at"]), s["title"],
                    s["location"] or "?", s["track"] or "sem trilha"))
        linhas += ["", "**Rascunho de mensagem:**", "",
                   "> " + rascunho(p), ""]
    return "\n".join(linhas)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ranking", default="data/ranking.json")
    ap.add_argument("--sessions", default="data/sessions.json")
    ap.add_argument("--top", type=int, default=50)
    args = ap.parse_args()

    ranking = json.loads(Path(args.ranking).read_text("utf-8"))["ranking"]
    sessions = json.loads(Path(args.sessions).read_text("utf-8"))

    roteiro = montar_roteiro(ranking, sessions, args.top)
    Path("data").mkdir(parents=True, exist_ok=True)
    Path("data/roteiro.md").write_text(roteiro, "utf-8")
    dossie = montar_dossie(ranking, args.top)
    Path("data/dossie.md").write_text(dossie, "utf-8")
    print("roteiro: data/roteiro.md | dossie: data/dossie.md "
          "(top {})".format(args.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
