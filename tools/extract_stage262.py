#!/usr/bin/env python3
import csv
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
ar = root / 'rathena-master/npc/other/hugel_bingo.txt'
en = root / 'rathena-master/npc_EN/other/hugel_bingo.txt'
out = root / 'stage262_pairs'
out.mkdir(exist_ok=True)

ar_lines = ar.read_text(encoding='utf-8-sig').splitlines()
en_lines = en.read_text(encoding='utf-8-sig').splitlines()
if len(ar_lines) != len(en_lines):
    raise SystemExit(f'line count mismatch: {len(ar_lines)} vs {len(en_lines)}')

rows = []
for i, (a, e) in enumerate(zip(ar_lines, en_lines), 1):
    # Include translated comments, visible NPC names, waitingroom labels,
    # dialogue, announcements, menu strings, and other quoted text.
    has_ar = bool(re.search(r'[\u0600-\u06FF]', a))
    has_en_text = bool(re.search(r'[A-Za-z]{2,}', e))
    if a != e and (has_ar or has_en_text):
        rows.append({'line': i, 'arabic': a, 'english': e})

with (out / 'pairs.csv').open('w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['line','arabic','english'])
    w.writeheader(); w.writerows(rows)
(out / 'pairs.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
(out / 'summary.txt').write_text(
    f'ar_lines={len(ar_lines)}\nen_lines={len(en_lines)}\npairs={len(rows)}\n',
    encoding='utf-8'
)
