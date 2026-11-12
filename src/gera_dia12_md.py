#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera docs/dia12_programacao.md a partir do raw do dia 12 (data/raw/schedule) e dos
snapshots do dia 11 e pré-remanejamento (backup/schedule-pre-remanejamento).
Rode da raiz do repo: python3 src/gera_dia12_md.py"""
import json,glob,re,collections
def load(d):
    r={}
    for f in sorted(glob.glob(f'data/raw/schedule/2026-11-{d}/**/page-*.json',recursive=True)):
        for it in json.load(open(f))['data']['listItems']: r[it['id']]=it
    return r
r11,r12=load('11'),load('12')
old={}
for f in glob.glob('backup/schedule-pre-remanejamento/2026-11-12/page-*.json'):
    for it in json.load(open(f))['data']['listItems']: old[it['id']]=it
def status(i):
    if i in r11 and i not in old: return 'remanejada do dia 11'
    if i in old: return 'já estava no dia 12'
    return 'nova no dia 12'
def hm(s): return s[11:16] if s else '--:--'
def clean(t): return re.sub(r'\n{3,}','\n\n',(t or '').replace('\r','').strip())
items=sorted(r12.values(),key=lambda x:(x['starts_at'] or '',(x.get('location') or {}).get('name') or '',x['title']))
cnt=collections.Counter(status(i['id']) for i in items)
out=['# Web Summit Lisboa 2026 — Programação do dia 12/11 (pós-remanejamento)','',
f'Fonte: API pública `/api/list-items/`, coletada em 12/11/2026. {len(items)} sessões. Horários em Lisboa (UTC+0 em novembro).','',
'Status: '+' · '.join(f'**{k}**: {v}' for k,v in cnt.items()),'',
'Origem: *remanejada* = mesmo id da sessão do dia 11 (cancelado); *já estava* = presente no snapshot anterior do dia 12; *nova* = id inédito.','',
f'Sessões do dia 11 sem correspondente no dia 12 (provável cancelamento): {len(set(r11)-set(r12))} — ver `data/raw/schedule/2026-11-11/`.','','---','']
cur=None
for it in items:
    h=hm(it['starts_at'])[:2]
    if h!=cur: cur=h; out+=[f'## {h}h','']
    loc=(it.get('location') or {}).get('name') or '—'
    tr=((it.get('schedule_track') or {}).get('name') or '').strip() or '—'
    out.append(f"### {hm(it['starts_at'])}–{hm(it['ends_at'])} · {it['title'].strip()}")
    out.append(f"- **Palco/local:** {loc} · **Trilha:** {tr} · **Status:** {status(it['id'])}")
    if i:=r11.get(it['id']):
        if i['starts_at']!=it['starts_at'] or (i.get('location') or {}).get('name')!=loc:
            out.append(f"- **Antes (dia 11):** {hm(i['starts_at'])} em {(i.get('location') or {}).get('name') or '—'}")
    langs=it.get('languages')
    if langs: out.append(f"- **Idiomas:** {', '.join(map(str,langs)) if isinstance(langs,list) else langs}")
    out.append(f"- **id:** `{it['id']}`")
    ps=it.get('timeslot_participations') or []
    if ps:
        out.append('- **Speakers:**')
        for p in ps:
            line=p['name'].strip()
            jc=', '.join(x for x in [p.get('job_title','').strip(),p.get('company_name','').strip()] if x)
            if jc: line+=f' — {jc}'
            if p.get('role'): line+=f" ({p['role']})"
            out.append(f'  - {line}')
    d=clean(it.get('description'))
    if d: out+=['',d.replace('\n','\n> ').join(['> ',''])]
    out.append('')
open('docs/dia12_programacao.md','w').write('\n'.join(out))
print(len(items),cnt)
