# X Board · @kkkkkkkkj22

A personal X virality dashboard. It scores the watchlist's daily hits (≥5K views), ranks
@kkkkkkkkj22 against the watchlist, and shows week/month leaderboards, top hits, trend
keywords, AI outsider virals from the last 48h, and X News.

* Static site: `index.html` reads `data.json`.
* Data: rebuilt daily from the X API with `scripts/build_data.py`. See **REFRESH.md**.
* Config (operator, watchlist, thresholds): `config.json`.

The layout is adapted from the public kiosa-board dashboard. This is a personal research tool and
is not affiliated with X Corp.
