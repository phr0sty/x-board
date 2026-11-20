#!/usr/bin/env python3
"""Fetch public Instagram data that is reachable without logging in: the profile link preview
(og:description = followers / following / posts) and, for any post URLs listed in config.json
"tracked_posts", the post link preview (likes, comments, date, caption).
Instagram does not expose per-post views, Reels plays or the recent-post list without a login;
those fields are reported as unavailable. Instagram rate-limits these previews, so the script
backs off and records failures instead of guessing."""
import re, json, sys, time, urllib.request, argparse, html as H, os
UA = 'facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)'
def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en-US'}), timeout=20).read().decode('utf8', 'ignore')
def num(s):
    s = s.replace(',', ''); m = re.match(r'([\d.]+)([KMB]?)', s)
    return int(round(float(m.group(1)) * {'': 1, 'K': 1e3, 'M': 1e6, 'B': 1e9}[m.group(2)])) if m else None
def og(h):
    m = re.search(r'<meta property="og:description" content="([^"]*)"', h); return H.unescape(m.group(1)) if m else None
def profile(u):
    d = og(get(f'https://www.instagram.com/{u}/'))
    if not d: return {'handle': u, 'error': 'no preview (rate-limited or not found)'}
    m = re.match(r'([\d.,]+[KMB]?) Followers, ([\d.,]+[KMB]?) Following, ([\d.,]+[KMB]?) Posts - See Instagram photos and videos from (.*?) \(@([\w.]+)\)', d)
    if not m: return {'handle': u, 'error': 'unrecognised preview', 'raw': d[:200]}
    return {'handle': m.group(5), 'name': m.group(4).strip() or m.group(5), 'followers': num(m.group(1)), 'following': num(m.group(2)), 'posts_count': num(m.group(3))}
def post(url):
    d = og(get(url))
    if not d: return {'url': url, 'error': 'no preview'}
    m = re.match(r'([\d.,]+[KMB]?) likes?, ([\d.,]+[KMB]?) comments? - ([\w.]+) on (\w+ \d+, \d{4}): "?(.*)', d, re.S)
    if not m: return {'url': url, 'error': 'unrecognised preview', 'raw': d[:200]}
    return {'url': url, 'likes': num(m.group(1)), 'comments': num(m.group(2)), 'handle': m.group(3),
            'date': time.strftime('%Y-%m-%d', time.strptime(m.group(4), '%B %d, %Y')), 'caption': m.group(5).rstrip('"').strip()}
def retry(fn, arg):
    r = None
    for wait in (0, 10, 30):
        time.sleep(wait)
        try: r = fn(arg)
        except Exception as e: r = {'error': str(e)}
        if 'error' not in r: return r
    r.setdefault('handle' if fn is profile else 'url', arg); return r
if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--config', default='config.json'); ap.add_argument('--out', default='raw/instagram.json')
    ap.add_argument('handles', nargs='*'); a = ap.parse_args()
    posts = []
    if a.handles: hs = a.handles
    else:
        c = json.load(open(a.config)); hs = [c['operator']] + [w['handle'] for w in c['watchlist']]; posts = c.get('tracked_posts', [])
    def save(path, obj):
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True); json.dump(obj, open(path, 'w'), ensure_ascii=False, indent=1)
    res = {'fetched_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'accounts': [], 'posts': []}
    for h in hs:
        r = retry(profile, h); res['accounts'].append(r); save(a.out, res)
        print(h, r.get('followers'), r.get('error', ''), file=sys.stderr, flush=True); time.sleep(4)
    failed = [i for i, r in enumerate(res['accounts']) if 'error' in r]
    if failed:  # one slower second pass for accounts that hit the rate limit
        time.sleep(60)
        for i in failed:
            r = retry(profile, hs[i])
            if 'error' not in r: res['accounts'][i] = r; save(a.out, res)
            print('retry', hs[i], r.get('followers'), r.get('error', ''), file=sys.stderr, flush=True); time.sleep(6)
    for p in posts:
        r = retry(post, p); res['posts'].append(r)
        print(p, r.get('likes'), r.get('error', ''), file=sys.stderr, flush=True); time.sleep(4)
    save(a.out, res)
