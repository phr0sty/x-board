#!/usr/bin/env bash
# Daily refresh for the Instagram / TikTok / YouTube boards. Run from the repo root.
# Needs only python3 + outbound HTTPS (no API keys). Fetch -> build; then commit the three data.json files.
set -uo pipefail
cd "$(dirname "$0")/../.."
S=scripts/social
python3 $S/fetch_youtube.py   --config youtube/config.json   --out youtube/raw/youtube.json     || echo "youtube fetch failed"
python3 $S/fetch_tiktok.py    --config tiktok/config.json    --out tiktok/raw/tiktok.json       || echo "tiktok fetch failed"
python3 $S/fetch_instagram.py --config instagram/config.json --out instagram/raw/instagram.json || echo "instagram fetch failed"
python3 $S/build_social.py --platform youtube --board youtube --raw youtube/raw/youtube.json
python3 $S/build_social.py --platform tiktok  --board tiktok  --raw tiktok/raw/tiktok.json
python3 $S/build_social.py --platform instagram --board instagram --raw instagram/raw/instagram.json \
        --signals tiktok/data.json --signals youtube/data.json
