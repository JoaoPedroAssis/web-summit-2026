#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coleta a programação do Web Summit Lisboa 2026 via API pública.

Estratégia:
  1. Para cada dia, varredura sem filtro. Teto da API: 32 páginas
     (~224 sessões/consulta; page=33+ responde 404).
  2. Se o dia bater no teto, re-consulta subdividindo por trilha via
     `filters` (base64 de JSON). Chave e valores extraídos da config
     oficial de filtros embutida no HTML de /schedule/ (27/10/2026) e
     validados contra a API: resposta vazia ou heterogênea -> erro.
  3. Cada resposta vai crua para data/raw/, um arquivo por página.
     Rerodar pula o que já foi baixado (resume).

Uso:
  python3 fetch.py                # dias 9-12, com subdivisão se precisar
  python3 fetch.py --days 10      # só 10/11
  python3 fetch.py --no-subdivide # só varredura sem filtro
"""

import argparse
import base64
import json
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = None  # usa os certificados padrão do sistema

API_URL = "https://websummit.com/api/list-items/"
TYPENAME = "DefaultTemplate_Custompage_FlexibleContent_ScheduleList"
TIMEZONE = "Europe/Lisbon"
MAX_PAGES = 32  # page=33+ responde 404 (verificado em 27/10/2026)
PAUSE = 0.4     # segundos entre requests
HTTP_TIMEOUT = 30
RETRIES = 3
TRACK_FILTER_KEY = "schedule_track.name"  # config oficial de /schedule/

# Valores exatos da config de filtros embutida no HTML de /schedule/
# (27/10/2026). Valor errado -> API responde lista vazia, sem erro.
TRACKS = [
    "AI Summit", "Centre Stage", "Commerce Summit",
    "Corporate Innovation Summit", "Creative Summit", "Cybersecurity Summit",
    "Developer Summit", "Energy Summit", "Future of Work Summit",
    "Growth Summit", "Health Summit", "Investor Masterclass",
    "Marketing Summit", "Masterclasses", "Meetup", "MoneyConf",
    "New Media Summit", "Night Summit", "Policy Summit", "Press conference",
    "SaaS Summit", "Sport Summit", "Startup Masterclass", "Venture Summit",
    "Women in tech",
]


class FilterError(RuntimeError):
    """A API não reconheceu o filtro ou o ignorou."""


def http_get_text(url):
    """GET com retries. Retorna o corpo texto, ou None se 404."""
    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "personal-schedule-fetcher/0.2",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT,
                                        context=SSL_CONTEXT) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            last_err = e
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
        time.sleep(2 ** attempt)  # backoff: 2s, 4s
    raise RuntimeError("falha apos {} tentativas: {}: {}".format(
        RETRIES, url, last_err))


def parse_payload(text):
    data = (json.loads(text) or {}).get("data") or {}
    return data.get("listItems") or [], data


def build_url(date, page, track=None):
    params = {
        "slug": "schedule",
        "typename": TYPENAME,
        "page": str(page),
        "date": date,
        "timezone": TIMEZONE,
    }
    if track is not None:
        payload = json.dumps({TRACK_FILTER_KEY: track},
                             separators=(",", ":"))
        params["filters"] = base64.b64encode(
            payload.encode("utf-8")).decode("ascii")
    return API_URL + "?" + urllib.parse.urlencode(params)


def track_of(item):
    return ((item.get("schedule_track") or {}).get("name") or "").strip()


def fetch_query(date, track, outdir, pause):
    """Baixa todas as páginas de uma consulta (dia × trilha opcional).
    Guarda cada página crua e pula as que já existem."""
    subdir = "" if track is None else "track--" + track.lower().replace(" ", "-").replace("/", "-")
    pagedir = outdir / date / subdir if subdir else outdir / date
    page, nb_pages, items_all = 1, None, []
    while True:
        f = pagedir / "page-{:03d}.json".format(page)
        if f.exists():
            text = f.read_text("utf-8")
        else:
            text = http_get_text(build_url(date, page, track))
            time.sleep(pause)
            if text is None:
                break  # 404: não há mais páginas
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text, "utf-8")
        items, data = parse_payload(text)
        if nb_pages is None:
            nb_pages = int(data.get("nbPages") or 0)
        items_all.extend(items)
        if page >= min(nb_pages, MAX_PAGES) or not items:
            break
        page += 1
    return {"query": track or "unfiltered", "captured": len(items_all),
            "nb_pages": nb_pages or 0, "truncated": (nb_pages or 0) > MAX_PAGES}


def validate_filter(date, probe_track, pause):
    """Uma trilha que existe no dia precisa voltar populada e homogênea.
    Valor/chave errados -> lista vazia; filtro ignorado -> trilhas estranhas."""
    text = http_get_text(build_url(date, 1, probe_track))
    time.sleep(pause)
    items, _ = parse_payload(text or "null")
    if not items:
        raise FilterError(
            "resposta vazia para a trilha {!r} no dia {} — filtro não "
            "reconhecido".format(probe_track, date))
    estranhas = sorted({track_of(i) for i in items
                        if track_of(i) and track_of(i) != probe_track})
    if estranhas:
        raise FilterError("filtro ignorado (voltaram trilhas {})".format(
            ", ".join(estranhas[:5])))


def collect_day(date, outdir, pause, no_subdivide=False):
    print("== {} ==".format(date))
    un = fetch_query(date, None, outdir, pause)
    print("  sem filtro: {} sessões (nbPages={}, {})".format(
        un["captured"], un["nb_pages"],
        "TRUNCADO no teto de {} páginas".format(MAX_PAGES)
        if un["truncated"] else "completo"))

    results = {"unfiltered": un, "tracks": {}}
    if un["truncated"] and not no_subdivide:
        validate_filter(date, "Meetup", pause)
        for t in TRACKS:
            r = fetch_query(date, t, outdir, pause)
            results["tracks"][t] = r
            if r["truncated"]:
                print("  AVISO: trilha {!r} com nbPages={} > teto; "
                      "sessões vão faltar.".format(t, r["nb_pages"]))
        total_tracks = sum(r["captured"] for r in results["tracks"].values())
        print("  por trilha: {} sessões em {} trilhas "
              "(nbPages máx: {})".format(
                  total_tracks, len(results["tracks"]),
                  max(r["nb_pages"] for r in results["tracks"].values())))

    # dedupe de IDs: varredura sem filtro + partições por trilha
    ids = set()
    for d in sorted((outdir / date).rglob("page-*.json")):
        for it in parse_payload(d.read_text("utf-8"))[0]:
            if it.get("id") is not None:
                ids.add(it["id"])
    print("  total único de sessões no dia: {}".format(len(ids)))
    return {"date": date, "unique_sessions": len(ids), "results": results}


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", default="9,10,11,12",
                    help="dias do evento, ex.: 10 ou 9,11")
    ap.add_argument("--out", default="data/raw/schedule",
                    help="diretório de saída (arquivos crus)")
    ap.add_argument("--pause", type=float, default=PAUSE)
    ap.add_argument("--no-subdivide", action="store_true",
                    help="pula a subdivisão por trilha")
    args = ap.parse_args()

    days = ["2026-11-{:02d}".format(int(d)) for d in args.days.split(",")]
    outdir = Path(args.out)

    for date in days:
        summary = collect_day(date, outdir, args.pause, args.no_subdivide)
        mpath = outdir / date / "manifest.json"
        mpath.parent.mkdir(parents=True, exist_ok=True)
        mpath.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                         "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
