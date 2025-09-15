#!/usr/bin/env python3
import os, re, json, time, math, hashlib, argparse, textwrap, random, subprocess
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
import feedparser, requests, yaml
from bs4 import BeautifulSoup
import trafilatura
from dateutil import parser as dateparse
from collections import Counter, defaultdict

import pandas as pd
import numpy as np

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE, "data")
REPORTS_DIR = os.path.join(BASE, "reports")
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")
STOPWORDS = set(open(os.path.join(os.path.dirname(__file__), "stopwords_en.txt")).read().split(","))

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "user_seed", "text"), exist_ok=True)

def load_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)

def norm_text(s: str) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s

def fetch_url(url: str, timeout=15):
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent":"Mozilla/5.0 (defence-proc-monitor)"})
        if r.status_code == 200:
            return r.text
    except Exception:
        return None
    return None

def extract_text(html: str, url: str) -> str:
    if not html:
        return ""
    try:
        downloaded = trafilatura.extract(html, url=url, include_comments=False, include_tables=False, no_fallback=False)
        if downloaded:
            return downloaded
    except Exception:
        pass
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script","style","noscript"]):
            tag.decompose()
        return soup.get_text(" ", strip=True)
    except Exception:
        return ""

def sim_hash(text: str) -> str:
    return hashlib.sha256(norm_text(text).lower().encode("utf-8")).hexdigest()

def score_article(meta, text, cfg):
    title = (meta.get("title") or "").lower()
    url = (meta.get("url") or "").lower()
    host = urlparse(url).hostname or ""
    content = (text or "").lower()
    n_chars = len(content)

    score = 0.0
    for d in cfg.get("prefer_domains", []):
        if d in host:
            score += 0.08
    base_kw = ["defence procurement","defense procurement","acquisition","tender","contracting","DE&S","industrial base","NAO","equipment plan","SSRO","single source"]
    for k in base_kw:
        if k in title:
            score += 0.10
    for k in base_kw:
        if k in content:
            score += 0.06
    for k in cfg.get("keywords",{}).get("problems",[]):
        if k.lower() in content:
            score += 0.02
    for k in cfg.get("keywords",{}).get("solutions",[]):
        if k.lower() in content:
            score += 0.02
    if n_chars >= cfg.get("scoring",{}).get("min_chars",800):
        score += 0.10
    else:
        score -= 0.08
    rec_days = cfg.get("scoring",{}).get("prefer_recency_days",365)
    dt = meta.get("date")
    if isinstance(dt, datetime):
        age_days = (datetime.now(timezone.utc) - dt).days
        if age_days <= rec_days:
            score += 0.06
        else:
            score -= 0.04
    return max(-1.0, min(1.0, score))

def tag_themes(text, cfg):
    content = (text or "").lower()
    tags = set()
    for k in cfg.get("keywords",{}).get("problems",[]):
        if k.lower() in content:
            tags.add(k)
    for k in cfg.get("keywords",{}).get("solutions",[]):
        if k.lower() in content:
            tags.add(k)
    return sorted(tags)

def extract_solutions(text):
    sentences = re.split(r'(?<=[.!?])\s+', text or "")
    cues = ("should","must","we need to","recommend","propose","ought to","could","establish","adopt","create","introduce")
    sols = []
    for s in sentences:
        sl = s.lower()
        if any(c in sl for c in cues) and 60 <= len(s) <= 280:
            sols.append(s.strip())
    return sols[:10]

def simple_summary(text, n_sent=5):
    if not text:
        return ""
    sentences = re.split(r'(?<=[.!?])\s+', norm_text(text))
    scored = []
    for s in sentences:
        tokens = [w for w in re.findall(r"[a-zA-Z\-]{3,}", s.lower()) if w not in STOPWORDS]
        scored.append((len(set(tokens)), s))
    top = [s for _, s in sorted(scored, key=lambda x: x[0], reverse=True)[:n_sent]]
    order = {s:i for i,s in enumerate(sentences)}
    top_sorted = sorted(top, key=lambda s: order.get(s, 0))
    return " ".join(top_sorted)

def openai_summary(text, api_key, max_tokens=300):
    try:
        import json, requests
        prompt = f"Summarise the following article in 5-7 bullet points focusing on UK defence procurement problems and proposed solutions. Be specific and concise.\n\n{text[:12000]}"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        body = {
            "model": "gpt-4o-mini",
            "temperature": 0.3,
            "messages": [{"role":"user","content":prompt}],
            "max_tokens": max_tokens
        }
        r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, data=json.dumps(body), timeout=60)
        if r.status_code == 200:
            out = r.json()["choices"][0]["message"]["content"]
            return out.strip()
    except Exception as e:
        return None
    return None

def fetch_feed(url):
    try:
        fp = feedparser.parse(url)
        return fp.entries
    except Exception:
        return []

def clean_date(e):
    for k in ("published","updated","created"):
        if e.get(k):
            try:
                return dateparse.parse(e[k]).astimezone(timezone.utc)
            except Exception:
                continue
    if e.get("published_parsed"):
        try:
            return datetime.fromtimestamp(time.mktime(e["published_parsed"]), tz=timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc)

def bing_search(q, api_key, n=10):
    url = "https://api.bing.microsoft.com/v7.0/search"
    try:
        r = requests.get(url, params={"q":q, "count":n, "mkt":"en-GB", "setLang":"EN"}, headers={"Ocp-Apim-Subscription-Key": api_key}, timeout=20)
        if r.status_code == 200:
            js = r.json()
            webPages = js.get("webPages",{}).get("value",[])
            return [{"name":w["name"],"url":w["url"],"snippet":w.get("snippet","")} for w in webPages]
    except Exception:
        return []
    return []

def gather_social(cfg):
    items = []
    try:
        for q in cfg.get("social",{}).get("twitter_searches",[]):
            cmd = ["snscrape", "--max-results", "30", "twitter-search", q]
            out = subprocess.check_output(cmd, text=True, timeout=60)
            for line in out.splitlines():
                try:
                    js = json.loads(line)
                    items.append({
                        "title": f"Tweet by @{js.get('user',{}).get('username','unknown')}",
                        "url": js.get("url"),
                        "source": "Twitter",
                        "date": dateparse.parse(js.get("date")).astimezone(timezone.utc),
                        "html": js.get("renderedContent")
                    })
                except Exception:
                    pass
        for q in cfg.get("social",{}).get("reddit_searches",[]):
            cmd = ["snscrape", "--max-results", "50", "reddit-search", q]
            out = subprocess.check_output(cmd, text=True, timeout=60)
            for line in out.splitlines():
                try:
                    js = json.loads(line)
                    items.append({
                        "title": js.get("title") or "Reddit post",
                        "url": js.get("url"),
                        "source": "Reddit",
                        "date": dateparse.parse(js.get("date")).astimezone(timezone.utc),
                        "html": js.get("content") or js.get("selfText","")
                    })
                except Exception:
                    pass
    except Exception:
        pass
    return items

def load_user_seed():
    urls_path = os.path.join(DATA_DIR, "user_seed", "urls.txt")
    texts_dir = os.path.join(DATA_DIR, "user_seed", "text")
    urls = []
    if os.path.exists(urls_path):
        with open(urls_path) as f:
            urls = [u.strip() for u in f if u.strip() and not u.strip().startswith("#")]
    texts = []
    for fn in os.listdir(texts_dir):
        if fn.lower().endswith(".txt"):
            with open(os.path.join(texts_dir, fn), "r", errors="ignore") as f:
                texts.append({"title": os.path.splitext(fn)[0], "text": f.read()})
    return urls, texts

def bias_terms_from_user(texts, topk=25):
    freq = Counter()
    for t in texts:
        for w in re.findall(r"[a-zA-Z\-]{3,}", t.get("text","").lower()):
            if w not in STOPWORDS:
                freq[w]+=1
    return [w for w,_ in freq.most_common(topk)]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="Pull new items from feeds, search, social")
    ap.add_argument("--summarise", action="store_true", help="Generate summaries (OpenAI if key present; fallback otherwise)")
    ap.add_argument("--weekly", action="store_true", help="Produce weekly summary report and site page")
    args = ap.parse_args()

    cfg = load_config()
    openai_key = os.environ.get("OPENAI_API_KEY")
    bing_key = os.environ.get("BING_API_KEY")

    existing = []
    articles_path = os.path.join(DATA_DIR, "articles.json")
    if os.path.exists(articles_path):
        with open(articles_path, "r") as f:
            try:
                existing = json.load(f)
            except Exception:
                existing = []
    seen_urls = {a["url"] for a in existing}
    seen_hashes = {a.get("content_hash") for a in existing if a.get("content_hash")}

    seed_urls, seed_texts = load_user_seed()
    boosted = set(bias_terms_from_user(seed_texts))
    for term in boosted:
        if term not in cfg["keywords"]["problems"] and term not in cfg["keywords"]["solutions"]:
            cfg["keywords"]["problems"].append(term)

    new_items = []

    if args.refresh:
        for feed in cfg.get("feeds", []):
            entries = fetch_feed(feed["url"])
            for e in entries:
                link = e.get("link") or e.get("id")
                if not link or link in seen_urls: 
                    continue
                title = norm_text(e.get("title") or "")
                if any(t.lower() in (title.lower()+" "+link.lower()) for t in cfg.get("exclude_terms",[])):
                    continue
                dt = clean_date(e)
                new_items.append({
                    "title": title,
                    "url": link,
                    "source": feed.get("name") or urlparse(link).hostname,
                    "date": dt,
                    "html": None
                })

        if bing_key:
            for q in cfg.get("queries", []):
                res = bing_search(q, bing_key, n=15)
                for r in res:
                    link = r["url"]
                    if link in seen_urls: 
                        continue
                    new_items.append({
                        "title": norm_text(r["name"]),
                        "url": link,
                        "source": urlparse(link).hostname,
                        "date": datetime.now(timezone.utc),
                        "html": None
                    })

        social = gather_social(cfg)
        new_items.extend(social)

        for u in seed_urls:
            if u not in seen_urls:
                new_items.append({
                    "title": "",
                    "url": u,
                    "source": urlparse(u).hostname,
                    "date": datetime.now(timezone.utc),
                    "html": None
                })

    processed = []
    for item in new_items:
        html = item.get("html") or fetch_url(item["url"])
        text = extract_text(html, item["url"])
        if not text or len(text) < 400:
            continue
        ch = sim_hash(text)
        if ch in seen_hashes:
            continue

        summary = ""
        if args.summarise and openai_key:
            summary = openai_summary(text, openai_key) or ""
        if args.summarise and not summary:
            summary = simple_summary(text, n_sent=5)

        meta = {"title": item["title"], "url": item["url"], "date": item["date"]}
        sc = score_article(meta, text, cfg)
        tags = tag_themes(text, cfg)
        solutions = extract_solutions(text)

        processed.append({
            "id": hashlib.md5(item["url"].encode()).hexdigest(),
            "title": item["title"] or text[:90] + "…",
            "url": item["url"],
            "source": item["source"],
            "date": item["date"].astimezone(timezone.utc).isoformat(),
            "summary": summary,
            "relevance_score": round(sc,3),
            "tags": tags,
            "solutions": solutions,
            "content_hash": ch,
            "content_length": len(text)
        })

    all_items = existing + processed
    all_items.sort(key=lambda a: a.get("date",""), reverse=True)

    theme_counts = Counter()
    sol_counts = Counter()
    for a in all_items:
        for t in a.get("tags",[]):
            theme_counts[t]+=1
        for s in a.get("solutions",[]):
            sol_counts[s]+=1

    themes = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "themes": [{"name":k, "count":v} for k,v in theme_counts.most_common(50)],
        "top_solutions": [{"text":k, "count":v} for k,v in sol_counts.most_common(50)]
    }

    with open(os.path.join(DATA_DIR, "articles.json"), "w") as f:
        json.dump(all_items, f, indent=2)
    with open(os.path.join(DATA_DIR, "themes.json"), "w") as f:
        json.dump(themes, f, indent=2)

    if args.weekly:
        one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        week_items = [a for a in all_items if dateparse.parse(a["date"]) >= one_week_ago]
        lines = ["# Weekly Summary (last 7 days)\n"]
        lines.append(f"Items collected: **{len(week_items)}**\n")
        tc = Counter()
        for a in week_items:
            for t in a.get("tags",[]):
                tc[t]+=1
        if tc:
            lines.append("## Emerging themes\n")
            for k,v in tc.most_common(10):
                lines.append(f"- **{k}** × {v}")
            lines.append("")
        if week_items:
            lines.append("## Highlights\n")
            for a in week_items[:10]:
                lines.append(f"- [{a['title']}]({a['url']}) — {a['source']} (score {a['relevance_score']})")
        md = "\n".join(lines)
        with open(os.path.join(REPORTS_DIR, "weekly_summary.md"), "w") as f:
            f.write(md)

    print(f"Processed {len(processed)} new items. Total stored: {len(all_items)}")

if __name__ == "__main__":
    main()
