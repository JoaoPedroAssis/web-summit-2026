#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Triagem de pessoas com a Jev (TypeSafe System One).

Para cada pessoa da base (data/people.json + bios de data/raw/profiles/),
faz composite scoring com perguntas atômicas tipadas:

  afinidade       score 0-4  — trilhou o caminho que o João persegue?
  acessibilidade  score 0-4  — quão alcançável é a conversa (perfil par)?
  oportunidade    score 0-4  — pode contratar/indicar/abrir portas?
  synkrony        score 0-4  — vive o problema que o Synkrony resolve?
  gancho          choice     — melhor ângulo de abordagem

  alvo_valido     noul      — é alvo de networking (gating: imprensa,
                             moderador puro, político etc. saem do ranking)

O texto de tudo vem de perfil.md (linguagem natural, editável). Os pesos
das dimensões também estão em perfil.md e são aplicados na agregação —
mudar peso e re-agregar não consome API. A nota efetiva desconta a
confiança da Jev (nota × confiança); a crua fica visível ao lado.

Perguntas são agrupadas em lotes de pessoas por request (state comparti-
lhado; instruções referenciam `candidatos[i]`). Respostas ficam em cache
(data/triage_cache.json) e rerodar pula quem já foi avaliado.

Uso:
  python3 triage.py                # classifica quem falta (usa cache)
  python3 triage.py --limit 10     # só 10 pessoas (teste de sanidade)
  python3 triage.py --refazer      # descarta o cache e refaz tudo
  python3 triage.py --agregar      # só re-agrega com os pesos atuais
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
MODELS_URL = "https://api.typesafe.ai/v1/models"
MODEL = "jev-latest"
BATCH = 10        # pessoas por request
PAUSE = 0.3
BIO_MAX = 600     # caracteres de bio por pessoa no state
TALK_DESC_MAX = 220

# rubricas 0-4 (critérios ordenados; a posição define a nota)
RUBRICAS = {
    "afinidade": [
        "Nenhuma relação com growth para software, SaaS ou IA aplicada a times",
        "Área adjacente, mas sem relação direta com o caminho do João",
        "Trabalha em software/produto, mas sem histórico de growth ou fundação",
        "Fez parte do caminho que o João persegue (growth, SaaS, engenharia virando produto/comercial)",
        "Personificação do caminho: fundador de SaaS/software com growth, ou migração engenharia → growth/produto com sucesso",
    ],
    "acessibilidade": [
        "Inalcançável na prática: megacorporação, celebridade tech ou mídia de massa",
        "Muito difícil: executivo de grande empresa, tema frio, pouco em comum",
        "Possível: cargo relevante mas aberto a networking",
        "Fácil: perfil parecido com o do João (fundador em estágio inicial, IC sênior, profile parecido), conversa flui de par a par",
        "Porta aberta: founder early-stage ou speaker com história muito próxima da do João, alta chance de resposta e conversa real",
    ],
    "oportunidade": [
        "Nenhum potencial de abrir portas no setor",
        "Pouco: conexões limitadas ou área sem contratação relevante",
        "Moderado: pode indicar ou apresentar alguém",
        "Alto: decide ou influencia contratação em empresas com vagas remotas, ou tem rede forte",
        "Altíssimo: contrata diretamente, recruta ou move o mercado (partner de VC com portfólio contratando, exec com histórico de contratações remotas em dólar)",
    ],
    "synkrony": [
        "Nada a ver com o problema do Synkrony",
        "Relação fraca com gestão de times de software",
        "Convive com o problema, mas sem dor clara",
        "Vive o problema: gerencia times de software ou produtos de execução de projetos",
        "Cliente ideal: decide ferramentas de execução/IA para times de software, ou constrói produto concorrente/parceiro nesse espaço",
    ],
}

GANCHOS = {
    "trajetoria": "Trajetória parecida: migração de engenharia para growth/produto ou fundação de SaaS",
    "produto_ia": "Produto/IA: o trabalho da pessoa conecta com IA aplicada a times de software (tema do Synkrony)",
    "growth": "Growth/comercial: a pessoa tem expertise em growth marketing ou vendas de software",
    "carreira": "Carreira/oportunidade: a pessoa pode orientar sobre transição de carreira ou contratação",
    "conteudo": "Conteúdo da palestra: o tema da talk da pessoa é o melhor gancho de conversa",
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


def ler_perfil(path):
    """Retorna (texto integral do perfil.md, pesos)."""
    texto = Path(path).read_text("utf-8")
    m = re.search(r"```json\s*(\{.*?\})\s*```", texto, re.S)
    if not m:
        raise SystemExit("perfil.md sem bloco ```json``` de pesos")
    pesos = json.loads(m.group(1))
    soma = sum(pesos.values())
    if abs(soma - 1.0) > 1e-6:
        raise SystemExit("pesos de perfil.md somam {} (devem somar 1,0)"
                         .format(soma))
    return texto, pesos


def carregar_base(people_path, profiles_dir):
    people = json.loads(Path(people_path).read_text("utf-8"))
    out = []
    for p in people:
        f = Path(profiles_dir) / "{}.json".format(p["attendance_id"])
        bio, pitch, talks = "", "", []
        if f.exists():
            prof = json.loads(f.read_text("utf-8"))
            if not prof.get("missing"):
                det = prof.get("details") or {}
                bio = (det.get("bio") or "")[:BIO_MAX]
                pitch = (det.get("elevatorPitch") or "")[:200]
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
            "elevator_pitch": pitch,
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
        "elevator_pitch": p["elevator_pitch"],
        "palestras": p["talks"],
    } for i, p in enumerate(lote)]
    state = {
        "perfil_do_joao": perfil_texto,
        "candidatos": candidatos,
    }
    perguntas = {}
    for i in range(len(lote)):
        perguntas["p{}_alvo_valido".format(i + offset)] = {
            "type": "noul",
            "instructions": (
                "Com base no perfil do João e na seção de escopo, "
                "`candidatos[{}]` ({}) é um alvo legítimo de networking "
                "para ele — e não imprensa, moderador de painel, político, "
                "acadêmico sem ligação com software, artista ou empresa/"
                "robô? Responda true apenas se fizer sentido o João "
                "procurar essa pessoa no evento.".format(
                    i + offset, candidatos[i]["nome"])),
        }
        for dim, rubrica in RUBRICAS.items():
            perguntas["p{}_{}".format(i + offset, dim)] = {
                "type": "score",
                "instructions": (
                    "Avalie apenas o candidato `candidatos[{}]` ({}), "
                    "considerando o perfil do João no state.".format(
                        i + offset, candidatos[i]["nome"])),
                "criteria": rubrica,
            }
        perguntas["p{}_gancho".format(i + offset)] = {
            "type": "choice",
            "instructions": (
                "Qual o melhor ângulo de primeira abordagem para "
                "`candidatos[{}]` ({}) à luz do perfil do João?".format(
                    i + offset, candidatos[i]["nome"])),
            "criteria": GANCHOS,
        }
    return {"model": MODEL, "state": state, "questions": perguntas}


def classificar(perfil_texto, base, cache, api_key, pause):
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
            pessoa = {}
            for dim in list(RUBRICAS) + ["gancho", "alvo_valido"]:
                r = respostas.get("p{}_{}".format(base.index(p), dim))
                if r is None:
                    continue
                if r.get("type") == "score":
                    pessoa[dim] = {"score": r.get("score"),
                                   "confidence": r.get("confidence")}
                elif r.get("type") == "choice":
                    pessoa[dim] = {"choice": r.get("choice"),
                                   "confidence": r.get("confidence")}
                elif r.get("type") == "noul":
                    pessoa[dim] = {"probability": r.get("noul"),
                                   "confidence": None}
            cache[aid] = pessoa
        n = min(b + BATCH, len(faltam))
        print("  {}/{} pessoas (tokens in={} out={})".format(
            n, len(faltam), input_tokens, output_tokens))
        time.sleep(pause)
    return cache


def agregar(base, cache, pesos):
    """Score final ponderado (0-100) + ranking. Não consome API.

    Nota efetiva = nota crua × confiança da Jev naquela dimensão;
    quem falha no gating (alvo_valido < 0.5) vai para o fim, marcado."""
    ranqueados = []
    for p in base:
        a = cache.get(p["attendance_id"]) or {}
        brutos, efetivos, confs = {}, {}, {}
        for d in RUBRICAS:
            r = a.get(d) or {}
            brutos[d] = (r.get("score") or 0.0) * 25  # 0-4 -> 0-100
            confs[d] = r.get("confidence") or 0.0
            efetivos[d] = brutos[d] * confs[d]
        final = sum(efetivos[d] * pesos[d] for d in RUBRICAS)
        alvo = (a.get("alvo_valido") or {}).get("probability")
        no_escopo = True if alvo is None else alvo >= 0.5
        gancho_r = a.get("gancho") or {}
        ranqueados.append({
            "attendance_id": p["attendance_id"],
            "name": p["name"],
            "job_title": p["job_title"],
            "company_name": p["company_name"],
            "in_meetup": p["in_meetup"],
            "sessions": p.get("_sessoes", []),
            "score_final": round(final, 1),
            "dims": {d: round(v, 1) for d, v in efetivos.items()},
            "dims_brutos": {d: round(v, 1) for d, v in brutos.items()},
            "confidence_media": round(sum(confs.values()) / len(confs), 2),
            "no_escopo": not no_escopo,
            "prob_alvo_valido": alvo,
            "gancho": gancho_r.get("choice"),
            "gancho_confidence": gancho_r.get("confidence"),
            "bio": p["bio"],
            "elevator_pitch": p["elevator_pitch"],
            "talks": p["talks"],
        })
    # fora do escopo vai pro fim, sem disputar o topo
    ranqueados.sort(key=lambda r: (r["no_escopo"], -r["score_final"]))
    return ranqueados


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
                    help="só re-agrega o ranking com os pesos atuais")
    args = ap.parse_args()

    perfil_texto, pesos = ler_perfil(args.perfil)
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
        cache = classificar(perfil_texto, base, cache, api_key, PAUSE)
        cpath.write_text(json.dumps(cache, ensure_ascii=False), "utf-8")

    ranqueados = agregar(base, cache, pesos)
    Path(args.out).write_text(
        json.dumps({"pesos": pesos, "ranking": ranqueados},
                   ensure_ascii=False, indent=1), "utf-8")
    with Path(args.csv).open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["posicao", "score", "escopo", "name", "job_title",
                    "company", "afinidade", "acessibilidade",
                    "oportunidade", "synkrony", "confianca", "meetup",
                    "gancho"])
        for i, r in enumerate(ranqueados, 1):
            w.writerow([i, r["score_final"],
                        "fora" if r["no_escopo"] else "dentro",
                        r["name"], r["job_title"], r["company_name"]] +
                       [r["dims"][d] for d in RUBRICAS] +
                       [r["confidence_media"],
                        "sim" if r["in_meetup"] else "nao",
                        r["gancho"] or ""])
    print("ranking: {} pessoas -> {} e {}".format(
        len(ranqueados), args.out, args.csv))
    fora = sum(1 for r in ranqueados if r["no_escopo"])
    print("fora do escopo (gating): {}".format(fora))
    print("top 10 (no escopo):")
    for i, r in enumerate([x for x in ranqueados if not x["no_escopo"]][:10],
                          1):
        print("  {:2}. {:4.1f} (conf {:.2f})  {} — {} @ {} ({})".format(
            i, r["score_final"], r["confidence_media"], r["name"],
            r["job_title"] or "?", r["company_name"] or "?",
            r["gancho"] or "?"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
