#!/usr/bin/env python3
import os, markdown
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE, "data")
SITE_DIR = os.path.join(BASE, "site")
REPORTS_DIR = os.path.join(BASE, "reports")
os.makedirs(SITE_DIR, exist_ok=True)

# Copy data into site
for name in ('articles.json','themes.json'):
    src = os.path.join(DATA_DIR, name)
    dst = os.path.join(SITE_DIR, name)
    if os.path.exists(src):
        with open(src, 'rb') as s, open(dst, 'wb') as d:
            d.write(s.read())

# Weekly summary -> HTML
wk_src = os.path.join(REPORTS_DIR, 'weekly_summary.md')
if os.path.exists(wk_src):
    with open(wk_src, 'r') as f:
        html = markdown.markdown(f.read(), extensions=['tables'])
    with open(os.path.join(SITE_DIR, 'weekly.html'), 'w') as f:
        f.write(f'<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="./styles.css"><a class="backlink" href="./index.html">← Back</a><main class="container card">{html}</main>')
