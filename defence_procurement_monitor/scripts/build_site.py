#!/usr/bin/env python3
import os, markdown
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE, "data")
SITE_DIR = os.path.join(BASE, "site")
REPORTS_DIR = os.path.join(BASE, "reports")
os.makedirs(SITE_DIR, exist_ok=True)
for name in ('articles.json','themes.json'):
    src=os.path.join(DATA_DIR,name); dst=os.path.join(SITE_DIR,name)
    if os.path.exists(src):
        with open(src,'rb') as s, open(dst,'wb') as d: d.write(s.read())
