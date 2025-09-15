#!/usr/bin/env python3
import os, re, json, time, hashlib, argparse, subprocess
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
import feedparser, requests, yaml
from bs4 import BeautifulSoup
import trafilatura
from dateutil import parser as dateparse
from collections import Counter

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

def norm_text(s): return re.sub(r"\s+"," ",s or "").strip()

def fetch_url(url, timeout=20):
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent":"Mozilla/5.0 (defence-proc-monitor)"})
        if r.status_code == 200: return r.text
    except Exception: return None
    return None

def extract_text(html, url):
    if not html: return ""
    try:
        out = trafilatura.extract(html, url=url, include_comments=False, include_tables=False, no_fallback=False)
        if out: return out
    except Exception: pass
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script","style","noscript"]): tag.decompose()
        return soup.get_text(" ", strip=True)
    except Exception: return ""

def sim_hash(text): return hashlib.sha256(norm_text(text).lower().encode("utf-8")).hexdigest()

def score_article(meta, text, cfg):
    title = (meta.get("title") or "").lower()
    url = (meta.get("url") or "").lower()
    host = urlparse(url).hostname or ""
    content = (text or "").lower()
    n_chars = len(content)
    score = 0.0
    for d in cfg.get("prefer_domains", []):
        if d in host: score += 0.08
    base_kw = ["defence procurement","defense procurement","acquisition","tender","contracting","de&s","industrial base","nao","equipment plan","ssro","single source"]
    for k in base_kw:
        if k in title: score += 0.10
        if k in content: score += 0.06
    for k in cfg.get("keywords",{}).get("problems",[]): 
        if k.lower() in content: score += 0.02
    for k in cfg.get("keywords",{}).get("solutions",[]): 
        if k.lower() in content: score += 0.02
    if n_chars >= cfg.get("scoring",{}).get("min_chars",800): score += 0.10
    else: score -= 0.08
    rec_days = cfg.get("scoring",{}).get("prefer_recency_days",365)
    dt = meta.get("date")
    if isinstance(dt, datetime):
        age_days = (datetime.now(timezone.utc) - dt).days
        score += (0.06 if age_days <= rec_days else -0.04)
    return max(-1.0, min(1.0, score))

def tag_themes(text, cfg):
    content = (text or "").lower()
    tags = set()
    for k in cfg.get("keywords",{}).get("problems",[]):
        if k.lower() in content: tags.add(k)
    for k in cfg.get("keywords",{}).get("solutions",[]):
        if k.lower() in content: tags.add(k)
    return sorted(tags)

def extract_solutions(text):
    sents = re.split(r'(?<=[.!?])\s+', text or "")
    cues = ("should","must","we need to","recommend","propose","ought to","could","establish","adopt","create","introduce")
    sols = [s.strip() for s in sents if any(c in s.lower() for c in cues) and 60 <= len(s) <= 280]
    return sols[:10]

def simple_summary(text, n=5):
    if not text: return ""
    sents = re.split(r'(?<=[.!?])\s+', norm_text(text))
    scored = []
    for s in sents:
        toks = [w for w in re.findall(r"[a-zA-Z\-]{3,}", s.lower()) if w not in STOPWORDS]
        scored.append((len(set(toks)), s))
    top = [s for _, s in sorted(scored, key=lambda x: x[0], reverse=True)[:n]]
    order = {s:i for i,s in enumerate(sents)}
    return " ".join(sorted(top, key=lambda s: order.get(s, 0)))

def openai_summary(text, api_key, max_tokens=300):
    try:
        import requests
        prompt = "Summarise in 5-7 bullets focusing on UK defence procurement problems and proposed solutions. Be specific.\\n\\n" + text[:12000]
        headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"}
        body={"model":"gpt-4o-mini","temperature":0.3,"messages":[{"role":"user","content":prompt}],"max_tokens":max_tokens}
        r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=body, timeout=60)
        if r.status_code==200: return r.json()["choices"][0]["message"]["content"].strip()
    except Exception: return None
    return None

def fetch_feed(url):
    try: return feedparser.parse(url).entries
    except Exception: return []

def clean_date(e):
    for k in ("published","updated","created"):
        if e.get(k):
            try: return dateparse.parse(e[k]).astimezone(timezone.utc)
            except Exception: pass
    if e.get("published_parsed"):
        try: 
            import time
            return datetime.fromtimestamp(time.mktime(e["published_parsed"]), tz=timezone.utc)
        except Exception: pass
    return datetime.now(timezone.utc)

def bing_search(q, api_key, n=12):
    try:
        r = requests.get("https://api.bing.microsoft.com/v7.0/search",
            params={"q":q,"count":n,"mkt":"en-GB","setLang":"EN"},
            headers={"Ocp-Apim-Subscription-Key":api_key}, timeout=20)
        if r.status_code==200:
            js=r.json().get("webPages",{}).get("value",[])
            return [{"name":w["name"],"url":w["url"],"snippet":w.get("snippet","")} for w in js]
    except Exception: return []
    return []

def gather_social(cfg):
    items=[]
    try:
        out=""
        for q in cfg.get("social",{}).get("twitter_searches",[]):
            out = subprocess.check_output(["snscrape","--max-results","30","twitter-search",q], text=True, timeout=60)
            for line in out.splitlines():
                try:
                    js=json.loads(line)
                    items.append({"title":f"Tweet by @{js.get('user',{}).get('username','unknown')}",
                                  "url":js.get("url"),"source":"Twitter",
                                  "date":dateparse.parse(js.get("date")).astimezone(timezone.utc),
                                  "html":js.get("renderedContent")})
                except Exception: pass
        for q in cfg.get("social",{}).get("reddit_searches",[]):
            out = subprocess.check_output(["snscrape","--max-results","50","reddit-search",q], text=True, timeout=60)
            for line in out.splitlines():
                try:
                    js=json.loads(line)
                    items.append({"title":js.get("title") or "Reddit post","url":js.get("url"),"source":"Reddit",
                                  "date":dateparse.parse(js.get("date")).astimezone(timezone.utc),
                                  "html":js.get("content") or js.get("selfText","")})
                except Exception: pass
    except Exception: pass
    return items

def load_user_seed():
    urls_path=os.path.join(DATA_DIR,"user_seed","urls.txt")
    texts_dir=os.path.join(DATA_DIR,"user_seed","text")
    urls=[]
    if os.path.exists(urls_path):
        with open(urls_path) as f: urls=[u.strip() for u in f if u.strip() and not u.strip().startswith("#")]
    texts=[]
    for fn in os.listdir(texts_dir):
        if fn.lower().endswith(".txt"):
            with open(os.path.join(texts_dir,fn),"r",errors="ignore") as f:
                texts.append({"title":os.path.splitext(fn)[0],"text":f.read()})
    return urls, texts

def bias_terms_from_user(texts, topk=25):
    from collections import Counter as C
    freq=C()
    for t in texts:
        for w in re.findall(r"[a-zA-Z\-]{3,}", t.get("text","").lower()):
            if w not in STOPWORDS: freq[w]+=1
    return [w for w,_ in freq.most_common(topk)]

def main():
    cfg=load_config()
    openai_key=os.environ.get("OPENAI_API_KEY")
    bing_key=os.environ.get("BING_API_KEY")

    existing=[]
    apath=os.path.join(DATA_DIR,"articles.json")
    if os.path.exists(apath):
        with open(apath,"r") as f:
            try: existing=json.load(f)
            except Exception: existing=[]
    seen_urls={a["url"] for a in existing}
    seen_hashes={a.get("content_hash") for a in existing if a.get("content_hash")}

    seed_urls, seed_texts = load_user_seed()
    boosted=set(bias_terms_from_user(seed_texts))
    for term in boosted:
        if term not in cfg["keywords"]["problems"] and term not in cfg["keywords"]["solutions"]:
            cfg["keywords"]["problems"].append(term)

    new_items=[]
    # Feeds
    for feed in cfg.get("feeds",[]):
        for e in fetch_feed(feed["url"]):
            link=e.get("link") or e.get("id")
            if not link or link in seen_urls: continue
            title=norm_text(e.get("title") or "")
            if any(t.lower() in (title.lower()+" "+link.lower()) for t in cfg.get("exclude_terms",[])): continue
            dt=clean_date(e)
            new_items.append({"title":title,"url":link,"source":feed.get("name"),"date":dt,"html":None})
    # Web search (optional)
    if bing_key:
        for q in cfg.get("queries",[]):
            for r in bing_search(q, bing_key, n=15):
                link=r["url"]
                if link in seen_urls: continue
                new_items.append({"title":norm_text(r["name"]),"url":link,"source":urlparse(link).hostname,"date":datetime.now(timezone.utc),"html":None})
    # Social
    new_items.extend(gather_social(cfg))
    # User seeds
    for u in seed_urls:
        if u not in seen_urls:
            new_items.append({"title":"", "url":u,"source":urlparse(u).hostname,"date":datetime.now(timezone.utc),"html":None})

    processed=[]
    for item in new_items:
        html=item.get("html") or fetch_url(item["url"])
        text=extract_text(html, item["url"])
        if not text or len(text)<400: continue
        ch=sim_hash(text)
        if ch in seen_hashes: continue

        summary = simple_summary(text, n=5)  # default; OpenAI optional
        if openai_key:
            o = openai_summary(text, openai_key) 
            if o: summary=o

        sc=score_article({"title":item["title"],"url":item["url"],"date":item["date"]}, text, cfg)
        tags=tag_themes(text, cfg)
        solutions=extract_solutions(text)

        processed.append({
            "id": hashlib.md5(item["url"].encode()).hexdigest(),
            "title": item["title"] or text[:90]+"…",
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

    theme_counts=Counter(); sol_counts=Counter()
    for a in all_items:
        for t in a.get("tags",[]): theme_counts[t]+=1
        for s in a.get("solutions",[]): sol_counts[s]+=1

    themes={"updated":datetime.datetime.utcnow().isoformat()+"Z",
            "themes":[{"name":k,"count":v} for k,v in theme_counts.most_common(50)],
            "top_solutions":[{"text":k,"count":v} for k,v in sol_counts.most_common(50)]}

    with open(os.path.join(DATA_DIR,"articles.json"),"w") as f: json.dump(all_items,f,indent=2)
    with open(os.path.join(DATA_DIR,"themes.json"),"w") as f: json.dump(themes,f,indent=2)
    print(f"Processed {len(processed)} new items. Total stored: {len(all_items)}")
