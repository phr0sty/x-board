#!/usr/bin/env python3
"""Fetch public TikTok data from TikTok's official creator embed page (https://www.tiktok.com/embed/@handle).
Gives profile counts (followers, total likes) and the creator's ~13 featured/recent videos with play counts.
Video publish time is decoded from the video id (id >> 32 = unix seconds). Output: raw JSON."""
import re, json, sys, time, urllib.request, argparse
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36'
def fetch(handle):
    req = urllib.request.Request(f'https://www.tiktok.com/embed/@{handle}', headers={'User-Agent': UA, 'Accept-Language': 'en-US'})
    h = urllib.request.urlopen(req, timeout=20).read().decode('utf8', 'ignore')
    m = re.search(r'<script id="__FRONTITY_CONNECT_STATE__"[^>]*>(.*?)</script>', h, re.S)
    if not m: return {'handle': handle, 'error': 'no embed state'}
    d = json.loads(m.group(1))['source']['data']
    x = next((v for k, v in d.items() if k.lower().startswith('/embed/@')), None)
    if not x or x.get('isError') or not x.get('userInfo'): return {'handle': handle, 'error': 'not found or private'}
    u = x['userInfo']
    vids = []
    for v in x.get('videoList') or []:
        vid = str(v['id'])
        vids.append({'id': vid, 'desc': v.get('desc', ''), 'plays': v.get('playCount'),
                     'created': int(vid) >> 32, 'cover': v.get('coverUrl'),
                     'url': f'https://www.tiktok.com/@{u["uniqueId"]}/video/{vid}'})
    return {'handle': u['uniqueId'], 'name': u.get('nickname'), 'followers': u.get('followerCount'),
            'likes': u.get('heartCount'), 'following': u.get('followingCount'), 'private': u.get('privateAccount'),
            'verified': u.get('verified'), 'videos': vids}
if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--config', default='config.json'); ap.add_argument('--out', default='raw/tiktok.json')
    ap.add_argument('handles', nargs='*'); a = ap.parse_args()
    if a.handles: hs = a.handles
    else:
        c = json.load(open(a.config)); hs = [c['operator']] + [w['handle'] for w in c['watchlist']]
    res = {'fetched_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'accounts': []}
    for h in hs:
        for attempt in range(3):
            try: r = fetch(h); break
            except Exception as e: r = {'handle': h, 'error': str(e)}; time.sleep(3)
        res['accounts'].append(r)
        print(h, r.get('followers'), len(r.get('videos', [])), r.get('error', ''), file=sys.stderr, flush=True)
        time.sleep(0.5)
    import os; os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    json.dump(res, open(a.out, 'w'), ensure_ascii=False, indent=1)
