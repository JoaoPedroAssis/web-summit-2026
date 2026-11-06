#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Consolida a base de pessoas a partir da programação crua.

Varre data/raw/schedule/**/*.json (pulando manifest.json), deduplica
participações por attendance_id e agrega por pessoa: cargo, empresa,
sessões (com dia, horário, palco e trilha) e flags úteis para a triagem.

Saída:
  data/people.json
  data/people.csv

Uso:
  python3 consolidate.py [--raw data/raw/schedule] [--out data]
"""

import argparse
import csv
import json
import sys
from pathlib import Path


def parse_payload(text):
    data = (json.loads(text) or {}).get("data") or {}
    return data.get("listItems") or []


def session_summary(item):
    track = ((item.get("schedule_track") or {}).get("name") or "").strip()
    loc = ((item.get("location") or {}).get("name") or "").strip()
    starts = item.get("starts_at") or ""
    # `date` vem em texto ("November 10"); a data canônica sai do starts_at
    return {
        "id": item.get("id"),
        "title": (item.get("title") or "").strip(),
        "date": starts[:10] if starts else (item.get("date") or ""),
        "starts_at": starts,
        "ends_at": item.get("ends_at") or "",
        "track": track,
        "location": loc,
    }


def best_avatar(p):
    urls = p.get("avatar_urls") or {}
    for size in ("medium", "large", "thumb", "tiny", "original"):
        if urls.get(size):
            return urls[size]
    return ""


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", default="data/raw/schedule")
    ap.add_argument("--out", default="data")
    args = ap.parse_args()

    rawdir, outdir = Path(args.raw), Path(args.out)
    people = {}
    sessions_by_id = {}
    n_sessions, n_participations = 0, 0
    problems = []

    for f in sorted(rawdir.rglob("page-*.json")):
        for item in parse_payload(f.read_text("utf-8")):
            if not item.get("id"):
                continue
            sess = session_summary(item)
            sessions_by_id[sess["id"]] = sess
            # mesma sessão pode aparecer em mais de uma consulta (sem
            # filtro + por trilha); a dedupe por id de sessão, feita mais
            # abaixo por pessoa, resolve a duplicação
            for p in item.get("timeslot_participations") or []:
                n_participations += 1
                aid = (p.get("attendance_id") or "").strip()
                if not aid:
                    problems.append("sessao {} tem participacao sem "
                                    "attendance_id".format(sess["id"]))
                    continue
                person = people.setdefault(aid, {
                    "attendance_id": aid,
                    "name": (p.get("name") or "").strip(),
                    "job_title": (p.get("job_title") or "").strip(),
                    "company_name": (p.get("company_name") or "").strip(),
                    "role": (p.get("role") or "").strip(),
                    "avatar_url": best_avatar(p),
                    "sessions": [],
                })
                # nome/cargo/empresa podem diferir entre sessões; mantém o
                # primeiro não vazio de cada campo
                for field in ("name", "job_title", "company_name", "role"):
                    if not person[field] and p.get(field):
                        person[field] = str(p[field]).strip()
                if not person["avatar_url"]:
                    person["avatar_url"] = best_avatar(p)
                person["sessions"].append(sess)

    # dedupe de sessões por pessoa (sessão vista em 2 arquivos) e enriquecimento
    for person in people.values():
        by_id = {}
        for s in person["sessions"]:
            by_id[s["id"]] = s
        person["sessions"] = sorted(
            by_id.values(), key=lambda s: (s["date"], s["starts_at"] or ""))
        person["n_talks"] = len(person["sessions"])
        person["tracks"] = sorted({s["track"] for s in person["sessions"]
                                   if s["track"]})
        person["in_meetup"] = any(s["track"] == "Meetup"
                                  for s in person["sessions"])
        person["days"] = sorted({s["date"] for s in person["sessions"]})
        n_sessions += person["n_talks"]

    people = sorted(people.values(),
                    key=lambda p: (-p["n_talks"], p["name"].lower()))

    # base de sessões completa (inclui as sem speakers, ex.: meetups),
    # com quem participa — insumo do roteiro
    sess_aids = {}
    for p in people:
        for s in p["sessions"]:
            sess_aids.setdefault(s["id"], []).append(p["attendance_id"])
    sessions = sorted(sessions_by_id.values(),
                      key=lambda s: (s["date"], s["starts_at"] or ""))
    for s in sessions:
        s["speaker_ids"] = sorted(sess_aids.get(s["id"], []))
    (outdir / "sessions.json").write_text(
        json.dumps(sessions, ensure_ascii=False, indent=1), "utf-8")

    outdir.mkdir(parents=True, exist_ok=True)
    jpath = outdir / "people.json"
    jpath.write_text(json.dumps(people, ensure_ascii=False, indent=1),
                     "utf-8")

    cpath = outdir / "people.csv"
    with cpath.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["attendance_id", "name", "job_title", "company_name",
                    "n_talks", "in_meetup", "tracks", "talks"])
        for p in people:
            w.writerow([
                p["attendance_id"], p["name"], p["job_title"],
                p["company_name"], p["n_talks"], "sim" if p["in_meetup"]
                else "nao", "; ".join(p["tracks"]),
                " | ".join("{}/{} {} ({}), {}".format(
                               s["date"][8:10], s["date"][5:7],
                               s["starts_at"][11:16],
                               s["track"] or "sem trilha",
                               s["location"] or "?")
                           for s in p["sessions"]),
            ])

    print("pessoas unicas: {}".format(len(people)))
    print("participacoes processadas: {}".format(n_participations))
    print("sessoes (pessoa x sessao): {}".format(n_sessions))
    meetups = sum(1 for p in people if p["in_meetup"])
    print("pessoas em meetup: {}".format(meetups))
    if problems:
        print("avisos ({}):".format(len(problems)))
        for msg in problems[:10]:
            print("  -", msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
