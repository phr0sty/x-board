# X Board · @kkkkkkkkj22

A personal X virality dashboard. It scores the watchlist's daily hits (≥5K views), ranks
@kkkkkkkkj22 against the watchlist, and shows week/month leaderboards, top hits, trend
keywords, AI outsider virals from the last 48h, and X News.

* Static site: `index.html` reads `data.json`.
* Data: rebuilt daily from the X API with `scripts/build_data.py`. See **REFRESH.md**.
* Config (operator, watchlist, thresholds): `config.json`.
* UI languages: English (default), Russian, Español, Português, Français, Deutsch, 日本語, 한국어, 简体中文.
  Pick one in the header or link with `?lang=xx` (e.g. `?lang=ja`); the choice is remembered.
  All UI strings live in `i18n.js`; `data.json` stays language-neutral.

## More boards (same repo)

* Instagram, "The Index": https://phr0sty.github.io/x-board/instagram/ (@sumofmyparts)
* TikTok, "Hot Board": https://phr0sty.github.io/x-board/tiktok/ (@jcizzle05)
* YouTube, "YouTube Pulse": https://phr0sty.github.io/x-board/youtube/ (@Llllhhhhhhhhhhhh22)

They track the music / DJ / synth and gear niche, include ready-to-shoot content drafts
("Make this"), and refresh with `bash scripts/social/refresh.sh`. See **SOCIAL_REFRESH.md**.

The layout is adapted from the public kiosa-board dashboard. This is a personal research tool and
is not affiliated with X Corp.
