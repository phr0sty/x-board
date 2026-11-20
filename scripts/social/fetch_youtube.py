#!/usr/bin/env python3
"""Fetch public YouTube data: channel header counts (subscribers, videos) from the public channel page
and the latest 15 uploads with view counts from the official channel RSS feed
(https://www.youtube.com/feeds/videos.xml?channel_id=...). Output: raw JSON."""
import re, json, sys, time, urllib.request, argparse, html as H, os
import xml.etree.ElementTree as ET
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36',
      'Accept-Language': 'en-US,en;q=0.9', 'Cookie': 'CONSENT=YES+1'}
NS = {'a': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015', 'media': 'http://search.yahoo.com/mrss/'}
def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20).read().decode('utf8', 'ignore')
def parse_count(s):
    if not s: return None
    m = re.match(r'([\d.,]+)\s*([KMB]?)', s.replace('\u00a0', ' '))
    if not m: return None
    n = float(m.group(1).replace(',', '')); return int(round(n * {'': 1, 'K': 1e3, 'M': 1e6, 'B': 1e9}[m.group(2)]))
def fetch(handle, channel_id=None):
    out = {'handle': handle, 'channel_id': channel_id}
    try:
        h = get(f'https://www.youtube.com/@{handle}')
        if not channel_id:
            m = re.search(r'"externalId":"(UC[\w-]{22})"', h); out['channel_id'] = m and m.group(1)
        t = re.search(r'<meta property="og:title" content="([^"]*)"', h); out['name'] = t and H.unescape(t.group(1))
        s = re.search(r'"content":"([\d.,]+[KMB]?) subscribers?"', h); out['subscribers_text'] = s and s.group(1)
        out['subscribers'] = parse_count(s and s.group(1))
        v = re.search(r'"content":"([\d.,]+[KMB]?) videos?"', h); out['video_count'] = parse_count(v and v.group(1))
    except Exception as e:
        out['page_error'] = str(e)
    if not out.get('channel_id'):
        out['error'] = 'channel not found'; return out
    x = get(f'https://www.youtube.com/feeds/videos.xml?channel_id={out["channel_id"]}')
    root = ET.fromstring(x); vids = []
    for e in root.findall('a:entry', NS):
        vid = e.find('yt:videoId', NS).text; link = e.find('a:link', NS).get('href')
        st = e.find('media:group/media:community/media:statistics', NS); rt = e.find('media:group/media:community/media:starRating', NS)
        vids.append({'id': vid, 'title': e.find('a:title', NS).text, 'published': e.find('a:published', NS).text,
                     'url': link, 'short': '/shorts/' in link, 'views': int(st.get('views')) if st is not None else None,
                     'likes': int(rt.get('count')) if rt is not None and rt.get('count') else None,
                     'thumb': f'https://i.ytimg.com/vi/{vid}/hqdefault.jpg'})
    out['videos'] = vids
    if not out.get('name'):
        a = root.find('a:title', NS); out['name'] = a.text if a is not None else handle
    return out
if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--config', default='config.json'); ap.add_argument('--out', default='raw/youtube.json')
    ap.add_argument('handles', nargs='*'); a = ap.parse_args()
    if a.handles: items = [(h, None) for h in a.handles]
    else:
        c = json.load(open(a.config)); items = [(c['operator'], c.get('operator_channel_id'))] + [(w['handle'], w.get('channel_id')) for w in c['watchlist']]
    res = {'fetched_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'accounts': []}
    for h, cid in items:
        for attempt in range(3):
            try: r = fetch(h, cid); break
            except Exception as e: r = {'handle': h, 'channel_id': cid, 'error': str(e)}; time.sleep(3)
        res['accounts'].append(r)
        print(h, r.get('subscribers'), len(r.get('videos', [])), r.get('error', ''), file=sys.stderr, flush=True)
        time.sleep(0.5)
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    json.dump(res, open(a.out, 'w'), ensure_ascii=False, indent=1)
