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

    # ========== 兰花知识（优先爬网络，不够就用内置精选中文知识库补全）==========
    {"name": "CSDN·兰花养护",   "type": "html", "category": "兰花知识",
     "url": "https://so.csdn.net/so/search?q=%E5%85%B0%E8%8A%B1%E5%85%BB%E6%8A%A4&t=blog",
     "list": r'<div[^>]*class="list-item main-item"[^>]*>.*?<a[^>]*href="(https://blog\.csdn\.net/[^"]+/article/details/\d+)"[^>]*>([^<]+)</a>',
     "summary_from": "title"},
    {"name": "花百科·兰花篇",   "type": "html", "category": "兰花知识",
     "url": "https://www.yuhuagu.com/lanhua/",
     "list": r'<a[^>]*href="(https://www\.yuhuagu\.com/lanhua/\d+\.html)"[^>]*title="([^"]+)"',
     "summary_from": "title"},
    {"name": "醉花网·兰花",     "type": "html", "category": "兰花知识",
     "url": "https://www.aihuhua.com/yanghua/lanhua/",
     "list": r'<a[^>]*href="(/yanghua/lanhua/\d+\.html)"[^>]*>([^<]+)</a>',
     "link_prefix": "https://www.aihuhua.com",
     "summary_from": "title"},
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
        # 通用HTML：用 src["list"] 的正则抓 (链接, 标题) 组
        return fetch_html_generic(src)
    # RSS 先试代理，失败再直抓
    res = fetch_rss_via_rss2json(src)
    if len(res) < 3:
        res2 = fetch_rss_direct(src)
        got_titles = {x["title"] for x in res}
        for x in res2:
            if x["title"] not in got_titles:
                res.append(x); got_titles.add(x["title"])
    return res


def fetch_html_generic(src):
    """通用HTML解析：用 src["list"] 正则批量抽 (url, title) 对"""
    import re
    items = []
    try:
        extra_headers = src.get("headers", {}) or {}
        req = urllib.request.Request(src["url"], headers={**{"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}, **extra_headers})
        with urllib.request.urlopen(req, timeout=20) as resp:
            b = resp.read()
        raw = None
        for enc in ["utf-8", "gbk", "gb2312"]:
            try: raw = b.decode(enc); break
            except: pass
        if not raw:
            try: raw = b.decode("utf-8", errors="ignore")
            except: return items
        pattern = src.get("list")
        if not pattern: return items
        seen = set()
        link_prefix = src.get("link_prefix", "")
        for m in re.finditer(pattern, raw):
            try:
                link = m.group(1).strip()
                title = m.group(2).strip()
            except Exception: continue
            if not link or not title: continue
            title_c = re.sub(r"<[^>]+>", "", title).strip()
            title_c = re.sub(r"\s+", " ", title_c)
            if len(title_c) < 5 or title_c in seen: continue
            if link.startswith("/") and link_prefix:
                link = link_prefix.rstrip("/") + link
            elif not link.startswith("http"):
                if link_prefix: link = link_prefix.rstrip("/") + "/" + link.lstrip("/")
                else: continue
            seen.add(title_c)
            items.append({
                "title": title_c,
                "link": link,
                "summary": title_c,
                "date": "",
                "source": src.get("name", src.get("category", "")),
            })
            if len(items) >= PER_CATEGORY*3: break
    except Exception as e:
        log(f"  ✖ HTML通用抓取失败 {src.get('name','')}: {e}")
    return items


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

    # —— 兰花知识：网络不够就用内置中文精选知识库补满 ——
    LAN_KB = [
      # === 浇水系列 ===
      ("兰花浇水口诀：见干见湿，浇则浇透",
       "兰花浇水最忌天天浇。正确做法：植料表面往下2-3厘米干透了再浇，一次浇透到盆底流水，半腰水是烂根第一杀手。"),
      ("夏天兰花什么时候浇水最好？",
       "夏季高温季节一定要在清晨或傍晚浇，避开正午高温；水温和盆土温差不要超过5℃，自来水最好提前晾1-2天再用。"),
      ("冬天兰花浇水要特别注意的3件事",
       "①水温与室温接近，别用冷水刺激根部；②选晴天中午浇，留出下午时间晾盆土；③整体减少浇水量，保持植料微润偏干即可。"),
      ("为什么我的兰花总烂根？90%是因为这3件事",
       "①植料不透气（纯园土/椰糠直接用）；②托盘长期积水（根喝死水烂掉）；③浇水过于频繁不看植料干湿。对照改正即可。"),

      # === 植料/上盆系列 ===
      ("新手养兰首选植料配方：松树皮+珍珠岩",
       "最省心的配方是发酵松树皮（小颗粒）:珍珠岩 = 7:3，透气保水又不容易积水。绝对不要直接拿花园泥土种兰花，必烂根无疑。"),
      ("兰花换盆的最佳时间和操作步骤",
       "春秋两季（15-25℃）最适合换盆。步骤：脱盆→清旧根→剪空根烂根→晾根1小时→上新植料→轻轻墩实→放阴凉处缓苗7天不浇水。"),
      ("花盆怎么选？泥瓦盆＞紫砂盆＞塑料盆",
       "透气性：泥瓦盆（红陶）最好，新手用最不容易烂根；紫砂盆美观透气中等；塑料盆方便但要注意减少浇水频率。"),
      ("兰花上盆时的两个致命错误",
       "①植料压太紧：根需要呼吸空间，轻轻墩实即可，手压压实直接闷根；②种太深：假鳞茎一定要露出一半，埋深了不发芽还烂茎。"),

      # === 光照系列 ===
      ("兰花到底要晒太阳吗？3句话讲清楚",
       "春冬可以直射晨光（上午10点前）；夏秋必须遮光50-70%（遮阳网或散光处）；叶片翠绿不发暗=光照正好，叶片焦黄=晒多了。"),
      ("家里什么位置最适合放兰花？",
       "最好的位置：朝南或朝东窗台外一米处（花架）；其次：客厅明亮散光的角落；最差：空调直吹处、厨房油烟处、卫生间湿气重且无光处。"),
      ("夏天兰花遮阳网要选多少针？",
       "建议选6针遮阳网（遮光约75%），或者双层3针叠加；阳台党如果没有遮阳网，可以搬到北阳台过夏，安全省心。"),
      ("光照不足的兰花会有哪6个表现？",
       "叶片细长徒长、叶片发暗没有光泽、假鳞茎瘦小、不开花、发芽少且弱、容易得病虫害。出现2条以上就要搬到更亮的地方。"),

      # === 温度系列 ===
      ("兰花最适宜的温度区间是多少？",
       "大多数中国兰花（春兰蕙兰建兰墨兰）最舒服的温度是18-28℃，低于5℃要防冻，高于35℃要降温通风，这两个温度是生死线。"),
      ("春兰蕙兰为什么冬天一定要春化？",
       "春兰蕙兰需要连续20-30天保持5-10℃低温完成花芽分化，否则第二年有花苞也开不出好花甚至消苞。建兰墨兰不需要春化。"),
      ("夏天高温期兰花如何安全度夏？",
       "核心三件事：①加强通风（风扇24小时吹最好）；②遮阳（遮光率70%+）；③控制浇水（傍晚凉风来再浇）。做到这三点度夏基本无忧。"),
      ("冬天兰花怎么安全越冬？",
       "0℃以上的地区，室外避雨遮阳处即可；零下地区搬入室内向阳处，减少浇水，远离暖气空调出风口，保持一定湿度。"),

      # === 施肥系列 ===
      ("兰花施肥原则：宁淡勿浓，薄肥勤施",
       "兰花根细不耐浓肥，任何肥料必须按说明书再稀释1-2倍使用。生长期（春秋）每10天一次薄肥，夏冬两季完全停肥。"),
      ("新手推荐的两款兰花肥",
       "①花多多1号（均衡肥，20-20-20）生长期灌根通用；②花多多2号（高磷肥，10-30-20）花苞期喷叶+灌根促花。都稀释1000倍用。"),
      ("有机肥好还是化肥好？",
       "新手推荐化肥（花多多系列），浓度好控制不烧根；老手可以用发酵羊粪、花生壳、油枯做底肥，效果更好但要注意完全腐熟。"),
      ("兰花刚上盆多久能施肥？",
       "新上盆/换盆的兰花3个月内绝对不要施肥，伤口还在愈合，施肥等于害它。等新根扎稳、新芽开口后再薄肥伺候。"),

      # === 病虫害系列 ===
      ("兰花最常见的3种病害及防治",
       "①茎腐病（假鳞茎发黑发软）：立刻切除病株，伤口涂多菌灵，换新植料重栽；②炭疽病（叶上黑斑）：摘掉病叶，喷甲基托布津；③软腐（新芽发黑流水）：通风+减少浇水+农用链霉素灌根。"),
      ("兰花最常见的3种虫害及防治",
       "①介壳虫（叶背小白点）：酒精擦或喷护花神；②红蜘蛛（叶面白点叶背结网）：喷阿维菌素；③蜗牛/蛞蝓（夜里啃新芽）：撒四聚乙醛颗粒或啤酒诱杀。"),
      ("预防兰花病虫害的5个好习惯",
       "①通风永远放第一位；②不积水、不喷叶过夜；③新买的兰苗隔离观察15天再合群；④病叶病株立刻切除别犹豫；⑤每月一次预防性喷多菌灵/代森锰锌交替。"),
      ("兰花叶片长黑斑就是炭疽病吗？不一定",
       "也可能是：①肥害烧尖（叶尖焦黑往后扩）；②晒伤（面向阳光那一面集中出现）；③冻害（水渍状褐斑）；④药害浓度高了。先找原因再下药。"),

      # === 品种/新手系列 ===
      ("新手养兰从这4个品种起步，100%不翻车",
       "①墨兰『企黑』：最耐阴好养、冬天开花浓香；②建兰『小桃红』：一年多次开花、泼辣好管理；③春兰『大富贵』：经典荷瓣花大花香；④杂交兰『台北小姐』：便宜大颗、新手练手神器。"),
      ("兰花市场常见的骗局，新手一定要避坑",
       "①几块钱一苗的「高科技组培奇花」，颜色越离谱越假；②路边卖的裸根「下山兰」大多是烂苗；③不要追求天价品种，先把普草养开花再说。"),
      ("兰花怎么算养得好？看这5个指标",
       "①假鳞茎饱满圆大；②叶片油亮翠绿有光泽；③根系雪白/米黄粗壮；④每年发新芽数量是老苗数的1.5倍以上；⑤该开花的季节按时出花苞。"),
      ("兰花一年能发几苗？正常是多少？",
       "健康的成株兰花，春秋两季各发1-2个新芽是正常水平（苗数×1.5~2倍/年）。一年到头不发芽的说明根系不好，倒盆检查植料和根。"),

      # === 进阶系列 ===
      ("兰花分株繁殖的最佳时间和操作要点",
       "春秋20℃左右的季节最适合分株。一盆兰花至少3苗连体才建议分；分株伤口涂抹多菌灵粉晾干；分下来的小苗先干植料上盆，3天后再浇水。"),
      ("判断兰花该浇水了的4个实用小技巧",
       "①插竹签法：竹签插盆底，拔出来看末端，干的就浇；②掂盆法：重量明显变轻就该浇；③看植料表面：往下2-3厘米干透再浇；④看叶片：新叶略微发软下垂就是缺水信号。"),
      ("墨兰建兰春兰蕙兰的养护区别",
       "墨兰（报岁兰）：最耐阴，冬季开花，怕冻需5℃以上；建兰（四季兰）：喜温暖，夏秋多次开花，最耐热；春兰：需春化冬末春初开；蕙兰：最耐寒需强光照，春化温度更低。"),
      ("兰花根从盆底下钻出来要不要紧？",
       "好事情！说明根系发达健康，兰株长势旺。等明年春秋季换大一号的盆即可，现在完全不用管，这是养功好的标志。"),
      ("新买的兰花上盆前一定要做的3件事",
       "①冲洗干净根部旧植料；②修剪空根烂根断根；③多菌灵溶液泡根30分钟后捞出晾根，直到根部发白变软再上盆，基本可以杜绝后期茎腐。"),
      ("兰花消苞是什么原因？怎么预防？",
       "消苞最常见3原因：①温度骤变10℃以上；②花苞期施浓肥或浇水溅到花苞里；③空气太干（湿度<40%）。预防：花苞期保持稳定环境，不施肥不折腾，湿度维持50-70%。"),
      ("如何判断兰花是活的还是死了？",
       "别急着扔！挖出来看根：只要还有3条以上饱满的白色/米黄色活根，就算叶子掉光假鳞茎还饱满，就一定能救回来：切干净烂根→晾根→换新植料→阴凉处缓苗。"),
      ("兰花叶片发黄的8种原因对照表",
       "①老苗自然退草（从叶尖均匀黄，整苗同步）：正常；②新叶发黄发软：水大烂根；③叶尖焦黄：肥害/根闷；④叶片局部黑斑：病害；⑤叶脉黄缺绿：缺肥；⑥整叶均匀黄：光照不足；⑦黄叶带透明：冻害；⑧黄叶一碰就掉：茎腐前兆。"),
      ("北方室内养兰花最头疼的3件事及解决办法",
       "①空气太干：旁边放加湿器/浅水盆，或组盆养；②冬季暖气太热：远离暖气片，放靠窗通风处；③自来水碱性大：浇花前静置24小时，或每月浇一次淘米水/千分之一柠檬酸调酸。"),
      ("兰花新芽长到什么时候算服盆成功？",
       "上盆后3个月内没倒苗，新根长到5厘米以上，新芽开口展叶且叶片油亮，就算彻底服盆了。这时候可以移到正常光照位置开始薄肥养护。"),
      ("养兰最忌讳的5件事，新手几乎全中",
       "①天天手贱拔起来看根；②天天浇水生怕干死；③今天看教程加个肥明天看文章换个植料；④一盆生病不隔离全室传染；⑤盲目追求名贵品种，普草都没养活先买天价苗。管住手，少折腾，兰花反而养得好。"),
    ]

    if len(collected.get("兰花知识", [])) < PER_CATEGORY:
        import random
        random.seed(int(date_str.replace("-", "")))  # 同一天固定随机种子，保证同一天重抓内容一致
        want = PER_CATEGORY - len(collected.get("兰花知识", []))
        kb_items = list(LAN_KB)
        random.shuffle(kb_items)
        got_titles = {x["title"] for x in collected.get("兰花知识", [])}
        kb_url_base = "https://www.baidu.com/s?wd=%E5%85%B0%E8%8A%B1%20"
        added = 0
        for (title, summary) in kb_items:
            if added >= want: break
            if title in got_titles: continue
            collected.setdefault("兰花知识", []).append({
                "title": title,
                "link": kb_url_base + urllib.parse.quote(title),
                "summary": summary,
                "date": "",
                "source": "兰花养护知识库",
            })
            added += 1
        if added > 0:
            log(f"  📚 兰花知识网络不足，从精选知识库补充了 {added} 条（总计 {len(collected['兰花知识'])} 条）")

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
    cats_order = ["梦幻西游", "AI资讯", "兰花知识"]
    for idx, cat in enumerate(cats_order):
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
        display = "block" if idx == 0 else "none"
        sections += f"""
        <section class="sec" id="sec-{idx}" data-cat="{cat}" style="display:{display};">
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
* {{ box-sizing:border-box; -webkit-tap-highlight-color:transparent; }}
html {{ scroll-behavior:smooth; }}
body {{ margin:0; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; background:var(--bg); color:var(--text); line-height:1.5; padding-top:128px; }}

/* ========== 顶部栏 ========== */
.header {{
  position:fixed; top:0; left:0; right:0; z-index:100;
  background:linear-gradient(180deg,#232733 0%, #1a1d26 100%);
  backdrop-filter:blur(10px);
  border-bottom:1px solid var(--line);
}}
.navrow {{ display:flex; align-items:center; justify-content:space-between; padding:10px 12px 0; gap:8px; }}
.back {{
  flex:0 0 auto; display:inline-flex; align-items:center; gap:4px;
  padding:7px 12px; font-size:13px; font-weight:700; color:var(--text);
  background:var(--card); border:1px solid var(--line); border-radius:10px;
  text-decoration:none; transition:all .15s;
}}
.back:active {{ transform:scale(.96); background:#2a2f3d; }}
.crumbs {{ flex:1; min-width:0; font-size:12px; color:var(--sub); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; text-align:right; }}
.crumbs a {{ color:var(--accent); text-decoration:none; margin:0 2px; }}
.titlerow {{ padding:8px 16px 0; }}
.titlerow h1 {{ margin:0; font-size:18px; font-weight:800; }}
.subline {{ margin-top:2px; color:var(--sub); font-size:12px; }}

/* ========== 分类Tab ========== */
.tabs {{
  display:grid; grid-template-columns:1fr 1fr 1fr;
  gap:0; margin:12px 14px 10px;
  background:var(--card); border:1px solid var(--line);
  border-radius:12px; overflow:hidden;
}}
.tab {{
  padding:11px 4px; font-size:14px; font-weight:800;
  color:var(--sub); background:transparent; border:0; cursor:pointer;
  text-align:center; transition:all .2s;
}}
.tab .tnum {{ display:inline-block; font-size:11px; margin-left:3px; padding:2px 6px; background:rgba(255,255,255,.06); border-radius:999px; }}
.tab.on {{ background:var(--accent); color:#1a1d26; }}
.tab.on .tnum {{ background:rgba(26,29,38,.25); color:#1a1d26; }}

/* ========== 内容区 ========== */
.container {{ padding:10px 14px 100px; max-width:720px; margin:0 auto; }}
.sec {{ }}
.sec-title {{ display:flex; align-items:center; font-size:17px; font-weight:800; padding:2px 0 10px 10px; }}
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
  <div class="navrow">
    <a href="index.html" class="back" onclick="if(history.length>1 && document.referrer.indexOf('github.io')>=0){{history.back();return false;}}">← 资讯列表</a>
    <a href="../workbench-mobile.html" class="back">🎯 工作台</a>
    <div class="crumbs"><a href="../workbench-mobile.html">工作台</a>›<a href="index.html">资讯</a>›当日</div>
  </div>
  <div class="titlerow">
    <h1>📰 每日资讯 {date_cn} {weekday}</h1>
    <div class="subline">共 {total} 条 · 自动抓取于 {datetime.datetime.now().strftime('%H:%M')}</div>
  </div>
  <div class="tabs" id="tabs">
    <button class="tab on" data-i="0">🎮 梦幻<span class="tnum">{len(categories.get('梦幻西游',[]))}</span></button>
    <button class="tab"    data-i="1">🤖 AI<span class="tnum">{len(categories.get('AI资讯',[]))}</span></button>
    <button class="tab"    data-i="2">🌺 兰花<span class="tnum">{len(categories.get('兰花知识',[]))}</span></button>
  </div>
</div>

<div class="container" id="cont">
  {sections}
  <div class="footer">本页面每天 08:00 自动生成 · 数据来自公开RSS/官网新闻</div>
</div>

<script>
(function(){{
  var tabs = document.querySelectorAll('#tabs .tab');
  var secs = document.querySelectorAll('.sec');
  tabs.forEach(function(t){{
    t.addEventListener('click', function(){{
      var i = +this.getAttribute('data-i');
      tabs.forEach(function(x){{x.classList.remove('on');}});
      this.classList.add('on');
      secs.forEach(function(s, j){{
        s.style.display = (j===i)?'block':'none';
      }});
      window.scrollTo({{top:0,behavior:'instant'}});
    }});
  }});
  // 防止浏览器后退按钮卡到微信
  window.addEventListener('popstate', function(){{}});
}})();
</script>
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

