#!/usr/bin/env python3
"""Build data.json for the X Virality board from raw X API (MCP) responses.

Usage (from repo root):
  python3 scripts/build_data.py --day 2026-11-19 --fetched-at 2026-11-20T13:45:00Z \
      --users raw/users.json --posts raw/posts_snapshot.json \
      [--outsiders raw/outsiders.json] [--news raw/news.json]

Inputs are the JSON bodies returned by the x MCP tools (wrapper text around the
JSON is tolerated):
  --users      get_users_by_usernames for operator + watchlist (user.fields=public_metrics)
  --posts      get_posts_by_ids snapshot (or search_posts_all pages) for every original
               post (no replies / reposts) by operator + watchlist since D 00:00 MSK.
               May be given several times; later files win for the same id.
  --outsiders  get_posts_by_ids / search pages for non-watchlist AI posts of the last 48h
  --news       search_news result, or a JSON list of {name,url,updated_at,category}

Never invents numbers: every view/like count comes from the input files.
Updates data/ledger.json and leaderboard_ledger.json in place and writes data.json.
"""
import argparse, json, math, re, statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone

ROOT = __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__)))
P = lambda *a: __import__('os').path.join(ROOT, *a)

def load_json(path):
    t = open(path, encoding='utf-8').read()
    i = min([x for x in (t.find('{'), t.find('[')) if x >= 0])
    obj, _ = json.JSONDecoder(strict=False).raw_decode(t[i:])
    return obj

def as_list(o):
    if isinstance(o, list):
        return o
    return [o]

def fmt(n):
    n = n or 0
    if n >= 1e6: return f"{n/1e6:.2f}M".replace('.00M', 'M')
    if n >= 1e3: return (f"{n/1e3:.0f}K" if n >= 1e5 else f"{n/1e3:.1f}K").replace('.0K', 'K')
    return str(int(n))

def sgn(n):
    return ('+' if n >= 0 else '−') + f"{abs(n):,}"

def parse_ts(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00'))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--day', required=True, help='calendar day D in MSK, YYYY-MM-DD')
    ap.add_argument('--fetched-at', required=True, help='UTC ISO time the snapshot was taken')
    ap.add_argument('--users', required=True)
    ap.add_argument('--posts', action='append', default=[])
    ap.add_argument('--outsiders', action='append', default=[])
    ap.add_argument('--news')
    a = ap.parse_args()

    cfg = json.load(open(P('config.json')))
    MSK = timezone(timedelta(hours=cfg.get('utc_offset_hours', 3)))
    T5, T10 = cfg['hit_threshold'], cfg['star_threshold']
    op_user = cfg['operator']
    wl = cfg['watchlist']
    keys = [op_user.lower()] + [h.lower() for h in wl]

    fetched = parse_ts(a.fetched_at).astimezone(MSK)
    fetched_s = fetched.isoformat(timespec='seconds')
    day = a.day
    d0 = datetime.fromisoformat(day + 'T00:00:00').replace(tzinfo=MSK)
    d1 = d0 + timedelta(days=1)
    l24 = fetched - timedelta(hours=24)
    l48 = fetched - timedelta(hours=48)
    msk = lambda s: parse_ts(s).astimezone(MSK).isoformat(timespec='seconds')
    ddmm = lambda s: parse_ts(s).astimezone(MSK).strftime('%Y-%m-%d')  # ISO MSK date; UI formats per locale

    # ---------- ledgers ----------
    try:
        L = json.load(open(P('data', 'ledger.json')))
    except Exception:
        L = {}
    L.setdefault('tracking_start', cfg['tracking_start']); L.setdefault('timezone', cfg['timezone'])
    L.setdefault('threshold', T5); L.setdefault('days', {}); L.setdefault('posts', {}); L.setdefault('followers', {})
    L['schema'] = 'v1: days{date:{accounts}} · posts{id:{snapshots{ts:metrics}}} · followers{key:{history{ts:count}}}'

    # ---------- users / followers ----------
    U = load_json(a.users)
    users = {}
    for u in U.get('data', []):
        users[u['username'].lower()] = u
    followers = {}
    for k in keys:
        u = users.get(k)
        if not u:
            continue
        cnt = u['public_metrics']['followers_count']
        hist = L['followers'].setdefault(k, {'history': {}})['history']
        prev = None
        # previous value = latest history entry at least 12h older than now
        for ts in sorted(hist):
            if parse_ts(ts) <= fetched - timedelta(hours=12):
                prev = (ts, hist[ts])
        hist[fetched_s] = cnt
        fi = {'count': cnt, 'as_of': fetched_s, 'stale': False}
        if prev:
            fi['delta'] = cnt - prev[1]; fi['delta_since'] = prev[0]
        followers[k] = fi

    def handle_of(k):
        u = users.get(k)
        return '@' + (u['username'] if u else k)

    # ---------- posts ----------
    def collect(files):
        posts, inc_posts, inc_users, media = {}, {}, {}, {}
        for f in files:
            o = load_json(f)
            for x in as_list(o):
                inc = x.get('includes', {})
                for u in inc.get('users', []): inc_users[u['id']] = u
                for m in inc.get('media', []): media[m['media_key']] = m.get('type')
                for p in inc.get('posts', []) + inc.get('tweets', []): inc_posts[p['id']] = p
                for p in x.get('data', []) or []:
                    posts[p['id']] = p
        return posts, inc_posts, inc_users, media

    def norm(p, inc_posts, inc_users, media):
        u = inc_users.get(p.get('author_id'), {})
        uname = u.get('username') or (p.get('url', '').split('/')[3] if p.get('url') else '?')
        pm = p.get('public_metrics', {})
        text = (p.get('note_tweet') or {}).get('text') or p.get('text', '')
        art = (p.get('article') or {}).get('title')
        if art and re.fullmatch(r'\s*https?://\S+\s*', text or ''):
            text = 'Article: ' + art
        text = text.replace('&gt;', '>').replace('&lt;', '<').replace('&amp;', '&')
        mtypes = [media.get(k) for k in (p.get('attachments') or {}).get('media_keys', []) if media.get(k)]
        if mtypes:
            mn = '+'.join(sorted(set(mtypes))).replace('animated_gif', 'gif')
        elif art:
            mn = 'article'
        else:
            mn = 'text-only'
        q = next((r['id'] for r in p.get('referenced_tweets', []) or [] if r['type'] == 'quoted'), None)
        r = {
            'id': p['id'], 'key': uname.lower(), 'handle': '@' + uname, 'name': u.get('name', uname),
            'display_name': u.get('name', uname),
            'url': f"https://x.com/{uname}/status/{p['id']}", 'status_url': f"https://x.com/{uname}/status/{p['id']}",
            'posted_at': msk(p['created_at']), 'created_utc': p['created_at'],
            'views': pm.get('impression_count', 0), 'likes': pm.get('like_count', 0),
            'reposts': pm.get('repost_count', pm.get('retweet_count', 0)), 'replies': pm.get('reply_count', 0),
            'bookmarks': pm.get('bookmark_count', 0), 'media_note': mn,
            'text': text[:280], 'full_text': text, 'original_en': text,
            'hook': re.sub(r'\s+', ' ', re.sub(r'https://t\.co/\S+', '', text)).strip()[:200],
            'metrics_note': f'exact metrics from x MCP (impression_count) at fetch time {fetched_s}',
            'views_as_of': fetched_s, 'stale': False, 'is_quote': bool(q),
        }
        if q:
            r['quote_of_id'] = q
            qp = inc_posts.get(q)
            if qp:
                if qp.get('created_at'): r['quote_of_date'] = ddmm(qp['created_at'])
                if qp.get('author_id') and qp.get('author_id') == p.get('author_id'):
                    r['self_quote'] = True
        return r

    raw, ip, iu, md = collect(a.posts)
    allp = [norm(p, ip, iu, md) for p in raw.values()]
    allp = [p for p in allp if p['key'] in keys]
    seen_text = {}
    dups = []
    for p in sorted(allp, key=lambda p: p['created_utc']):
        sig = (p['key'], re.sub(r'\W+', '', p['full_text'].lower())[:200])
        if sig in seen_text and sig[1]:
            p['excluded_reason'] = 'duplicate'; dups.append(p)
        else:
            seen_text[sig] = p['id']

    # ledger snapshots for every post
    for p in allp:
        e = L['posts'].setdefault(p['id'], {'id': p['id'], 'handle': p['handle'], 'posted_at': p['posted_at'],
                                             'day': parse_ts(p['posted_at']).astimezone(MSK).strftime('%Y-%m-%d'), 'snapshots': {}})
        snaps = e['snapshots']
        prior = sorted(snaps.items())
        snaps[fetched_s] = {k: p[k] for k in ('views', 'likes', 'reposts', 'replies', 'bookmarks')}
        p['snapshots'] = len(snaps)
        if prior:
            p['views_first'] = prior[0][1]['views']; p['first_at'] = prior[0][0]
            p['growth_since_first'] = p['views'] - p['views_first']
            last = prior[-1]
            p['views_prev'] = last[1]['views']; p['views_delta'] = p['views'] - last[1]['views']; p['delta_since'] = last[0]
        else:
            p['views_first'] = p['views']; p['first_at'] = fetched_s; p['growth_since_first'] = 0
        fi = followers.get(p['key'])
        if fi: p['followers'] = fi
        p['is_you'] = p['key'] == op_user.lower()

    inday = lambda p: d0 <= parse_ts(p['posted_at']) < d1
    day_posts = [p for p in allp if inday(p) and not p.get('excluded_reason')]
    excluded = [p for p in allp if inday(p) and p.get('excluded_reason')]
    hits = sorted([p for p in day_posts if p['views'] >= T5], key=lambda p: -p['views'])
    for i, h in enumerate(hits):
        h['highlight'] = h['views'] >= T10; h['board_rank'] = i + 1

    # ---------- outsiders (virals) ----------
    oraw, oip, oiu, omd = collect(a.outsiders)
    virals = [norm(p, oip, oiu, omd) for p in oraw.values()]
    virals = [v for v in virals if v['key'] not in keys and parse_ts(v['posted_at']) >= l48 and v['views'] >= T5]
    virals.sort(key=lambda v: -v['views'])
    for i, v in enumerate(virals):
        v['highlight'] = v['views'] >= T10; v['board_rank'] = i + 1; v['is_you'] = False
        u = next((x for x in oiu.values() if x.get('username', '').lower() == v['key']), None)
        if u and u.get('public_metrics'):
            c = u['public_metrics']['followers_count']
            v['followers'] = {'count': c, 'as_of': fetched_s, 'stale': False}
        v['hook'] = v['handle'] + ': ' + v['hook']

    # ---------- trend keywords (from real post texts, >=5K views, >=2 authors) ----------
    STOP = set('''the a an and or of to in on for with is are was were be been it its this that these those you your i me my we our they their he she his her them
    just now new how what why when who all any can will not no yes do does did get got have has had more most than then there here from by at as if so but
    about into out up down one two three only like make made use used using every each over after before still want need know see dont doesnt isnt it's don't
    people thing things way day week time today year years really even much many very also back first last next free full real right big best top via
    here's that's you're i'm what's it’s don’t you’re here’s that’s i’m going gonna let lets let's other some same while because without within off own
    f*cking fucking shit holy damn ever never guy guys someone something everyone anyone nobody 1 2 3 4 5 6 7 8 9 10 →'''.split())
    COMMON = STOP | set('''this here stop most anyone imagine introducing meet phew today tried someone step steps paste give gave save says said watch look check build built turn turned whole hours minutes month job jobs work take put post below run code team three nobody'''.split())
    corpus = [p for p in allp if p['views'] >= T5 and parse_ts(p['posted_at']) >= l48] + virals
    LEX = set('''agent agents prompt prompts model models harness repo repos mcp skill skills video videos bot bots memory workflow workflows
    automation trading coding course plugin plugins api open-source local gpu benchmark leak lawsuit nda settlement'''.split())
    def uni_ok(w):
        return (w.lower() in LEX) or any(c.isupper() for c in w[1:]) or any(c.isdigit() for c in w) or (w[0].isupper() and w.lower() not in COMMON)
    def grams(text):
        t = re.sub(r'https?://\S+', ' ', text).replace('’', "'")
        t = re.sub(r"\S*\*\S*", ' ', t)  # drop censored words like f*cking
        toks = re.findall(r"[A-Za-z][A-Za-z0-9\.\-\+']*[A-Za-z0-9\+]|[A-Za-z]", t)
        toks = [x.strip(".'") for x in toks]
        out = set()
        for i, w in enumerate(toks):

            if w.lower() not in STOP and len(w) > 2 and uni_ok(w):
                out.add(w)
            if i + 1 < len(toks):
                w2 = toks[i + 1]
                if w.lower() not in STOP and w2.lower() not in STOP and (uni_ok(w) or uni_ok(w2)) and (w[0].isupper() or any(c.isdigit() for c in w2) or w2.lower() in LEX):
                    out.add(w + ' ' + w2)
        return out
    agg = defaultdict(lambda: {'posts': set(), 'authors': set(), 'score': 0.0, 'forms': defaultdict(int)})
    for p in corpus:
        for g in grams(p['full_text']):
            k = g.lower()
            e = agg[k]
            if p['id'] in e['posts']: continue
            e['posts'].add(p['id']); e['authors'].add(p['key']); e['score'] += math.log10(max(p['views'], 10)); e['forms'][g] += 1
    kws = []
    for k, e in agg.items():
        if len(e['authors']) < 2: continue
        form = max(e['forms'].items(), key=lambda x: x[1])[0]
        bonus = 1.3 if ' ' in k else 1.0
        kws.append({'keyword': form, 'score': round(e['score'] * len(e['authors']) * bonus, 1), 'posts': len(e['posts']), 'authors': len(e['authors'])})
    kws.sort(key=lambda x: -x['score'])
    # drop unigrams fully contained in a higher-ranked bigram with the same post set
    final = []
    for k in kws:
        if ' ' not in k['keyword'] and any(k['keyword'].lower() in f['keyword'].lower().split() and f['posts'] == k['posts'] for f in final):
            continue
        final.append(k)
        if len(final) >= 40: break
    for i, k in enumerate(final): k['rank'] = i + 1

    def why(p):
        low = p['full_text'].lower()
        matched = [k for k in final if re.search(r'(?<![a-z0-9])' + re.escape(k['keyword'].lower()) + r'(?![a-z0-9])', low)]
        prod = 1.0
        for k in matched:
            w = 0.35 if k['rank'] <= 10 else 0.22 if k['rank'] <= 25 else 0.12
            prod *= (1 - w)
        tm = round(100 * (1 - prod))
        media = 'video' if 'video' in p['media_note'] else 'image' if ('photo' in p['media_note'] or 'gif' in p['media_note']) else p['media_note'].replace('text-only', 'text')
        verdict = 'trend' if tm >= 50 else ('visual' if media in ('video', 'image') else 'audience')
        return {'trend_match': tm, 'verdict': verdict, 'matched_keywords': [k['keyword'] for k in matched][:5], 'media': media, 'note': '', 'topic': ''}
    for p in hits + virals:
        p['why_hit'] = why(p)

    # ---------- roster / you_rank ----------
    roster = []
    for k in keys:
        ps = [p for p in day_posts if p['key'] == k]
        best = max(ps, key=lambda p: p['views']) if ps else None
        hp = [p for p in ps if p['views'] >= T5]
        r = {'handle': handle_of(k), 'name': (users.get(k) or {}).get('name', k), 'views': best['views'] if best else 0,
             'total_views': sum(p['views'] for p in ps), 'hit': bool(hp), 'is_you': k == op_user.lower(),
             'best_url': best['url'] if best else None, 'stale': False, 'posts': len(ps), 'hits': len(hp)}
        if k in followers: r['followers'] = followers[k]
        roster.append(r)
    roster.sort(key=lambda r: (-r['views'], -r['total_views']))
    me = next(r for r in roster if r['is_you'])
    my_posts = sorted([p for p in day_posts if p['key'] == op_user.lower()], key=lambda p: -p['views'])
    you_rank = {
        'date': day, 'best_views': me['views'] if my_posts else None, 'total_views': me['total_views'], 'best_url': me['best_url'],
        'rank_among_watchlist': roster.index(me) + 1, 'total_accounts': len(roster),
        'vs_5k': 'done' if me['views'] >= T5 else 'pending', 'vs_10k': 'done' if me['views'] >= T10 else 'pending',
        'best_incl_self': me['views'], 'best_incl_self_url': me['best_url'], 'self_quotes': 0,
        'self_quotes_counted': sum(1 for p in my_posts if p.get('self_quote')),
        'posts': [{k: p.get(k) for k in ('url', 'views', 'views_as_of', 'likes', 'reposts', 'replies', 'bookmarks', 'posted_at', 'is_quote')} for p in my_posts],
        'views_as_of': fetched_s, 'followers': followers.get(op_user.lower()),
        'no_posts': not my_posts,
    }

    no_hits = []
    for r in roster:
        if r['hit'] or r['is_you']: continue
        nh = {'handle': r['handle'], 'reason_code': 'no_posts' if r['posts'] == 0 else 'below_floor', 'max_views': r['views'], 'posts': r['posts']}
        if 'followers' in r: nh['followers'] = r['followers']
        no_hits.append(nh)

    # ---------- day ledger + leaderboards ----------
    accts = {}
    for k in keys:
        hp = [p for p in hits if p['key'] == k]
        if not hp: continue
        b = max(hp, key=lambda p: p['views'])
        accts[k] = {'handle': handle_of(k), 'name': b['name'], 'hits': len(hp), 'best': b['views'], 'total': sum(p['views'] for p in hp),
                    'best_url': b['url'], 'post_ids': [p['id'] for p in hp], 'best_as_of': fetched_s, 'best_stale': False}
    L['days'][day] = {'accounts': accts}
    # refresh older days' totals from latest snapshots of their posts
    for dd, dv in L['days'].items():
        for k, e in dv['accounts'].items():
            vs = []
            for pid in e.get('post_ids', []):
                s = L['posts'].get(pid, {}).get('snapshots', {})
                if s: vs.append((s[max(s)]['views'], pid, max(s)))
            if vs:
                e['total'] = sum(v for v, _, _ in vs); bv = max(vs); e['best'] = bv[0]; e['best_as_of'] = bv[2]
                e['best_url'] = f"https://x.com/{e['handle'].lstrip('@')}/status/{bv[1]}"
    L['last_refresh'] = fetched_s
    LB = {'tracking_start': L['tracking_start'], 'timezone': L['timezone'], 'threshold': T5,
          'days': {dd: {'accounts': {k: {x: e[x] for x in ('handle', 'name', 'hits', 'best', 'total', 'best_url')} for k, e in dv['accounts'].items()}} for dd, dv in L['days'].items()}}

    def board(days):
        agg = {}
        for dd in days:
            for k, e in L['days'].get(dd, {}).get('accounts', {}).items():
                a_ = agg.setdefault(k, {'handle': e['handle'], 'name': e['name'], 'hits': 0, 'days': 0, 'views': 0, 'best': 0, 'best_url': None,
                                        'best_as_of': e.get('best_as_of'), 'best_stale': False, 'is_you': k == op_user.lower()})
                a_['hits'] += e['hits']; a_['days'] += 1; a_['views'] += e['total']
                if e['best'] > a_['best']: a_['best'] = e['best']; a_['best_url'] = e['best_url']; a_['best_as_of'] = e.get('best_as_of')
        out = sorted(agg.values(), key=lambda x: (-x['views'], -x['best']))
        for e in out:
            k = e['handle'].lstrip('@').lower()
            if k in followers: e['followers'] = followers[k]
        return out
    tracked = sorted(L['days'])
    dD = datetime.fromisoformat(day).date()
    week_days = [d for d in tracked if (dD - datetime.fromisoformat(d).date()).days in range(0, 7)]
    month_days = [d for d in tracked if d[:7] == day[:7] and d <= day]
    leaderboards = {
        'as_of': day, 'tracking_start': L['tracking_start'], 'days_included': week_days, 'month_days_included': month_days,
        'computed_from': 'latest refreshed views per post; same-text duplicates excluded (self-quotes count)', 'views_as_of': fetched_s,
        'week': {'range': [week_days[0], week_days[-1]], 'entries': board(week_days)},
        'month': {'range': [month_days[0], month_days[-1]], 'entries': board(month_days)},
    }
    all_time = {'range': [tracked[0], tracked[-1]], 'entries': board(tracked)}

    # ---------- yesterday (D-1 posts, growth over ~24h from ledger) ----------
    yday = (dD - timedelta(days=1)).isoformat()
    yh = []
    for k, e in L['days'].get(yday, {}).get('accounts', {}).items():
        for pid in e.get('post_ids', []):
            s = L['posts'].get(pid, {}).get('snapshots', {})
            ts = sorted(s)
            if len(ts) < 2: continue
            cur = s[ts[-1]]
            base_ts = min(ts[:-1], key=lambda t: abs((parse_ts(ts[-1]) - parse_ts(t)).total_seconds() - 86400))
            g = cur['views'] - s[base_ts]['views']
            hrs = round((parse_ts(ts[-1]) - parse_ts(base_ts)).total_seconds() / 3600)
            yh.append({'id': pid, 'handle': e['handle'], 'name': e['name'], 'url': f"https://x.com/{e['handle'].lstrip('@')}/status/{pid}",
                       'is_you': k == op_user.lower(), 'views': cur['views'], 'views_as_of': ts[-1], 'snapshots': len(ts), 'stale': False,
                       'g24': g, 'g24_since': base_ts, 'g24_hours': hrs,
                       'posted_at': L['posts'][pid].get('posted_at'), 'followers': followers.get(k)})
    yh.sort(key=lambda h: -(h['g24'] or 0))
    yesterday = {'date': yday, 'refreshed_at': fetched_s,
                 'hits': yh, 'total_views': sum(h['views'] for h in yh), 'total_g24': sum(h['g24'] for h in yh), 'excluded': 0,
                 'needs_second_snapshot': not yh}

    # ---------- last 24h ----------
    lp = sorted([p for p in allp if parse_ts(p['posted_at']) >= l24 and not p.get('excluded_reason')], key=lambda p: -p['views'])
    for p in lp:
        p['age_h'] = round((fetched - parse_ts(p['posted_at'])).total_seconds() / 3600, 1)
        p['hit'] = p['views'] >= T5; p['star'] = p['views'] >= T10
    last24h = {'start': l24.isoformat(timespec='seconds'), 'end': fetched_s, 'fetched_at': fetched_s,
               'scope': 'operator+watchlist; replies and reposts excluded', 'posts': lp,
               'hits_count': sum(1 for p in lp if p['hit']), 'star_count': sum(1 for p in lp if p['star']), 'excluded': 0,
               'total_views': sum(p['views'] for p in lp)}

    # ---------- narrative-free summaries (computed only) ----------
    patterns = [{'keyword': k['keyword'], 'authors': k['authors']} for k in final[:6]]
    tm = [p for p in hits if p['why_hit']['verdict'] == 'trend']
    med = lambda xs: int(statistics.median(xs)) if xs else 0
    verd = defaultdict(int)
    for p in hits + virals: verd[p['why_hit']['verdict']] += 1
    news = []
    if a.news:
        n = load_json(a.news)
        n = n.get('data', []) if isinstance(n, dict) else n
        news = [{'name': x.get('name'), 'url': x.get('url'), 'updated_at': x.get('updated_at'), 'category': x.get('category')} for x in n]
    trend_radar = {
        'date': day, 'title': 'Trend radar',
        'window': {'end': fetched_s, 'start24': l24.isoformat(timespec='seconds'), 'start48': l48.isoformat(timespec='seconds')},
        'corpus': {'posts': len(corpus), 'min_views': T5, 'lanes': {'watchlist': len(corpus) - len(virals), 'outsider': len(virals)}},
        'summary': {
            'date': day, 'hits': len(hits), 'trend_hits': len(tm),
            'median_trend': med([p['views'] for p in tm]), 'median_other': med([p['views'] for p in hits if p not in tm]),
            'top_keywords': [k['keyword'] for k in final[:5]],
            'stats': {'all': {'n': len(hits) + len(virals), 'verdicts': dict(verd)}},
        },
        'topics': [], 'ideas': [], 'articles': [],
        'why_hit': [{'id': p['id'], 'handle': p['handle'], 'lane': 'outsider' if p in virals else 'watchlist', 'views': p['views'], **p['why_hit']} for p in hits + virals],
        'news': news,  # legend text lives in i18n.js (key legend_text)
    }

    def strip(p):
        return {k: v for k, v in p.items() if k not in ('key', 'created_utc')}

    hits_out = [strip(p) for p in hits]
    data = {
        'title': 'X Digest Board', 'brand_title': cfg['brand_title'], 'brand_handle': '@' + op_user,
        'date': day, 'timezone': cfg['timezone'], 'updated': fetched_s,
        'hits': hits_out, 'virals': [strip(v) for v in virals], 'outsiders': [strip(v) for v in virals],
        'outsiders_count': len(virals), 'virals_target': cfg['virals_target'],
        'virals_window': f"last ~48h (posts since {l48.strftime('%d %b %Y %H:%M')} MSK)",
        'virals_narrative': '', 'narrative_synthesis': '',
        'patterns': patterns, 'no_hits': no_hits,
        'watchlist_brief': {'intro': '', 'recurring_names': [], 'structures': [], 'phrases': [], 'draft_rules': []},
        'hits_count': len(hits), 'hits_count_raw': len(hits) + len(excluded), 'star_count': sum(1 for p in hits if p['highlight']),
        'operator': {'handle': '@' + op_user, 'name': (users.get(op_user.lower()) or {}).get('name', cfg.get('operator_name', op_user)),
                     'profile_url': f'https://x.com/{op_user}', 'followers': followers.get(op_user.lower())},
        'day_roster': roster, 'you_rank': you_rank, 'leaderboards': leaderboards, 'yesterday': yesterday, 'all_time': all_time,
        'followers': followers,
        'refresh': {'ts': fetched_s, 'requested': len(allp), 'refreshed': len(allp), 'stale_this_fetch': 0, 'stale_total': 0, 'stale_failed': 0,
                    'stale_age': None, 'stale': 0, 'followers': len(followers), 'stale_ids': [], 'note': 'single snapshot via x MCP get_posts_by_ids'},
        'window': {'type': 'calendar_day', 'date': day, 'start': d0.isoformat(), 'end': d1.isoformat(), 'views_as_of': fetched_s,
                   'views_basis': 'lifetime_at_snapshot'},
        'excluded_hits': [strip(p) for p in excluded],
        'exclusions': {'self_quotes': 0, 'self_quotes_counted': sum(1 for p in hits if p.get('self_quote')), 'duplicates': len(excluded),
                       'promoted_near_miss': [], 'rule': 'self_quotes_counted_duplicates_excluded'},
        'last24h': last24h,
        'trend_keywords': {'date': day, 'window': 'D hits + last-24h posts ≥5k + outsiders (48h)',
                           'method': 'sum(log10 views) over distinct posts × author count × 1.3 for 2-word phrases; ≥2 authors', 'keywords': final[:25]},
        'trend_radar': trend_radar,
        'drafts_top10': [], 'experiment': None, 'trend_input_only_posts': [],
    }
    json.dump(data, open(P('data.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
    json.dump(L, open(P('data', 'ledger.json'), 'w'), ensure_ascii=False)
    json.dump(LB, open(P('leaderboard_ledger.json'), 'w'), ensure_ascii=False)
    print(json.dumps({'day': day, 'posts': len(allp), 'day_posts': len(day_posts), 'hits': len(hits), 'virals': len(virals),
                      'last24h': len(lp), 'keywords': len(final), 'you_rank': you_rank['rank_among_watchlist']}, ensure_ascii=False))

if __name__ == '__main__':
    main()
