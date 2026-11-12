#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Baixa os perfis públicos dos speakers (bio, elevator pitch e descrição
das talks) para cada pessoa da base consolidada.

Para cada attendance_id em data/people.json, busca
`https://websummit.com/attendees/lis26/<attendance_id>/` (funciona sem
slug; slug errado dá 404), extrai o JSON embutido `__NEXT_DATA__` e
salva só o que interessa em data/raw/profiles/<attendance_id>.json.
404 = perfil não existe (pessoa sem página pública); é registrado e
pulado. Rerodar pula o que já foi baixado (resume).

Uso:
  python3 fetch_profiles.py                 # base toda
  python3 fetch_profiles.py --limit 10      # amostra
"""

import argparse
import json
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

PROFILE_URL = "https://websummit.com/attendees/lis26/{}/"
PAUSE = 0.4
HTTP_TIMEOUT = 30
RETRIES = 3
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.S)


def http_get(url):
    """GET com retries. Retorna o corpo texto, ou None se 404."""
    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (personal-profile-fetcher/0.1)",
                "Accept": "text/html",
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
        time.sleep(2 ** attempt)
    raise RuntimeError("falha apos {} tentativas: {}: {}".format(
        RETRIES, url, last_err))


def extract_profile(html):
    """Tira de __NEXT_DATA__ o que importa: details (bio etc.) e sessões."""
    m = NEXT_DATA_RE.search(html)
    if not m:
        return None
    data = (json.loads(m.group(1)) or {}).get("props", {}) \
        .get("pageProps", {}).get("data", {})
    page = (data.get("page") or {})
    blocks = ((page.get("template") or {}).get("customPage") or {})
    blocks = blocks.get("attendeeDetailsTemplate") or []
    details, sessions = {}, []
    for b in blocks:
        typename = b.get("__typename") or ""
        if typename.endswith("_Profile"):
            details = b.get("details") or {}
        elif typename.endswith("_Schedule"):
            sessions = b.get("sessions") or []
    keep_details = {k: details.get(k) for k in (
        "bio", "elevatorPitch", "jobTitle", "company", "companyURL",
        "country", "industry", "hashtags", "role", "featuredSpeaker")}
    keep_sessions = [{
        "id": s.get("id"),
        "title": s.get("title"),
        "description": s.get("description"),
        "date": (s.get("starts_at") or "")[:10],
        "starts_at": s.get("starts_at"),
        "track": ((s.get("schedule_track") or {}).get("name") or ""),
    } for s in sessions]
    return {"details": keep_details, "sessions": keep_sessions,
            "meta_desc": ((page.get("seo") or {}).get("metaDesc") or "")}


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--people", default="data/people.json")
    ap.add_argument("--out", default="data/raw/profiles")
    ap.add_argument("--pause", type=float, default=PAUSE)
    ap.add_argument("--limit", type=int, default=0,
                    help="processa só as N primeiras (teste)")
    args = ap.parse_args()

    people = json.loads(Path(args.people).read_text("utf-8"))
    if args.limit:
        people = people[:args.limit]
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    ok, missing, errors = 0, 0, 0
    for i, p in enumerate(people, 1):
        f = outdir / "{}.json".format(p["attendance_id"])
        if f.exists():
            ok += 1
            continue
        try:
            html = http_get(PROFILE_URL.format(p["attendance_id"]))
        except RuntimeError as e:
            print("ERRO {}: {}".format(p["name"], e))
            errors += 1
            continue
        time.sleep(args.pause)
        if html is None:
            f.write_text(json.dumps({"missing": True},
                          ensure_ascii=False), "utf-8")
            missing += 1
            continue
        profile = extract_profile(html)
        if profile is None:
            print("AVISO: {} sem __NEXT_DATA__".format(p["name"]))
            errors += 1
            continue
        profile["attendance_id"] = p["attendance_id"]
        f.write_text(json.dumps(profile, ensure_ascii=False), "utf-8")
        ok += 1
        if i % 50 == 0:
            print("  {}/{} (ok={}, sem pagina={}, erros={})".format(
                i, len(people), ok, missing, errors))

    print("pronto: ok={}, sem pagina (404)={}, erros={}".format(
        ok, missing, errors))
    return 0


if __name__ == "__main__":
    sys.exit(main())
