# -*- coding: utf-8 -*-
"""
每日资讯抓取脚本
每天早上8:00运行，抓取3类各8条（共约24条）权威资讯，生成当日HTML页面
三类：梦幻西游 / AI资讯 / 兰花知识
"""
import os
import sys
import json
import time
import datetime
import urllib.parse
import urllib.request
import urllib.error
import ssl
import xml.etree.ElementTree as ET
from html import unescape

# 全局取消SSL证书验证（解决国内网络/代理的证书问题）
ssl._create_default_https_context = ssl._create_unverified_context

# ========== 配置 ==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "news_data")     # 每日原始数据json
OUT_DIR  = os.path.join(BASE_DIR, "news_pages")    # 每日生成的html页面
INDEX_FILE = os.path.join(OUT_DIR, "index.html")   # 新闻汇总入口页
PER_CATEGORY = 8    # 每个分类抓8条

RSS_PROXY = "https://api.rss2json.com/v1/api.json?rss_url="
CORS_PROXY = "https://corsproxy.io/?"

SOURCES = [
    # ========== AI资讯（权威+稳定源，共5个，取前8条）==========
    {"name": "量子位",       "type": "rss", "category": "AI资讯",   "url": "https://www.qbitai.com/feed"},
    {"name": "InfoQ中文站",  "type": "rss", "category": "AI资讯",   "url": "https://www.infoq.cn/feed"},
    {"name": "开源中国AI",   "type": "rss", "category": "AI资讯",   "url": "https://www.oschina.net/news/rss/industry/ai"},
    {"name": "Hacker News AI","type": "rss","category": "AI资讯",   "url": "https://hnrss.org/newest?q=AI+OR+LLM+OR+Agent+OR+GPT"},
    {"name": "机器之心(RSSHub)", "type": "rss", "category": "AI资讯", "url": "https://rsshub.app/jiqizhixin"},

    # ========== 梦幻西游（多源互补确保8条，共4个）==========
    {"name": "梦幻西游官网",  "type": "html", "category": "梦幻西游", "url": "https://xyq.163.com/",
     "parse": "xyq_163"},
    {"name": "梦幻官网新闻",  "type": "html", "category": "梦幻西游", "url": "https://xyq.163.com/news/",
     "parse": "xyq_163"},
    {"name": "梦幻贴吧精品",  "type": "html", "category": "梦幻西游", "url": "https://tieba.baidu.com/f?kw=%E6%A2%A6%E5%B9%BB%E8%A5%BF%E6%B8%B8&tab=good",
     "parse": "tieba_xyq"},
    {"name": "大神梦幻号",    "type": "html", "category": "梦幻西游", "url": "https://ds.163.com/game/xyq/",
     "parse": "ds_163"},

    # ========== 兰花知识（稳定英文+中文博客，共5个）==========
    {"name": "JustAddIce兰花", "type": "rss", "category": "兰花知识", "url": "https://www.justaddiceorchids.com/orchid-care-blog/rss.xml"},
    {"name": "Orchideria百科", "type": "rss", "category": "兰花知识", "url": "https://orchideria.com/feed/"},
    {"name": "Brooklyn兰花",   "type": "rss", "category": "兰花知识", "url": "https://bklynorchids.com/feed/"},
    {"name": "American Orchid","type": "rss",  "category": "兰花知识", "url": "https://www.aos.org/aos-blog?format=feed"},
    {"name": "兰花吧论坛",    "type": "rss",  "category": "兰花知识", "url": "https://rsshub.app/tieba/forum/兰花"},
]

CATEGORY_COLORS = {
    "梦幻西游": "#c9a96a",
    "AI资讯":     "#5f7aa8",
    "兰花知识":   "#5a8f7b",
}
CATEGORY_ICONS = {
    "梦幻西游": "🎮",
    "AI资讯":     "🤖",
    "兰花知识":   "🌺",
}

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"

# ========== 工具函数 ==========
def log(msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def http_get(url, timeout=20):
    """GET请求，URL含中文自动编码，自动检测UTF-8/GBK"""
    try:
        parts = urllib.parse.urlparse(url)
        path_parts = [urllib.parse.quote(p, safe=";/?:@&=+$,%-_.~") for p in parts.path.split("/")]
        query_enc = urllib.parse.quote_plus(parts.query, safe=";/?:@&=+$,%") if parts.query else ""
        url_enc = urllib.parse.urlunparse(parts._replace(path="/".join(path_parts), query=query_enc))
    except Exception:
        url_enc = url
    req = urllib.request.Request(url_enc, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        b = resp.read()
    for enc in ["utf-8", "gbk", "gb2312"]:
        try: return b.decode(enc)
        except: pass
    return b.decode("utf-8", errors="ignore")

def strip_html(html, max_len=200):
    import re
    txt = re.sub(r"<[^>]+>", "", html or "")
    txt = unescape(txt).replace("\r", "").replace("\n", " ").replace("\t", " ")
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt if len(txt) <= max_len else txt[:max_len] + "…"

# ========== 抓取方法 ==========
def fetch_rss_via_rss2json(src):
    """用公共代理转rss->json，解决跨域"""
    url = RSS_PROXY + urllib.parse.quote(src["url"])
    try:
        raw = http_get(url)
        data = json.loads(raw)
        if data.get("status") != "ok":
            raise Exception(data.get("message", "rss2json status no-ok"))
        items = []
        for it in data.get("items", [])[:PER_CATEGORY*2]:
            title = strip_html(it.get("title"), 120)
            if not title: continue
            items.append({
                "title": title,
                "link": it.get("link") or it.get("guid") or "",
                "summary": strip_html(it.get("description") or it.get("content") or "", 260),
                "date": it.get("pubDate") or "",
                "source": src["name"],
            })
        return items
    except Exception as e:
        log(f"  ✖ RSS2JSON 失败 {src['name']}: {e}")
        return []

def fetch_rss_direct(src):
    """直接解析原始RSS XML（不走代理）"""
    try:
        raw = http_get(src["url"])
        root = ET.fromstring(raw)
        # rss 2.0: /rss/channel/item  atom: /feed/entry
        items = []
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for item in root.findall(".//item") + root.findall(".//atom:entry", ns):
            t_el = item.find("title")
            l_el = item.find("link") or item.find("atom:link", ns)
            d_el = item.find("description") or item.find("summary") or item.find("atom:summary", ns) or item.find("content")
            title = strip_html(t_el.text if t_el is not None else "", 120)
            if not title: continue
            link = ""
            if l_el is not None:
                link = l_el.attrib.get("href") or l_el.text or ""
            date_el = item.find("pubDate") or item.find("updated") or item.find("atom:updated", ns)
            date = (date_el.text if date_el is not None else "") or ""
            desc = d_el.text if d_el is not None else ""
            items.append({
                "title": title,
                "link": link,
                "summary": strip_html(desc, 260),
                "date": date,
                "source": src["name"],
            })
            if len(items) >= PER_CATEGORY*2: break
        return items
    except Exception as e:
        log(f"  ✖ 直抓RSS失败 {src['name']}: {e}")
        return []

def fetch_xyq_163(src):
    """解析梦幻西游官网页面 —— 放宽要求：只要是 .html 的中长标题就收"""
    import re
    try:
        req = urllib.request.Request(src["url"], headers={
            "User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://xyq.163.com/",
        })
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw_bytes = resp.read()
        try: raw = raw_bytes.decode("gbk", errors="ignore")
        except: raw = raw_bytes.decode("utf-8", errors="ignore")
        items, seen = [], set()
        for href, title in re.findall(
            r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]{6,180}?)</a>', raw
        ):
            title_raw = re.sub(r"<[^>]+>", "", title).strip()
            title_clean = re.sub(r"\s+", " ", title_raw)
            if len(title_clean) < 8: continue
            if href.startswith("//"): href = "https:" + href
            elif href.startswith("/"): href = "https://xyq.163.com" + href
            elif href.startswith("./"): href = "https://xyq.163.com/" + href[2:]
            elif not href.startswith("http"): continue
            if not re.search(r"(xyq|163).*\.s?html", href): continue
            zh_count = len(re.findall(r"[\u4e00-\u9fa5]", title_clean))
            if zh_count < 4: continue
            if title_clean in seen: continue
            seen.add(title_clean)
            items.append({
                "title": title_clean[:120],
                "link": href,
                "summary": title_clean[:240],
                "date": "",
                "source": src["name"],
            })
            if len(items) >= PER_CATEGORY*3: break
        if len(items) < PER_CATEGORY:
            items.extend(fetch_xyq_backup_gonglve())
        return items
    except Exception as e:
        log(f"  ✖ 梦幻官网解析失败: {e}")
        return fetch_xyq_backup_gonglve()


def fetch_xyq_backup_gonglve():
    """梦幻官网不够的话，抓17173梦幻攻略页作为备份"""
    items = []
    try:
        import re
        url = "https://xyq.17173.com/"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as resp:
            b = resp.read()
        try:
            raw = b.decode("gbk", errors="ignore")
        except Exception:
            raw = b.decode("utf-8", errors="ignore")
        seen = set()
        for href, title in re.findall(
            r'<a[^>]*href=["\']([^"\']+\.s?html)["\'][^>]*>([\s\S]{6,150}?)</a>', raw
        ):
            title_c = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", title)).strip()
            if len(title_c) < 8 or title_c in seen: continue
            if not re.search(
                r"梦幻|攻略|武神坛|门派|锦衣|五开|召唤兽|PK|更新|维护|新服|玩法|师门|抓鬼|副本|科举|跑商|法宝|装备|特技",
                title_c,
            ):
                continue
            if href.startswith("//"): href = "https:" + href
            if not href.startswith("http"): continue
            seen.add(title_c)
            items.append({
                "title": title_c,
                "link": href,
                "summary": title_c,
                "date": "",
                "source": "17173梦幻专区",
            })
            if len(items) >= PER_CATEGORY: break
    except Exception as e:
        log(f"  ✖ 17173备份源失败: {e}")
    return items

def fetch_source(src):
    if src["type"] == "html":
        parser = src.get("parse")
        if parser == "xyq_163": return fetch_xyq_163(src)
        if parser == "xyq_17173": return fetch_xyq_backup_gonglve()
        if parser == "tieba_xyq": return fetch_tieba_xyq(src)
        if parser == "ds_163": return fetch_ds_163(src)
    # RSS 先试代理，失败再直抓
    res = fetch_rss_via_rss2json(src)
    if len(res) < 3:
        res2 = fetch_rss_direct(src)
        got_titles = {x["title"] for x in res}
        for x in res2:
            if x["title"] not in got_titles:
                res.append(x); got_titles.add(x["title"])
    return res


def fetch_tieba_xyq(src):
    """百度梦幻西游贴吧精品区，加上浏览器Referer绕过403"""
    items = []
    try:
        import re
        req = urllib.request.Request(src["url"], headers={
            "User-Agent": UA,
            "Referer": "https://tieba.baidu.com/",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            b = resp.read()
        try: raw = b.decode("utf-8", errors="ignore")
        except: raw = b.decode("gbk", errors="ignore")
        seen = set()
        pattern = r'href=["\'](/p/\d+[^"\']*?)["\'][^>]*>([\s\S]{6,150}?)</a>'
        for href, title in re.findall(pattern, raw):
            title_c = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", title)).strip()
            if len(title_c) < 10 or title_c in seen: continue
            zh_count = len(re.findall(r"[\u4e00-\u9fa5]", title_c))
            if zh_count < 6: continue
            seen.add(title_c)
            items.append({
                "title": title_c[:120],
                "link": "https://tieba.baidu.com" + href,
                "summary": title_c[:240],
                "date": "",
                "source": "梦幻贴吧",
            })
            if len(items) >= PER_CATEGORY: break
    except Exception as e:
        log(f"  ✖ 梦幻贴吧抓取失败: {e}")
    return items


def fetch_ds_163(src):
    """网易大神梦幻专区抓帖"""
    items = []
    try:
        import re
        req = urllib.request.Request(src["url"], headers={
            "User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://ds.163.com/",
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            b = resp.read()
        try: raw = b.decode("utf-8", errors="ignore")
        except: raw = b.decode("gbk", errors="ignore")
        seen = set()
        for href, title in re.findall(
            r'<a[^>]*href=["\'](https?://ds\.163\.com[^"\']*?)["\'][^>]*>([\s\S]{6,180}?)</a>', raw
        ):
            title_c = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", title)).strip()
            if len(title_c) < 8 or title_c in seen: continue
            zh_count = len(re.findall(r"[\u4e00-\u9fa5]", title_c))
            if zh_count < 4: continue
            seen.add(title_c)
            items.append({
                "title": title_c[:120],
                "link": href,
                "summary": title_c[:240],
                "date": "",
                "source": "网易大神",
            })
            if len(items) >= PER_CATEGORY: break
    except Exception as e:
        log(f"  ✖ 网易大神抓取失败: {e}")
    return items

# ========== 主流程 ==========
def run(date_str=None, force=False):
    """抓指定日期；force=True 就算JSON存在也重抓覆盖"""
    if not date_str:
        date_str = datetime.date.today().isoformat()
    data_path = os.path.join(DATA_DIR, f"news-{date_str}.json")
    if os.path.exists(data_path) and not force:
        log(f"[跳过] {date_str} 已有数据，不再抓（加 --force 重抓）")
        return True

    log(f"===== 抓取 {date_str} =====")
    collected = {"梦幻西游": [], "AI资讯": [], "兰花知识": []}

    for src in SOURCES:
        cat = src["category"]
        log(f"→ 抓 [{cat}] {src['name']} ({src['type']})")
        items = fetch_source(src)
        if not items:
            log("  没抓到东西，跳过")
            continue
        for it in items[:PER_CATEGORY]:
            got = {x["title"] for x in collected[cat]}
            if it["title"] not in got:
                collected[cat].append(it)
        log(f"  ✔ 抓到 {len(items)} 条，分类池累计 {len(collected[cat])} 条")
        time.sleep(0.5)

    final = {}
    for cat, arr in collected.items():
        final[cat] = arr[:PER_CATEGORY]
        log(f"[{cat}] 最终 {len(final[cat])} 条")

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump({"date": date_str, "categories": final, "generated_at": int(time.time())}, f, ensure_ascii=False, indent=2)
    log(f"原始数据保存：{data_path}")

    page_path = render_daily_html(date_str, final)
    log(f"当日页面：{page_path}")

    render_index_html()
    log(f"汇总入口：{INDEX_FILE}")
    log(f"===== {date_str} 完成 =====")
    return True


def sync_missing_days(days=30, force=False):
    """向前补抓 days 天内所有缺失日期的新闻"""
    today = datetime.date.today()
    ok = 0
    for i in range(days):
        d = today - datetime.timedelta(days=i)
        ds = d.isoformat()
        try:
            if run(ds, force=force):
                ok += 1
        except Exception as e:
            log(f"[异常] {ds}: {e}")
    log(f"\n===== 补齐完成：{ok}/{days} 天成功 =====")
    render_index_html()
    return True


# ========== 渲染HTML ==========
def render_daily_html(today, categories):
    sections = ""
    total = 0
    for cat in ["梦幻西游", "AI资讯", "兰花知识"]:
        color = CATEGORY_COLORS[cat]
        icon = CATEGORY_ICONS[cat]
        items = categories.get(cat, [])
        total += len(items)
        list_html = ""
        if items:
            for i, it in enumerate(items, 1):
                link = it.get("link") or "#"
                summary = it.get("summary") or it.get("title")
                src = it.get("source") or cat
                list_html += f"""
                <div class="card">
                  <div class="idx">{i:02d}</div>
                  <div class="cbody">
                    <a class="title" href="{link}" target="_blank" rel="noopener">{it['title']}</a>
                    <div class="sum">{summary}</div>
                    <div class="meta"><span class="src" style="color:{color}">{icon} {src}</span></div>
                  </div>
                </div>"""
        else:
            list_html = '<div class="empty">今天这个分类没有抓到内容，稍后重试一下吧~</div>'
        sections += f"""
        <section class="sec" id="{cat}">
          <div class="sec-title" style="border-left:5px solid {color};"><span style="font-size:22px;margin-right:6px;">{icon}</span>{cat} <span class="cnt">{len(items)}条</span></div>
          <div class="list">{list_html}</div>
        </section>"""

    date_cn = datetime.date.fromisoformat(today).strftime("%Y年%m月%d日")
    weekday = ["星期一","星期二","星期三","星期四","星期五","星期六","星期日"][datetime.date.fromisoformat(today).weekday()]
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<meta name="theme-color" content="#1a1d26">
<title>每日资讯 · {today}</title>
<style>
:root {{ --bg:#1a1d26; --card:#232733; --text:#e8eaef; --sub:#a7acba; --line:#2f3443; --accent:#c9a96a; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; background:var(--bg); color:var(--text); line-height:1.5; }}
.header {{ padding:22px 18px 14px; background:linear-gradient(180deg,#232733 0%, #1a1d26 100%); position:sticky; top:0; z-index:10; backdrop-filter:blur(8px); }}
.header h1 {{ margin:0; font-size:20px; font-weight:800; }}
.header .sub {{ margin-top:4px; color:var(--sub); font-size:13px; }}
.tabs {{ display:flex; gap:6px; margin:12px 18px 0; overflow-x:auto; padding-bottom:2px; }}
.tab {{ flex:0 0 auto; padding:6px 14px; font-size:13px; font-weight:700; color:var(--sub); background:var(--card); border:1px solid var(--line); border-radius:999px; text-decoration:none; }}
.tab.on {{ background:var(--accent); color:#1a1d26; border-color:var(--accent); }}
.container {{ padding:12px 14px 100px; max-width:720px; margin:0 auto; }}
.sec {{ margin-top:18px; }}
.sec-title {{ display:flex; align-items:center; font-size:17px; font-weight:800; padding:2px 0 2px 10px; margin-bottom:10px; }}
.sec-title .cnt {{ font-size:12px; color:var(--sub); font-weight:600; margin-left:8px; align-self:flex-end; }}
.list {{ display:flex; flex-direction:column; gap:10px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:14px 14px 14px 12px; display:flex; gap:12px; }}
.card .idx {{ flex:0 0 auto; width:28px; height:28px; border-radius:8px; background:rgba(201,169,106,.15); color:var(--accent); font-weight:800; font-size:13px; display:grid; place-items:center; flex-shrink:0; }}
.card .cbody {{ flex:1; min-width:0; }}
.card .title {{ color:var(--text); font-size:15px; font-weight:700; text-decoration:none; line-height:1.45; display:block; margin-bottom:6px; word-break:break-word; }}
.card .title:hover {{ color:var(--accent); }}
.card .sum {{ color:var(--sub); font-size:13px; line-height:1.55; margin-bottom:8px; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }}
.card .meta {{ font-size:12px; color:var(--sub); }}
.card .meta .src {{ font-weight:700; }}
.empty {{ padding:24px 12px; text-align:center; color:var(--sub); font-size:14px; background:var(--card); border-radius:14px; border:1px dashed var(--line); }}
.footer {{ text-align:center; color:var(--sub); font-size:12px; margin-top:28px; padding-bottom:10px; }}
.banner {{ margin:14px; padding:10px 14px; background:rgba(90,143,123,.15); border:1px solid rgba(90,143,123,.4); border-radius:12px; font-size:13px; color:#8abaa5; }}
</style>
</head>
<body>
<div class="header">
  <h1>📰 每日资讯 {date_cn} {weekday}</h1>
  <div class="sub">共 {total} 条 · 梦幻西游 / AI资讯 / 兰花知识 · 自动抓取于 {datetime.datetime.now().strftime('%H:%M')}</div>
  <div class="tabs">
    <a class="tab on" href="#梦幻西游">🎮 梦幻 {len(categories.get('梦幻西游',[]))}</a>
    <a class="tab" href="#AI资讯">🤖 AI {len(categories.get('AI资讯',[]))}</a>
    <a class="tab" href="#兰花知识">🌺 兰花 {len(categories.get('兰花知识',[]))}</a>
  </div>
</div>
<div class="container">
  {sections}
  <div class="footer">本页面每天 08:00 自动生成 · 数据来自公开RSS/官网新闻</div>
</div>
</body>
</html>"""
    out_path = os.path.join(OUT_DIR, f"news-{today}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path

def render_index_html():
    """生成所有新闻的列表页（按日期）"""
    files = sorted([f for f in os.listdir(OUT_DIR) if f.startswith("news-") and f.endswith(".html") and f != "news-.html"], reverse=True)
    items_html = ""
    for fn in files[:30]:
        date_str = fn.replace("news-", "").replace(".html", "")
        try:
            dt = datetime.date.fromisoformat(date_str)
            label = dt.strftime("%m月%d日")
            weekday = "一二三四五六日"[dt.weekday()]
        except:
            label, weekday = date_str, ""
        # 尝试读数量
        cnt = ""
        json_fn = f"news-{date_str}.json"
        json_path = os.path.join(DATA_DIR, json_fn)
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    js = json.load(f)
                    cats = js.get("categories", {})
                    s = sum(len(v) for v in cats.values())
                    cnt = f"{s}条"
            except: pass
        items_html += f'<li><a href="{fn}"><span class="d"><b>{label}</b><small>周{weekday}</small></span><span class="cnt">{cnt}</span><span class="arr">›</span></a></li>'
    if not items_html:
        items_html = '<li style="padding:24px;text-align:center;color:#a7acba;">还没有生成的资讯，先运行一次 news_fetcher.py 吧</li>'

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#1a1d26">
<title>每日资讯汇总</title>
<style>
:root {{ --bg:#1a1d26; --card:#232733; --text:#e8eaef; --sub:#a7acba; --line:#2f3443; --accent:#c9a96a; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; background:var(--bg); color:var(--text); }}
.header {{ padding:22px 18px; background:linear-gradient(180deg,#232733,#1a1d26); }}
.header h1 {{ margin:0; font-size:22px; font-weight:800; }}
.header p {{ margin:6px 0 0; color:var(--sub); font-size:13px; }}
.container {{ max-width:720px; margin:0 auto; padding:12px 14px 80px; }}
ul {{ list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:8px; }}
li a {{ display:flex; align-items:center; padding:14px 16px; background:var(--card); border:1px solid var(--line); border-radius:14px; text-decoration:none; color:var(--text); }}
li a:hover {{ border-color:var(--accent); }}
.d {{ flex:1; display:flex; flex-direction:column; }}
.d b {{ font-size:16px; font-weight:800; }}
.d small {{ font-size:12px; color:var(--sub); margin-top:2px; }}
.cnt {{ color:var(--accent); font-weight:700; font-size:13px; margin-right:8px; }}
.arr {{ color:var(--sub); font-size:22px; font-weight:700; }}
</style>
</head>
<body>
<div class="header">
  <h1>📰 每日资讯汇总</h1>
  <p>每天早上8:00自动更新 · 共 {len(files)} 天记录</p>
</div>
<div class="container"><ul>{items_html}</ul></div>
</body>
</html>"""
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="每日资讯抓取器")
    ap.add_argument("--sync", type=int, default=0, help="向前补抓N天（例--sync 30）")
    ap.add_argument("--date", type=str, default="", help="只抓指定日期 YYYY-MM-DD")
    ap.add_argument("--force", action="store_true", help="强制重抓覆盖已有JSON")
    args = ap.parse_args()

    if args.sync > 0:
        ok = sync_missing_days(days=args.sync, force=args.force)
    else:
        date_str = args.date or None
        ok = run(date_str=date_str, force=args.force)
    sys.exit(0 if ok else 1)

