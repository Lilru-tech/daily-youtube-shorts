# Daily YouTube Shorts Automation

Fully automated pipeline that generates and uploads one YouTube Short per day about **Amazing Facts and Psychological Insights**.

## What it does

1. Gemini generates an English script (strict JSON)
2. edge-tts creates Spanish voiceover + English subtitles
3. Pexels provides vertical background clips per line
4. FFmpeg composes a 1080x1920 Short with burned-in subtitles
5. YouTube Data API uploads the video (unlisted by default)

## Quick start (local)

```bash
cd daily-youtube-shorts
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set environment variables:

```bash
export GEMINI_API_KEY="..."
export PEXELS_API_KEY="..."
export YT_CLIENT_ID="..."
export YT_CLIENT_SECRET="..."
export YT_REFRESH_TOKEN="..."
```

Generate without uploading:

```bash
python main.py --skip-upload
```

Run a smoke test (needs `GEMINI_API_KEY` + `PEXELS_API_KEY` only):

```bash
python scripts/smoke_test.py
```

## YouTube OAuth setup (one-time)

1. Create a Google Cloud project and enable **YouTube Data API v3**
2. Create an OAuth 2.0 Client ID (Desktop app)
3. Download `client_secret.json` into this project root
4. Run:

```bash
python scripts/get_youtube_refresh_token.py
```

5. Copy the printed values into GitHub Secrets

## GitHub Actions secrets

| Secret | Required |
|--------|----------|
| `GEMINI_API_KEY` | Yes |
| `PEXELS_API_KEY` | Yes |
| `YT_CLIENT_ID` | Yes |
| `YT_CLIENT_SECRET` | Yes |
| `YT_REFRESH_TOKEN` | Yes |
| `YT_PRIVACY_STATUS` | No (default: `unlisted`) |
| `EDGE_TTS_VOICE` | No (default: `es-ES-AlvaroNeural`) |
| `GEMINI_MODEL` | No (default: `gemini-2.0-flash`) |

## GitHub deployment

1. Push this folder to a GitHub repository
2. Add the secrets under **Settings → Secrets and variables → Actions**
3. Run manually: **Actions → Daily YouTube Short → Run workflow**
4. Daily cron runs at **15:00 UTC**

## Notes

- Unverified YouTube API projects may force uploads to **private** even when requesting `unlisted`
- The pipeline sets `containsSyntheticMedia: true` on every upload
- Failed runs upload `work/` artifacts for debugging (3-day retention)
