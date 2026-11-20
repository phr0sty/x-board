#!/usr/bin/env python3
"""Build <platform>/data.json for the Instagram / TikTok / YouTube boards from the raw fetch output.
Every number comes from the raw files; a metric the platform does not expose stays null and is
listed in data.json -> limits. Content ideas are read from <platform>/ideas.json (hand-written drafts).

  python3 scripts/social/build_social.py --platform youtube   --board youtube   --raw youtube/raw/youtube.json
  python3 scripts/social/build_social.py --platform tiktok    --board tiktok    --raw tiktok/raw/tiktok.json
  python3 scripts/social/build_social.py --platform instagram --board instagram --raw instagram/raw/instagram.json \
          --signals tiktok/data.json --signals youtube/data.json
"""
import json, re, math, time, argparse, statistics, os, datetime as dt
from collections import defaultdict

URL = {'youtube': 'https://www.youtube.com/@{}', 'tiktok': 'https://www.tiktok.com/@{}', 'instagram': 'https://www.instagram.com/{}/'}
WINDOW_DAYS = {'youtube': 7, 'tiktok': 30, 'instagram': 30}
FORMATS = [  # first match wins
    ('gear', r'\breview\b|first look|unbox|\bvs\.?\b|hands.on|plugin|\bvst\b|\blabs\b'),
    ('tutorial', r'how to|how do|tips?\b|learn|wrong|secret|hack|explain|guide|you.?re doing|fix(es)?\b|theory|must know|make the most'),
    ('build', r'\bdiy\b|breadboard|wiring|circuit|soldering|built|i made|electronics'),
    ('transition', r'transition|mashup|\bmix(es|ing)?\b|\bedit\b|remix|backspin|scratch'),
    ('gear', r'test|demo|synth|controller|pedal|\bmpc\b|interface|drum machine|sampler|instrument|update|clone|xdj|cdj|ddj|\bpush\b|rekordbox|serato|traktor|ableton|\bdaw\b'),
    ('live', r'boiler room|\blive\b|\bset\b|tour|festival|crowd|last night|coachella|edc|creamfields|tomorrowland|\bshow\b|stage'),
    ('release', r'out now|introducing|album|release|\bsale\b|presale|available|launch'),
]
STOP = set('the a an and or of to in on for with is it this that my your you i we our at by from be are was its it’s it\'s me us as so just now new out up how what why all not no but get got can will one more most like do does did has have had ever about into over than then there their they them he she his her if when who were been being way really very only also back here off too much any some link bio full video thank thanks time happy watch today tonight yall guys check'.split())

def fmt_of(text):
    for k, rx in FORMATS:
        if re.search(rx, text or '', re.I): return k
    return 'other'

def iso(ts): return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def items_for(platform, acc):
    """Normalise each account's posts to {id,title,url,thumb,views,likes,comments,created(ts),short}."""
    out = []
    for v in acc.get('videos', []) or []:
        if platform == 'youtube':
            ts = dt.datetime.fromisoformat(v['published']).timestamp()
            out.append({'id': v['id'], 'title': v['title'], 'url': v['url'], 'thumb': v.get('thumb'), 'views': v.get('views'),
                        'likes': v.get('likes'), 'comments': None, 'created': ts, 'short': bool(v.get('short'))})
        else:
            out.append({'id': v['id'], 'title': v.get('desc') or '', 'url': v['url'], 'thumb': v.get('cover'), 'views': v.get('plays'),
                        'likes': None, 'comments': None, 'created': v['created'], 'short': True})
    return out

def keywords(posts, top=20):
    score, authors = defaultdict(float), defaultdict(set)
    for p in posts:
        words = [w for w in re.findall(r"[a-z0-9][a-z0-9'’\-]{2,}", re.sub(r'https?://\S+|[@#]\w+', ' ', p['title'].lower())) if w not in STOP and not w.isdigit()]
        for w in set(words):
            score[w] += math.log10(max(p['views'] or 1, 10)); authors[w].add(p['handle'])
    rows = [{'k': w, 'score': round(s * len(authors[w]), 2), 'authors': len(authors[w])} for w, s in score.items() if len(authors[w]) >= 2]
    return sorted(rows, key=lambda r: -r['score'])[:top]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--platform', required=True, choices=['youtube', 'tiktok', 'instagram'])
    ap.add_argument('--board', required=True, help='board folder containing config.json / ideas.json')
    ap.add_argument('--raw', required=True); ap.add_argument('--signals', action='append', default=[])
    a = ap.parse_args(); P = a.platform
    cfg = json.load(open(os.path.join(a.board, 'config.json'))); raw = json.load(open(a.raw))
    ideas_path = os.path.join(a.board, 'ideas.json'); ideas = json.load(open(ideas_path)) if os.path.exists(ideas_path) else {'ideas': []}
    fetched = dt.datetime.fromisoformat(raw['fetched_at'].replace('Z', '+00:00')).timestamp()
    win = WINDOW_DAYS[P]; start = fetched - win * 86400
    op_handle = cfg['operator'].lower()
    accounts, all_posts = [], []
    for acc in raw['accounts']:
        h = acc.get('handle'); posts = items_for(P, acc)
        for p in posts:
            p.update(handle=h, name=acc.get('name') or h, format=fmt_of(p['title']),
                     age_h=round((fetched - p['created']) / 3600, 1))
            p['vph'] = round(p['views'] / max(p['age_h'], 1), 1) if p['views'] is not None else None
            p['created_iso'] = iso(p['created'])
        inwin = [p for p in posts if p['created'] >= start and p['views'] is not None]
        accounts.append({'handle': h, 'name': acc.get('name') or h, 'url': URL[P].format(h), 'is_operator': (h or '').lower() == op_handle,
                         'followers': acc.get('subscribers') if P == 'youtube' else acc.get('followers'),
                         'posts_count': acc.get('video_count') if P == 'youtube' else acc.get('posts_count'),
                         'likes_total': acc.get('likes') if P == 'tiktok' else None,
                         'posts_window': len(inwin) if P != 'instagram' else None,
                         'best_views': max((p['views'] for p in inwin), default=None) if P != 'instagram' else None,
                         'total_views': sum(p['views'] for p in inwin) if inwin else (0 if P != 'instagram' and not acc.get('error') else None),
                         'error': acc.get('error')})
        all_posts += posts
    watch = [p for p in all_posts if p['handle'].lower() != op_handle]
    inwin = [p for p in watch if p['created'] >= start and p['views'] is not None]
    def capped(rows, per, n):  # keep the list varied: at most `per` posts per creator
        seen, out = defaultdict(int), []
        for p in rows:
            if seen[p['handle']] < per: out.append(p); seen[p['handle']] += 1
            if len(out) >= n: break
        return out
    hot = capped(sorted(inwin, key=lambda p: -(p['vph'] or 0)), 2, 24)
    top_views = capped(sorted(inwin, key=lambda p: -p['views']), 3, 12)
    evergreen = sorted([p for p in watch if p['views'] is not None], key=lambda p: -p['views'])[:10]
    roster = sorted([x for x in accounts if not x['is_operator']], key=lambda x: (-(x['best_views'] or -1), -(x['followers'] or -1)))
    for i, r in enumerate(roster, 1): r['rank'] = i
    fm = defaultdict(list)
    for p in inwin: fm[p['format']].append(p['views'])
    formats = sorted([{'key': k, 'count': len(v), 'avg_views': int(statistics.mean(v)), 'median_views': int(statistics.median(v))} for k, v in fm.items()], key=lambda r: -r['median_views'])
    op_acc = next((x for x in accounts if x['is_operator']), None); op_raw = next((x for x in raw['accounts'] if (x.get('handle') or '').lower() == op_handle), {})
    op_posts = [p for p in all_posts if p['handle'].lower() == op_handle]
    if P == 'tiktok' and op_raw.get('error'): status = 'private'
    elif op_raw.get('error'): status = 'unavailable'
    elif P != 'instagram' and not op_posts: status = 'empty'
    else: status = 'ok'
    views = [p['views'] for p in inwin]
    data = {
        'platform': P, 'niche': cfg.get('niche'), 'updated': iso(time.time()), 'fetched_at': raw['fetched_at'], 'window_days': win,
        'operator': {'handle': cfg['operator'], 'url': URL[P].format(cfg['operator']), 'status': status, 'note': cfg.get('operator_note') or cfg.get('operator_verified'),
                     'name': (op_acc or {}).get('name'), 'followers': (op_acc or {}).get('followers'), 'posts_count': (op_acc or {}).get('posts_count'),
                     'likes_total': (op_acc or {}).get('likes_total'), 'posts': sorted(op_posts, key=lambda p: -p['created'])[:10]},
        'metrics': {'views': P != 'instagram', 'likes': P == 'youtube', 'comments': False, 'followers': True, 'post_list': P != 'instagram'},
        'summary': {'accounts': len(roster), 'accounts_ok': sum(1 for r in roster if not r['error']), 'posts_window': len(inwin),
                    'views_window': sum(views) if views else None, 'median_views': int(statistics.median(views)) if views else None,
                    'top_views': max(views) if views else None, 'over_100k': sum(1 for v in views if v >= 100000),
                    'over_1m': sum(1 for v in views if v >= 1000000), 'followers_total': sum(r['followers'] or 0 for r in roster)},
        'hot': hot, 'top_views': top_views, 'evergreen': evergreen, 'roster': roster, 'formats': formats,
        'keywords': keywords(inwin), 'ideas': ideas.get('ideas', []), 'ideas_updated': ideas.get('updated'),
        'sources': {'youtube': ['Public channel page (subscriber + video counts)', 'Official channel RSS feed: latest 15 uploads with view counts'],
                    'tiktok': ['TikTok official creator embed (tiktok.com/embed/@handle): followers, total likes, ~10-13 featured/recent videos with play counts', 'Post time decoded from the video id'],
                    'instagram': ['Instagram public link preview of each profile: followers, following, post count']}[P],
        'limits': {'youtube': ['Only the latest 15 uploads per channel are visible (RSS limit).', 'Comment counts are not in the feed.', 'Views are lifetime totals at fetch time.'],
                   'tiktok': ['Private accounts expose nothing, including the operator account while it is private.', 'The embed shows ~10-13 videos per creator (featured + recent), not the full feed.', 'Likes, comments and shares per video are not in the embed.'],
                   'instagram': ['Instagram hides per-post views, Reels plays, likes and the recent-post list from logged-out visitors; only profile totals are reachable.', 'Instagram rate-limits link previews; failed accounts show as unavailable for that run.', '"Signals" are real TikTok / YouTube Shorts numbers from the sibling boards, used as a proxy for what short-form music video is working right now.']}[P],
    }
    if P == 'instagram':
        sig = []
        for s in a.signals:
            try: d = json.load(open(s))
            except Exception: continue
            for p in d.get('hot', []):
                if p.get('short'): sig.append(dict(p, source=d['platform']))
        by_src = defaultdict(list)  # sibling lists are already capped per creator; interleave sources
        for p in sorted(sig, key=lambda p: -(p['vph'] or 0)): by_src[p['source']].append(p)
        mixed = [x for pair in __import__('itertools').zip_longest(*by_src.values()) for x in pair if x]
        data['signals'] = mixed[:12]
        data['tracked_posts'] = [p for p in raw.get('posts', []) if not p.get('error')]
        fm2 = defaultdict(list)
        for p in sig: fm2[p['format']].append(p['views'])
        data['formats'] = sorted([{'key': k, 'count': len(v), 'avg_views': int(statistics.mean(v)), 'median_views': int(statistics.median(v))} for k, v in fm2.items()], key=lambda r: -r['median_views'])
        # Instagram previews are rate-limited: carry an account's last successfully read counts forward
        # (marked with stale_from = the fetch time they were read) instead of dropping it.
        prev = {}
        try:
            old = json.load(open(os.path.join(a.board, 'data.json')))
            prev = {r['handle'].lower(): r for r in old.get('roster', []) + [old.get('operator') or {}] if r.get('handle') and r.get('followers') is not None}
            prev_time = old.get('fetched_at')
        except Exception: prev_time = None
        for x in accounts:
            pr = prev.get((x['handle'] or '').lower())
            if x['followers'] is None and pr:
                x.update(followers=pr['followers'], posts_count=pr.get('posts_count'), name=pr.get('name') or x['name'], stale_from=pr.get('stale_from') or prev_time)
        if data['operator']['followers'] is None and op_acc and op_acc.get('followers') is not None:
            data['operator'].update(followers=op_acc['followers'], posts_count=op_acc['posts_count'], status='ok')
        data['roster'] = sorted([x for x in accounts if not x['is_operator']], key=lambda x: -(x['followers'] or -1))
        for i, r in enumerate(data['roster'], 1): r['rank'] = i
        fol = [r['followers'] for r in data['roster'] if r['followers']]
        data['summary'].update(accounts_ok=len(fol), followers_total=sum(fol), median_followers=int(statistics.median(fol)) if fol else None)
    out = os.path.join(a.board, 'data.json'); json.dump(data, open(out, 'w'), ensure_ascii=False, indent=1)
    s = data['summary']; print(f"{P}: {s['accounts_ok']}/{s['accounts']} accounts, {s['posts_window']} posts in {win}d, top {s['top_views']}, operator {status} -> {out}")
main()
