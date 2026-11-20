# Daily refresh procedure

This board tracks **@kkkkkkkkj22** against the watchlist in `config.json`.
A daily run (an agent with the `x` MCP connector and GitHub write access) regenerates
`data.json`, rolls the ledgers, and pushes one commit. Nothing is ever posted to X.

## 0. Schedule and time window

* Run once a day at about **10:50 MSK (07:50 UTC)**.
* **D** = yesterday's calendar day in MSK (Europe/Moscow, UTC+3).
  Window = `D 00:00 MSK` → `D+1 00:00 MSK` = `D-1T21:00:00Z` → `DT21:00:00Z`.
* Views are lifetime totals at snapshot time (`impression_count`), not views gained that day.
* Budget: X MCP allows 30 reads/min, 1000/day, max 25 results per search call. A normal
  run takes about 10 calls.

## 1. Fetch (x MCP tools). Save each raw JSON response to `raw/` (raw/ is not committed)

| # | Tool | Arguments | Save as |
|---|------|-----------|---------|
| 1 | `get_users_by_usernames` | `usernames` = operator + every watchlist handle from `config.json`; `user.fields=[public_metrics,name,username]` | `raw/users.json` |
| 2 | `search_posts_all` (page until `meta.next_token` is absent or `result_count` is 0) | `query` = `(from:kkkkkkkkj22 OR from:<each watchlist handle>) -is:retweet -is:reply`; `start_time` = `D-1T21:00:00Z` (window start; this also covers the last-24h tab); `end_time` = now minus 1 min; `max_results=25`; `sort_order=recency`; `post.fields=[created_at,public_metrics,author_id]`; `expansions=[author_id]` | `raw/search_pN.json` |
| 3 | `get_posts_by_ids` (≤100 ids per call) | every id from step 2 **plus** every post id still listed in `data/ledger.json` → `days[D-1]` (so yesterday's hits get their 24h growth); `post.fields=[created_at,public_metrics,author_id,referenced_posts,attachments,text,article]`; `expansions=[author_id,attachments.media_keys,referenced_posts]`; `media.fields=[type]`; `user.fields=[username,name]` | `raw/posts_snapshot.json` |
| 4 | Outsiders: take `includes.posts` from step 3 whose author is not on the watchlist and whose `created_at` is within the last 48h, plus up to 25 results of `search_posts_all` with `query` = `(AI OR Claude OR ChatGPT OR OpenAI OR Anthropic OR Grok OR Gemini OR "AI agent" OR LLM) -is:retweet -is:reply lang:en`, `sort_order=relevancy`, `start_time` = now-48h. Then call `get_posts_by_ids` on those ids with `expansions=[author_id,attachments.media_keys]`, `user.fields=[username,name,public_metrics]` | `raw/outsiders.json` (+ `raw/ai_search.json`) |
| 5 | `search_news` | `query="AI"`, `max_age_hours=48`, `max_results=10` | `raw/news.json` |

Notes
* The search API has **no engagement filter** (`min_faves` is dropped), so outsiders come from
  posts the watchlist quoted plus relevancy search, filtered to ≥5K views by the build script.
* Large MCP results get spilled to a "Full text" file; copy that file, not the truncated preview.
  The build script tolerates text before and after the JSON body.

## 2. Build

```bash
python3 scripts/build_data.py --day D --fetched-at <UTC ISO time of step 3> \
  --users raw/users.json --posts raw/posts_snapshot.json \
  --outsiders raw/outsiders.json --outsiders raw/ai_search.json --news raw/news.json
```

`--posts` can be given more than once (for example search pages plus the snapshot); the
last file wins for the same id. The script prints a one-line summary. Sanity check: `hits`
> 0 on a normal day, and the `you_rank` rank is between 1 and the number of accounts.

### How each field is computed (all from fetched data; nothing is invented)

| data.json field | Rule |
|---|---|
| `hits` | Original posts (no replies or reposts) by operator + watchlist posted inside D (MSK) with views ≥ 5,000, sorted by views. `highlight` (★) = ≥ 10,000. Self-quotes (quoting the author's own post) **count**, labelled `самоцитата DD.MM`. Same-author same-text duplicates go to `excluded_hits`. |
| X Score (computed in the page) | `round(100·(0.45·min(hits/12,1) + 0.55·min(totalViews/100K,1)))` over `hits`. Targets live in `index.html` → `DASHBOARD_TARGETS`. |
| Day Target | hits vs 12 and total views vs 100K (page), plus the operator's best post vs 5K / 10K (`you_rank`). |
| `day_roster` | Every tracked account: best post (`views`) and sum of the day's posts (`total_views`), ranked by best. |
| `you_rank` | The operator's row from the roster: rank, best/total, list of the operator's D posts. `best_views` is null when the operator posted nothing on D. |
| `no_hits` | Watchlist accounts with no ≥5K post on D: reason + best views seen. |
| `last24h` | Operator + watchlist originals posted in the 24h before the snapshot, any view count; `hit` ≥5K, `star` ≥10K. |
| `virals` / `outsiders` | Non-watchlist AI posts from the last 48h with ≥5K views (see step 4). |
| `trend_keywords` | 1- and 2-word phrases from the ≥5K corpus (48h watchlist posts + outsiders). Only keeps phrases used by **≥2 different authors**. Score = Σ log10(views) × authors (× 1.3 for 2-word phrases). Top 25 are shown; the top 40 feed `why_hit`. |
| `why_hit` / radar C | trend match = 1 − ∏(1 − w) over matched keywords (rank 1–10 w = 0.35, 11–25 w = 0.22, 26–40 w = 0.12). Verdict: ≥50% `тренд`; otherwise image/video `визуал`; otherwise `автор/аудитория`. |
| `trend_radar.news` | X News stories from step 5. |
| `patterns` | The top 6 keywords with author counts. |
| `followers` | Count at snapshot; `delta` versus the latest ledger value at least 12h older. |
| `yesterday` | D-1 hits from the ledger, with growth (`g24`) = latest views minus the snapshot closest to 24h earlier. It needs two daily snapshots, so it stays hidden on the first day. |
| `leaderboards.week` / `.month` / `all_time` | Summed from `data/ledger.json → days` (hits, best, total per account per day), using the latest refreshed views for each post. Week = the last 7 tracked days ending D; month = tracked days of D's month. |
| Not auto-generated (left empty so the page hides or blanks them) | `trend_radar.topics`, `ideas`, `articles`, `x_keywords`, `drafts_top10`, `draft_en`, `watchlist_brief`, `virals_narrative`, `experiment`. An agent may fill them by hand from the same day's real posts. Keep the original schema: see the `renderRadar` / `renderExp` functions in `index.html`. |

## 3. Ledgers (how they roll)

* `data/ledger.json`
  * `posts[id].snapshots[ts]`: one metrics snapshot per run for every post fetched. Never delete these, because growth and leaderboards depend on them.
  * `days[D].accounts[handle]`: hits, best, total, best_url, post_ids for D. Older days are recomputed from the newest snapshot of their post_ids on every run.
  * `followers[handle].history[ts]`: follower count per run.
  * `tracking_start`: 2026-11-19 (first day of this board).
* `leaderboard_ledger.json`: a compact copy of `days` (no snapshots), rewritten every run.
* To add or remove a watchlist account, edit `config.json → watchlist` and also edit the
  `from:` query in step 2.

## 4. Commit and push

* Commit `data.json`, `data/ledger.json`, `leaderboard_ledger.json` (never `raw/`).
* Message: `Board update YYYY-MM-DD` (D, the MSK day shown on the board), e.g. `Board update 2026-11-19`.
* Branch `main`. GitHub Pages serves `main` / root, and the page re-fetches `data.json?ts=…` on load.

## 5. Verify

Open the Pages URL. The header shows `@kkkkkkkkj22`, the meta line shows `за DD.MM … updated …`,
and the page does not show "failed to load data.json".
