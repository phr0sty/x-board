# Instagram / TikTok / YouTube boards: daily refresh

Three extra boards live next to the X board in this repo. They share the X board's ideas:
a static `index.html` reading a language-neutral `data.json`, a watchlist in `config.json`,
a build script, and a 9-language UI.

| Board | Folder | Operator | Look |
|---|---|---|---|
| Instagram | `instagram/` | @sumofmyparts | "The Index": cream/black editorial |
| TikTok | `tiktok/` | @jcizzle05 (private) | "Hot Board": bright, big cards, emoji |
| YouTube | `youtube/` | @Llllhhhhhhhhhhhh22 ("First Last", channel `UCHR7rKQW9gJE6NbdODzCG5g`) | "YouTube Pulse": dark/red |

Niche: music / DJ / synths and gear / production. Nothing is ever posted to any platform.

## Run it

```bash
bash scripts/social/refresh.sh     # fetch + build all three (python3 only, no keys)
```

Then commit `instagram/data.json`, `tiktok/data.json` and `youtube/data.json` (and any
edited `ideas.json`) to `main` with the message `Social boards update YYYY-MM-DD`.
`raw/` folders are git-ignored. A full run takes about 2 to 15 minutes; Instagram is the
slow one because it backs off when rate-limited.

Sanity checks after a run (the build prints one line per board):
* youtube: `26/26 accounts` (or close), `posts in 7d` > 0
* tiktok: `28/28 accounts` (or close), operator `private` until @jcizzle05 goes public
* instagram: some accounts may fail on a given run. Their last good counts are carried
  forward and marked with the date they were read (`stale_from`), never invented.

## Where each number comes from

| Platform | Source (public, no login) | Real | Not available |
|---|---|---|---|
| YouTube | Channel page header; official RSS `feeds/videos.xml?channel_id=` | subscribers, video count, latest 15 uploads with views + likes, publish time, Shorts flag | comments; anything older than the last 15 uploads |
| TikTok | Official creator embed `tiktok.com/embed/@handle` | followers, total likes, ~10-13 featured/recent videos with play counts; post time decoded from video id | per-video likes/comments/shares; private accounts (incl. the operator for now) |
| Instagram | Profile link preview (`og:description`) | followers, following, post count | per-post views, Reels plays, likes, the post list (all login-only). "Signals" = real TikTok + YouTube Shorts numbers as a proxy |

Optional: add exact post URLs to `instagram/config.json -> tracked_posts`; the fetcher then
reads each post's public preview (likes, comments, date, caption) into `data.json -> tracked_posts`.

## How data.json is built (`scripts/social/build_social.py`)

* Window: YouTube 7 days, TikTok 30 days.
* `hot`: watchlist posts in the window ranked by views per hour since posting (`vph`), max 2 per creator.
* `top_views`: most viewed in the window, max 3 per creator. `evergreen`: most viewed overall.
* `formats`: rule-based buckets from the title/caption (gear, tutorial, build, transition, live,
  release, other) with median and mean views.
* `keywords`: words used by at least 2 different creators in the window, scored by sum of log10(views) times authors.
* `roster`: every account's followers, posts in window, best and total views (Instagram: followers only).
* `ideas`: copied from `<board>/ideas.json` (hand-written drafts; each names the real post it is modelled on
  and that post's view count on the date written). Refresh them when the hot list changes a lot.

## Languages

UI strings for all three boards are in `social-i18n.js` (en, ru, es, pt, fr, de, ja, ko, zh).
Pick one with the header dropdown or `?lang=xx`; the choice is remembered in localStorage
(`social_lang`). Third-party titles, the content drafts, and the data-limit notes stay in English or their original language.
