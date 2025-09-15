#!/usr/bin/env python3
import os, json, markdown
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE, "data")
SITE_DIR = os.path.join(BASE, "site")
REPORTS_DIR = os.path.join(BASE, "reports")

os.makedirs(SITE_DIR, exist_ok=True)

# Copy weekly summary as HTML
wk_src = os.path.join(REPORTS_DIR, "weekly_summary.md")
wk_dst = os.path.join(SITE_DIR, "weekly.html")
if os.path.exists(wk_src):
    with open(wk_src, "r") as f:
        html = markdown.markdown(f.read(), extensions=["tables"])
    template = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Weekly Summary</title>
<link rel="stylesheet" href="./styles.css" />
</head>
<body class="container">
<a class="backlink" href="./index.html">← Back to Dashboard</a>
<main class="card">{html}</main>
</body>
</html>"""
    with open(wk_dst, "w") as f:
        f.write(template)
