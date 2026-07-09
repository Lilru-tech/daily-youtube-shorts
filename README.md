# Daily YouTube Shorts Automation

Fully automated pipeline that generates and uploads YouTube Shorts for **two channels** from one repo:

| Profile | Channel | Handle | Schedule (local) |
|---------|---------|--------|------------------|
| `datos_es` | Datos interesantes Español | @Datosinteresantes-v7 | 10:00, 14:00, 18:00 Europe/Madrid |
| `whatifvibe` | WhatIfVibe | @WhatIfVibe-m5k | 10:00, 14:00, 18:00 US Eastern |

## What it does

1. Gemini generates a script (Spanish psychology facts or English "What happens if..." scenarios)
2. edge-tts creates voiceover + burned-in subtitles
3. Pexels provides vertical background clips per line
4. FFmpeg composes a 1080x1920 Short with hook overlay
5. YouTube Data API uploads to the selected channel

## Quick start (local)

```bash
cd daily-youtube-shorts
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set shared environment variables:

```bash
export GEMINI_API_KEY="..."
export PEXELS_API_KEY="..."
export YT_CLIENT_ID="..."
export YT_CLIENT_SECRET="..."
```

Per-channel variables (examples):

```bash
# Datos interesantes Español
export YT_REFRESH_TOKEN_DATOS_ES="..."
export YT_TARGET_CHANNEL_ID_DATOS_ES="UCw272LClsZaAXko-DieXKKA"

# WhatIfVibe
export YT_REFRESH_TOKEN_WHATIFVIBE="..."
export YT_TARGET_CHANNEL_ID_WHATIFVIBE="UC..."
```

Generate without uploading:

```bash
python main.py --channel datos_es --skip-upload
python main.py --channel whatifvibe --skip-upload
```

Smoke test (needs `PEXELS_API_KEY`; sets a placeholder channel ID for WhatIfVibe):

```bash
python scripts/smoke_test.py --channel datos_es
python scripts/smoke_test.py --channel whatifvibe
```

Generate branding assets:

```bash
python create_branding.py --channel datos_es
python create_branding.py --channel whatifvibe
python create_branding.py --channel whatifvibe --update-youtube
```

## YouTube OAuth setup (one-time per channel)

Run OAuth **once per channel** while switched to that channel in YouTube:

```bash
python get_token.py --channel datos_es
python get_token.py --channel whatifvibe
```

Tokens are saved locally as `youtube_secrets_{profile}.json` and pushed to GitHub Secrets when `gh` CLI is available.

## GitHub Actions secrets

### Shared

| Secret | Required |
|--------|----------|
| `GEMINI_API_KEY` | Yes |
| `PEXELS_API_KEY` | Yes |
| `YT_CLIENT_ID` | Yes |
| `YT_CLIENT_SECRET` | Yes |
| `YT_PRIVACY_STATUS` | No (default: `public`) |
| `GEMINI_MODEL` | No |

### Datos interesantes Español

| Secret | Value |
|--------|-------|
| `YT_REFRESH_TOKEN_DATOS_ES` | OAuth refresh token for Spanish channel |
| `YT_TARGET_CHANNEL_ID_DATOS_ES` | `UCw272LClsZaAXko-DieXKKA` |
| `EDGE_TTS_VOICE_DATOS_ES` | No (default: `es-ES-AlvaroNeural`) |

### WhatIfVibe

| Secret | Value |
|--------|-------|
| `YT_REFRESH_TOKEN_WHATIFVIBE` | OAuth refresh token for WhatIfVibe |
| `YT_TARGET_CHANNEL_ID_WHATIFVIBE` | Your WhatIfVibe `UC...` channel ID |
| `EDGE_TTS_VOICE_WHATIFVIBE` | No (default: `en-US-ChristopherNeural`) |

If you have an existing `YT_REFRESH_TOKEN` for the Spanish channel, rename it to `YT_REFRESH_TOKEN_DATOS_ES` in GitHub Secrets.

## GitHub workflows

| Workflow | Channel | Local target | UTC attempts | Local window (summer) |
|----------|---------|--------------|--------------|------------------------|
| `auto_shorts_datos_es.yml` | `datos_es` | 10:00 / 14:00 / 18:00 Europe/Madrid | 07:42+08:22 / 11:42+12:22 / 15:42+16:22 | two tries per slot, ~20 min apart |
| `auto_shorts_whatifvibe.yml` | `whatifvibe` | 10:00 / 14:00 / 18:00 US Eastern | 13:42+14:22 / 17:42+18:22 / 21:42+22:22 | two tries per slot, ~20 min apart |
| `schedule_watchdog.yml` | both | manual recovery | `workflow_dispatch` only | re-triggers a missing slot after checking `recent_topics.json` |

This repository is **public** for reliable GitHub Actions cron scheduling. Secrets (`GEMINI_API_KEY`, OAuth tokens, etc.) live only in **GitHub Actions Secrets** — never in the repo.

GitHub Actions cron runs in **UTC only**. Summer offsets: Madrid CEST = UTC+2, US Eastern EDT = UTC−4. Each slot has two cron attempts at minutes `:42` and `:22` to avoid on-the-hour scheduler queues. Channel windows are staggered so Datos ES and WhatIfVibe never overlap (shared `GEMINI_API_KEY` and `youtube-shorts-gemini-global` concurrency group).

Scheduled runs map each cron expression directly to an upload slot via `CRON_SLOT_MAP` in `scripts/should_run.py`, so GitHub delays do not skip uploads. `should_run.py` dedupes by slot/day so at most one upload happens per slot. If you change any cron, update `CRON_SLOT_MAP` to match.

If a scheduled slot is missed, run **Schedule Watchdog** manually from Actions (pick channel + slot). No external cron service or PAT is required.

### Daylight saving drift

Fixed UTC crons shift local publish times by **one hour** when clocks change (CET/EST in winter vs CEST/EDT in summer). Update cron hours seasonally or accept ~1 h drift.

Trigger any workflow manually from **Actions** in GitHub.

## Security

**Audit result:** OAuth JSON files (`youtube_secrets_*.json`, `client_secret.json`), `.env`, and `token.json` have **never been committed** to git history. Only `client_secret.json.template` (placeholder values) is tracked.

Files blocked by `.gitignore` and must stay local:

- `youtube_secrets_*.json`, `client_secret.json`, `token.json`
- `.env`, `.env.*`
- `work/`, `.venv/`, `data/*_log.csv`

**Token rotation is not required** from a git-leak perspective. Rotate OAuth refresh tokens only if you suspect local machine compromise.

Never commit real credentials. Use `get_token.py` locally and store tokens in GitHub Secrets.

## Data layout

```
data/datos_es/recent_topics.json      # tracked (dedup state)
data/datos_es/uploads_log.csv         # local/CI only (gitignored)
data/whatifvibe/recent_topics.json
data/whatifvibe/uploads_log.csv
work/{profile}/{date}_{slot}/         # gitignored
branding/{profile}/                   # gitignored
```

## Notes

- Unverified YouTube API projects may force uploads to **private**
- The pipeline sets `containsSyntheticMedia: true` on every upload
- On macOS, subtitle burn-in requires FFmpeg with libass: `brew install ffmpeg-full`
- `scripts/setup_channel.py` is a wrapper for `create_branding.py --channel datos_es --update-youtube`
- Gemini script generation tries multiple models with separate free-tier quotas:
  `gemini-2.5-flash-lite` → `gemini-2.5-flash` → `gemini-2.0-flash-lite` → `gemini-2.0-flash` → `gemini-1.5-flash` → `gemini-1.5-flash-8b`.
  On `429` daily quota for one model, the pipeline automatically switches to the next model. Per-minute `429` responses wait and retry.
- Both channel workflows share the `youtube-shorts-gemini-global` concurrency group so only one Gemini call runs at a time.
- If all models return `RESOURCE_EXHAUSTED (429)`, update `GEMINI_API_KEY` or enable billing on the Google AI project.
