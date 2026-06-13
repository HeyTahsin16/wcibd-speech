# WCIBD Bot

A Discord bot with one job: reply with random images or pre-written sentences, all sourced from a GitHub repository — nothing is stored on Railway.

---

## How it works

| What you type | What happens |
|---|---|
| `wcibd` | Bot sends a random image from your GitHub `images/` folder |
| `wcibd free speech` | If `"free speech"` is a key in `responses.json`, bot sends that sentence |
| `wcibd unknown thing` | No match → bot sends a random image |

**Reply behaviour:** if you use `wcibd` while replying to someone, the bot responds to *that person's* message — not yours. Perfect for clapping back on behalf of the server.

```
Person 1: "is there free speech here?"
Person 2: [replies to Person 1] "wcibd free speech"
Bot:      [replies to Person 1] "Free speech is alive and well here! 🗽"
```

---

## Setup — two repos, one bot

You need **two** GitHub repos (or one repo with two folders, your call):

### 1. Content repo (images + responses)

Create a GitHub repo with this structure:

```
wcibd-content/
├── images/
│   ├── funny1.gif
│   ├── meme2.jpg
│   └── ...
└── data/
    └── responses.json
```

The `sample-github-data/` folder in this repo is your template — copy it over.

#### responses.json format

Keys are the keywords (case-insensitive). Values are what the bot says.

```json
{
  "free speech": "Free speech is alive and well here! 🗽",
  "rules": "Check #rules for what's expected around here.",
  "mods": "The mod team keeps things fair — DM a mod if you need help!"
}
```

To add a new keyword, just add a new key-value pair and push. The bot picks up changes within `CACHE_TTL` seconds (default 5 min).

To add images, drop files into `images/` and push. Same cache window applies.

---

### 2. Bot repo (this repo — deployed to Railway)

---

## Discord Developer Portal setup

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications) → **New Application**.
2. Click **Bot** in the sidebar → **Add Bot**.
3. Copy the **Token** — you'll need it for Railway.
4. Under **Privileged Gateway Intents**, enable **Message Content Intent**.
5. Under **OAuth2 → URL Generator**:
   - Scopes: `bot`
   - Bot Permissions: `Send Messages`, `Read Message History`, `Attach Files`
6. Open the generated URL to invite the bot to your server.

---

## Deploy to Railway

### Option A — Deploy from GitHub (recommended)

1. Push this repo to GitHub.
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo** → select this repo.
3. Once the project is created, go to **Variables** and add:

| Variable | Value |
|---|---|
| `DISCORD_TOKEN` | Your bot token from the Developer Portal |
| `GITHUB_OWNER` | Your GitHub username |
| `GITHUB_REPO` | Name of your content repo (e.g. `wcibd-content`) |
| `GITHUB_BRANCH` | `main` (or whatever your branch is) |
| `GITHUB_TOKEN` | *(optional but recommended)* A GitHub PAT with `repo` read access |
| `IMAGES_FOLDER` | `images` |
| `RESPONSES_PATH` | `data/responses.json` |
| `CACHE_TTL` | `300` |

4. Railway will auto-detect Python via `requirements.txt` and run `python bot.py`.
5. Check the **Logs** tab — you should see `✅  Bot is online as ...`.

### Option B — Railway CLI

```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

Then set variables via the dashboard or:
```bash
railway variables set DISCORD_TOKEN=xxx GITHUB_OWNER=yyy ...
```

---

## GitHub Personal Access Token (optional but recommended)

Without a token: **60 GitHub API requests/hour** (shared across all unauthenticated requests from Railway's IP — could run dry fast).

With a token: **5,000 requests/hour**.

Create one at [github.com/settings/tokens](https://github.com/settings/tokens) → **Generate new token (classic)** → tick only `repo` (read access). Paste it into the `GITHUB_TOKEN` Railway variable.

If your content repo is **public**, you can skip this — public repos don't need auth for reads, but you still get higher limits with a token.

---

## Adding content (no bot restart needed)

### New image
Push any `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp` or `.bmp` to `images/` in your content repo. The bot picks it up within `CACHE_TTL` seconds.

### New keyword response
Edit `data/responses.json` and push. Same cache window.

```json
{
  "free speech": "Free speech is alive here! 🗽",
  "your new keyword": "Your new response sentence here."
}
```

Keywords are matched **case-insensitively** — `wcibd Free Speech` and `wcibd free speech` both work.

---

## Local development

```bash
# Clone this repo
git clone https://github.com/you/wcibd-bot
cd wcibd-bot

# Install deps
pip install -r requirements.txt

# Copy and fill in your env
cp .env.example .env
# Edit .env with your DISCORD_TOKEN, GITHUB_OWNER, etc.

# Run
python bot.py
```
