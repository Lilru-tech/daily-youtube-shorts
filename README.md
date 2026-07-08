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

| Workflow | Channel | Local target | First UTC attempt | Retry window (local) |
|----------|---------|--------------|-------------------|----------------------|
| `auto_shorts_datos_es.yml` | `datos_es` | 10:00 / 14:00 / 18:00 Europe/Madrid | 07:42 / 11:42 / 15:42 UTC | ~09:42–10:42 / 13:42–14:42 / 17:42–18:42 Madrid (CEST) |
| `auto_shorts_whatifvibe.yml` | `whatifvibe` | 10:00 / 14:00 / 18:00 US Eastern | 13:42 / 17:42 / 21:42 UTC | ~09:42–10:42 / 13:42–14:42 / 17:42–18:42 EDT |
| `schedule_watchdog.yml` | both | backup only | external trigger | fires missing slots via `workflow_dispatch` |

GitHub Actions cron runs in **UTC only**. Summer offsets: Madrid CEST = UTC+2, US Eastern EDT = UTC−4. Each slot has four redundant cron attempts at minutes `:42`, `:02`, `:22`, `:42` to avoid on-the-hour scheduler queues. Channel windows are staggered so Datos ES and WhatIfVibe never overlap (shared `GEMINI_API_KEY` and `youtube-shorts-gemini-global` concurrency group).

Scheduled runs map each cron expression directly to an upload slot via `CRON_SLOT_MAP` in `scripts/should_run.py`, so GitHub delays do not skip uploads. `should_run.py` dedupes by slot/day so at most one upload happens per slot. If you change any cron, update `CRON_SLOT_MAP` to match.

### Private-repo scheduler reliability

This repo is private. GitHub frequently **delays or silently drops** scheduled workflow events on low-activity private repositories. Mitigations:

1. **Redundant crons** (configured above) — four attempts per slot.
2. **Schedule Watchdog** (`schedule_watchdog.yml`) — external backup via `repository_dispatch`. Configure [cron-job.org](https://cron-job.org) (or similar) to POST at ~09:50 / 13:50 / 17:50 local time per channel, **after** the primary window, only if the slot may have been missed:

   ```
   POST https://api.github.com/repos/Lilru-tech/daily-youtube-shorts/dispatches
   Authorization: Bearer <PAT with repo scope>
   {"event_type":"schedule_watchdog","client_payload":{"channel":"datos_es","slot":"morning"}}
   ```

   Replace `channel` / `slot` for each backup (six dispatches per day total). The watchdog checks `recent_topics.json` and triggers the channel workflow with `force_slot` only when today's slot is missing.

3. **Make the repo public** (simplest fix) — scheduled events become significantly more reliable; secrets remain protected.

### Daylight saving drift

Fixed UTC crons shift local publish times by **one hour** when clocks change (CET/EST in winter vs CEST/EDT in summer). Update cron hours seasonally or accept ~1 h drift.

Trigger any workflow manually from **Actions** in GitHub.

## Data layout

```
data/datos_es/recent_topics.json
data/datos_es/uploads_log.csv
data/whatifvibe/recent_topics.json
data/whatifvibe/uploads_log.csv
work/{profile}/{date}_{slot}/
branding/{profile}/
```

## Notes

- Unverified YouTube API projects may force uploads to **private**
- The pipeline sets `containsSyntheticMedia: true` on every upload
- On macOS, subtitle burn-in requires FFmpeg with libass: `brew install ffmpeg-full`
- `scripts/setup_channel.py` is a wrapper for `create_branding.py --channel datos_es --update-youtube`
- Gemini script generation tries multiple models with separate free-tier quotas:
  `gemini-2.5-flash-lite` → `gemini-2.5-flash` → `gemini-2.0-flash-lite` → `gemini-2.0-flash`.
  On `429` daily quota for one model, the pipeline automatically switches to the next model.
- If all models return `RESOURCE_EXHAUSTED (429)`, update `GEMINI_API_KEY` or enable billing on the Google AI project.
