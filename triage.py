#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Triagem de pessoas com a Jev (TypeSafe System One) — v2, por tipo de conexão.

Para cada pessoa da base (data/people.json + bios de data/raw/profiles/),
a Jev responde 4 perguntas atômicas:

  tipo        choice — par / referencia / porta / contexto
                     (pra que serve a conexão; ver perfil.md)
  prioridade  score 0-4 — quanto vale o esforço de procurar a pessoa
  gancho      choice — melhor ângulo de primeira abordagem
  alvo_valido noul — gating: imprensa, moderador puro, político etc.
                     saem das listas

Não há soma ponderada nem multiplicação por confiança: a prioridade bruta
ordena, e confiança baixa (< confianca_min do perfil.md) só marca a pessoa
para revisão manual. Saída: ranking geral + listas por tipo.

O texto de tudo vem de perfil.md. Respostas ficam em cache
(data/triage_cache.json) — gravado a cada lote, rerodar pula quem já foi
avaliado. O cache v1 (por dimensões) é incompatível; foi arquivado em
data/triage_cache_v1.json.

Uso:
  python3 triage.py                # classifica quem falta (usa cache)
  python3 triage.py --limit 10     # só 10 pessoas (teste de sanidade)
  python3 triage.py --refazer      # descarta o cache e refaz tudo
  python3 triage.py --agregar      # só re-agrega com a config atual
"""

import argparse
import csv
import json
import os
import random
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = None

API_URL = "https://api.typesafe.ai/v1/systemone"
MODELS_URL = "https://api.typesafe.ai/v1/models"
MODEL = "jev-latest"
BATCH = 10        # pessoas por request
PAUSE = 0.3
BIO_MAX = 600     # caracteres de bio por pessoa no state
TALK_DESC_MAX = 220

# tipos de conexão (choice; descrições viram critério da pergunta)
TIPOS = {
    "par": (
        "Trajetória parecida com a do João: engenharia → growth/produto, "
        "fundador em estágio inicial, construiu o próprio SaaS/software"),
    "referencia": (
        "Já fez com sucesso o caminho que o João quer trilhar, em escala "
        "maior (growth para software, founder que escalou/saiu, engenharia "
        "virando produto/comercial no topo) — gente para aprender com"),
    "porta": (
        "Pode gerar oportunidade de emprego de forma realista: hiring "
        "manager, founder contratando, recrutador, VC com portfólio "
        "contratando, ou pessoa em empresa que contrata remoto"),
    "contexto": (
        "Vale pelo conteúdo: IA aplicada a times de software, produto, "
        "execução de projetos — conversa técnica/produto flui, sem "
        "interesse comercial"),
}

# rubrica de prioridade 0-4 (a posição define a nota)
PRIORIDADE = [
    "Não vale o esforço: sem relação clara com os objetivos do João e "
    "difícil de acessar",
    "Vale pouco: algum interesse, mas a conversa provavelmente não rende "
    "nada concreto",
    "Vale: pessoa interessante, procurar se a ocasião aparecer",
    "Vale procurar de propósito: relação clara com os objetivos do João "
    "(em qualquer tipo) e conversa possível",
    "Prioridade máxima: par raro, porta quente ou referência direta do "
    "caminho dele — organizar o evento em volta dessa conversa",
]

GANCHOS = {
    "trajetoria": "Trajetória parecida: migração de engenharia para growth/produto ou fundação de SaaS",
    "growth": "Growth/comercial: a pessoa tem expertise em growth marketing ou vendas de software",
    "carreira": "Carreira/mercado: a pessoa pode orientar sobre transição de carreira ou contratação",
    "conteudo": "Conteúdo da palestra/tema: o tema da talk ou o trabalho da pessoa é o melhor gancho de conversa",
    "contratacao": "Times/vagas: a pessoa ou a empresa dela contrata — falar de times, mercado e oportunidades",
}


def http_post_json(url, payload, api_key):
    req = urllib.request.Request(
        url, method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        })
    with urllib.request.urlopen(req, timeout=120, context=SSL_CONTEXT) as r:
        return json.loads(r.read().decode("utf-8"))


def ler_dotenv(path=".env"):
    """Carrega KEY=VALUE de .env (sem sobrescrever o ambiente)."""
    f = Path(path)
    if not f.exists():
        return
    for line in f.read_text("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip("'\"")
        if k and k not in os.environ:
            os.environ[k] = v


def ler_perfil(path):
    """Retorna (texto integral do perfil.md, config)."""
    texto = Path(path).read_text("utf-8")
    m = re.search(r"```json\s*(\{.*?\})\s*```", texto, re.S)
    if not m:
        raise SystemExit("perfil.md sem bloco ```json``` de configuração")
    config = json.loads(m.group(1))
    config.setdefault("confianca_min", 0.5)
    config.setdefault("top_por_tipo", 15)
    return texto, config


def carregar_base(people_path, profiles_dir):
    people = json.loads(Path(people_path).read_text("utf-8"))
    out = []
    for p in people:
        f = Path(profiles_dir) / "{}.json".format(p["attendance_id"])
        bio, talks = "", []
        if f.exists():
            prof = json.loads(f.read_text("utf-8"))
            if not prof.get("missing"):
                det = prof.get("details") or {}
                bio = (det.get("bio") or "")[:BIO_MAX]
                for s in (prof.get("sessions") or [])[:3]:
                    talks.append("{}: {}".format(
                        s.get("title") or "",
                        (s.get("description") or "")[:TALK_DESC_MAX]))
        out.append({
            "attendance_id": p["attendance_id"],
            "name": p["name"],
            "job_title": p["job_title"],
            "company_name": p["company_name"],
            "tracks": p["tracks"],
            "in_meetup": p["in_meetup"],
            "bio": bio,
            "talks": talks,
        })
    return out


def montar_request(perfil_texto, lote, offset):
    """State com o perfil do João + o lote de candidatos; perguntas por
    pessoa referenciando `candidatos[i]`."""
    candidatos = [{
        "indice": i + offset,
        "nome": p["name"],
        "cargo": p["job_title"],
        "empresa": p["company_name"],
        "trilhas": p["tracks"],
        "participa_de_meetup": p["in_meetup"],
        "bio": p["bio"] or "sem bio disponível",
        "palestras": p["talks"],
    } for i, p in enumerate(lote)]
    state = {
        "perfil_do_joao": perfil_texto,
        "candidatos": candidatos,
    }
    perguntas = {}
    for i in range(len(lote)):
        k = i + offset
        perguntas["p{}_alvo_valido".format(k)] = {
            "type": "noul",
            "instructions": (
                "Com base no perfil do João e na seção de escopo, "
                "`candidatos[{}]` ({}) é um alvo legítimo de networking "
                "para ele — e não imprensa, moderador de painel, político, "
                "acadêmico sem ligação com software, artista ou empresa/"
                "robô? Responda true apenas se fizer sentido o João "
                "procurar essa pessoa no evento.".format(
                    k, candidatos[i]["nome"])),
        }
        perguntas["p{}_tipo".format(k)] = {
            "type": "choice",
            "instructions": (
                "Qual o tipo principal de conexão de `candidatos[{}]` ({}) "
                "com o João, à luz das definições no perfil dele? Escolha "
                "UM tipo. Se mais de um se aplicar, escolha o mais "
                "relevante para o objetivo dele.".format(
                    k, candidatos[i]["nome"])),
            "criteria": TIPOS,
        }
        perguntas["p{}_prioridade".format(k)] = {
            "type": "score",
            "instructions": (
                "Quanto vale o esforço do João procurar `candidatos[{}]` "
                "({}) no evento, considerando o tipo de conexão e a "
                "acessibilidade, conforme o perfil?".format(
                    k, candidatos[i]["nome"])),
            "criteria": PRIORIDADE,
        }
        perguntas["p{}_gancho".format(k)] = {
            "type": "choice",
            "instructions": (
                "Qual o melhor ângulo de primeira abordagem para "
                "`candidatos[{}]` ({}) à luz do perfil do João?".format(
                    k, candidatos[i]["nome"])),
            "criteria": GANCHOS,
        }
    return {"model": MODEL, "state": state, "questions": perguntas}


def classificar(perfil_texto, base, cache, api_key, pause, cpath):
    faltam = [p for p in base if p["attendance_id"] not in cache]
    print("a classificar: {} de {} (cache: {})".format(
        len(faltam), len(base), len(base) - len(faltam)))
    input_tokens = output_tokens = 0
    for b in range(0, len(faltam), BATCH):
        lote = faltam[b:b + BATCH]
        offset = base.index(lote[0])
        payload = montar_request(perfil_texto, lote, offset)
        for attempt in range(1, 4):
            try:
                resp = http_post_json(API_URL, payload, api_key)
                break
            except (urllib.error.HTTPError, urllib.error.URLError,
                    TimeoutError) as e:
                if attempt == 3:
                    raise SystemExit("falha na Jev: {}".format(e))
                print("  erro ({}, tentativa {})".format(e, attempt))
                time.sleep(3 * attempt)
        respostas = resp.get("answers") or {}
        uso = resp.get("usage") or {}
        input_tokens += uso.get("input_tokens") or 0
        output_tokens += uso.get("output_tokens") or 0
        for p in lote:
            aid = p["attendance_id"]
            k = base.index(p)
            pessoa = {}
            r = respostas.get("p{}_alvo_valido".format(k))
            if r is not None:
                pessoa["alvo_valido"] = {"probability": r.get("noul")}
            r = respostas.get("p{}_tipo".format(k))
            if r is not None:
                pessoa["tipo"] = {"choice": r.get("choice"),
                                  "confidence": r.get("confidence")}
            r = respostas.get("p{}_prioridade".format(k))
            if r is not None:
                pessoa["prioridade"] = {"score": r.get("score"),
                                        "confidence": r.get("confidence")}
            r = respostas.get("p{}_gancho".format(k))
            if r is not None:
                pessoa["gancho"] = {"choice": r.get("choice"),
                                    "confidence": r.get("confidence")}
            cache[aid] = pessoa
        # persiste a cada lote: crash no meio não perde o que já rodou
        cpath.write_text(json.dumps(cache, ensure_ascii=False), "utf-8")
        n = min(b + BATCH, len(faltam))
        print("  {}/{} pessoas (tokens in={} out={})".format(
            n, len(faltam), input_tokens, output_tokens))
        time.sleep(pause)
    return cache


def agregar(base, cache, config):
    """Ranking + listas por tipo. Não consome API.

    Prioridade bruta (0-4 → 0-100) ordena; confiança baixa marca para
    revisão manual em vez de penalizar a nota. Quem falha no gating
    (alvo_valido < 0.5) e quem ainda não foi avaliado vai para o fim."""
    conf_min = config["confianca_min"]
    top_por_tipo = config["top_por_tipo"]
    ranqueados = []
    for p in base:
        a = cache.get(p["attendance_id"]) or {}
        pr = (a.get("prioridade") or {})
        prioridade = pr.get("score")
        conf = pr.get("confidence")
        tipo_r = (a.get("tipo") or {})
        alvo = (a.get("alvo_valido") or {}).get("probability")
        if alvo is None:
            no_escopo = False
        else:
            no_escopo = alvo < 0.5
        avaliado = prioridade is not None
        ranqueados.append({
            "attendance_id": p["attendance_id"],
            "name": p["name"],
            "job_title": p["job_title"],
            "company_name": p["company_name"],
            "in_meetup": p["in_meetup"],
            "sessions": p.get("_sessoes", []),
            # 0-4 → 0-100, bruto (sem desconto por confiança)
            "prioridade": round((prioridade or 0.0) * 25, 1),
            "prioridade_crua": prioridade,
            "conf_prioridade": conf,
            "revisar": bool(avaliado and (conf is None or conf < conf_min)),
            "tipo": tipo_r.get("choice"),
            "tipo_confidence": tipo_r.get("confidence"),
            "no_escopo": no_escopo,
            "prob_alvo_valido": alvo,
            "avaliado": avaliado,
            "gancho": (a.get("gancho") or {}).get("choice"),
            "gancho_confidence": (a.get("gancho") or {}).get("confidence"),
            "bio": p["bio"],
            "talks": p["talks"],
        })
    # não avaliados por último, depois fora do escopo, depois prioridade
    ranqueados.sort(key=lambda r: (not r["avaliado"], r["no_escopo"],
                                   -r["prioridade"]))
    # listas por tipo (só dentro do escopo e avaliado)
    listas = {}
    for tipo in TIPOS:
        listas[tipo] = [r for r in ranqueados
                        if r["tipo"] == tipo and not r["no_escopo"]
                        and r["avaliado"]][:top_por_tipo]
    return ranqueados, listas


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--perfil", default="perfil.md")
    ap.add_argument("--people", default="data/people.json")
    ap.add_argument("--profiles", default="data/raw/profiles")
    ap.add_argument("--cache", default="data/triage_cache.json")
    ap.add_argument("--out", default="data/ranking.json")
    ap.add_argument("--csv", default="data/ranking.csv")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--amostra", type=int, default=0,
                    help="amostra estratificada: N com mais talks + N "
                         "aleatórias + arquetipos (founders conhecidos)")
    ap.add_argument("--refazer", action="store_true",
                    help="descarta o cache de respostas")
    ap.add_argument("--agregar", action="store_true",
                    help="só re-agrega o ranking com a config atual")
    args = ap.parse_args()

    perfil_texto, config = ler_perfil(args.perfil)
    base = carregar_base(args.people, args.profiles)
    cpath = Path(args.cache)
    cache = {} if args.refazer else (
        json.loads(cpath.read_text("utf-8"))
        if cpath.exists() else {})
    # sessões completas de people.json, para o roteiro
    people_by_id = {p["attendance_id"]: p
                    for p in json.loads(
                        Path(args.people).read_text("utf-8"))}
    for p in base:
        p["_sessoes"] = people_by_id[p["attendance_id"]]["sessions"]

    if args.amostra:
        # amostra estratificada: as primeiras da base tendem a ser
        # moderadores/imprensa (muitas talks); mistura com founders
        # conhecidos e gente com 1 talk só
        procurados = ["catasta", "abbas", "harbaugh", "brevik"]
        achados = [p for p in base
                   if any(s in p["name"].lower() for s in procurados)]
        resto = [p for p in base if p not in achados]
        com_mais = sorted(resto, key=lambda p: -len(p["_sessoes"]))
        com_mais = com_mais[:args.amostra]
        random.seed(42)
        pool = [p for p in resto if p not in com_mais]
        aleatorias = random.sample(pool, min(args.amostra, len(pool)))
        base = achados + com_mais + aleatorias

    if not args.agregar:
        ler_dotenv()
        api_key = os.environ.get("TYPESAFE_API_KEY")
        if not api_key:
            raise SystemExit("defina TYPESAFE_API_KEY no ambiente")
        if args.limit:
            base = base[:args.limit]
        cache = classificar(perfil_texto, base, cache, api_key, PAUSE,
                            cpath)

    ranqueados, listas = agregar(base, cache, config)
    Path(args.out).write_text(
        json.dumps({"config": config, "ranking": ranqueados,
                    "listas": listas},
                   ensure_ascii=False, indent=1), "utf-8")
    with Path(args.csv).open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["posicao", "prioridade", "escopo", "tipo",
                    "conf_prioridade", "revisar", "name", "job_title",
                    "company", "meetup", "gancho"])
        for i, r in enumerate(ranqueados, 1):
            w.writerow([
                i, r["prioridade"],
                "fora" if r["no_escopo"] else "dentro",
                r["tipo"] or "",
                r["conf_prioridade"] if r["conf_prioridade"] is not None
                else "",
                "sim" if r["revisar"] else "",
                r["name"], r["job_title"], r["company_name"],
                "sim" if r["in_meetup"] else "nao",
                r["gancho"] or "",
            ])
    print("ranking: {} pessoas -> {} e {}".format(
        len(ranqueados), args.out, args.csv))
    fora = sum(1 for r in ranqueados if r["no_escopo"])
    avaliados = sum(1 for r in ranqueados if r["avaliado"])
    revisar = sum(1 for r in ranqueados if r["revisar"])
    print("avaliados: {} | fora do escopo (gating): {} | para revisar "
          "(conf < {}): {}".format(avaliados, fora, config["confianca_min"],
                                   revisar))
    for tipo in TIPOS:
        top = listas[tipo]
        print("  {}: {} na lista (top {}): {}".format(
            tipo, len(top), config["top_por_tipo"],
            "; ".join("{} ({:.0f})".format(p["name"], p["prioridade"])
                      for p in top[:5]) or "—"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
