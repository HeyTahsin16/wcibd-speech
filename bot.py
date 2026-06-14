"""
WCIBD Discord Bot
─────────────────────────────────────────────────────────────────
Usage:
  wcibd                  → sends the next image from a shuffled, no-repeat
                           deck pulled from your GitHub stash
  wcibd <keyword>        → if the keyword exists in responses.json, the bot
                           replies with the mapped sentence; otherwise sends
                           the next image instead.

  When used as a reply, the bot always responds to the *original* message
  author (not the person who typed wcibd).

  Image order: images are dealt from a shuffled deck — every image is shown
  once before any repeats, and no image is ever immediately followed by
  itself (including across a reshuffle). This lives in memory, so a restart
  simply starts a fresh shuffle.
─────────────────────────────────────────────────────────────────
"""

import discord
import aiohttp
import random
import json
import os
import io
import time
import logging
from dotenv import load_dotenv

# ── Setup ─────────────────────────────────────────────────────────────────────

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
log = logging.getLogger(__name__)

# Required
DISCORD_TOKEN  = os.getenv('DISCORD_TOKEN')
GITHUB_OWNER   = os.getenv('GITHUB_OWNER')
GITHUB_REPO    = os.getenv('GITHUB_REPO')

# Optional / defaults
GITHUB_TOKEN   = os.getenv('GITHUB_TOKEN', '')
GITHUB_BRANCH  = os.getenv('GITHUB_BRANCH',  'main')
IMAGES_FOLDER  = os.getenv('IMAGES_FOLDER',  'images')
RESPONSES_PATH = os.getenv('RESPONSES_PATH', 'data/responses.json')
CACHE_TTL      = int(os.getenv('CACHE_TTL', '300'))   # seconds; default 5 min

PREFIX         = 'wcibd'
IMAGE_EXTS     = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}

# ── Validate config at startup ─────────────────────────────────────────────────

if not DISCORD_TOKEN:
    raise RuntimeError('DISCORD_TOKEN is not set in environment variables.')
if not GITHUB_OWNER or not GITHUB_REPO:
    raise RuntimeError('GITHUB_OWNER and GITHUB_REPO must both be set.')

# ── Simple in-memory cache ─────────────────────────────────────────────────────

_cache: dict = {
    'responses': {'data': None, 'ts': 0.0},
    'images':    {'data': None, 'ts': 0.0},
}

# ── No-repeat image sequencer ───────────────────────────────────────────────────
# Keeps a shuffled "deck" of images. Each send pops the next card off the deck.
# Once the deck is empty it's reshuffled — and the reshuffle is checked so the
# new first card never matches the last card that was just sent (no back-to-back
# repeats, even across a reshuffle). Lives purely in memory: resets on restart,
# which is fine since "the first one can be anything".
_shuffle_state: dict = {
    'queue': [],                # list[dict] — remaining images for this cycle
    'last_sent': None,          # str|None — filename of the last image sent
    'snapshot': frozenset(),    # set of filenames the current queue was built from
}


def _build_deck(images: list) -> list:
    """Return a freshly shuffled copy of `images`, avoiding a repeat of last_sent
    in the first slot (when possible)."""
    deck = images.copy()
    random.shuffle(deck)
    last = _shuffle_state['last_sent']
    if last is not None and len(deck) > 1 and deck[0]['name'] == last:
        deck[0], deck[1] = deck[1], deck[0]
    return deck


def get_next_image(images: list) -> dict:
    """
    Pop the next image off the no-repeat deck. Rebuilds/reshuffles the deck
    when it's empty or when the available image set has changed (new images
    pushed to GitHub, old ones removed/renamed).
    """
    current_names = frozenset(img['name'] for img in images)

    if not _shuffle_state['queue'] or _shuffle_state['snapshot'] != current_names:
        _shuffle_state['queue'] = _build_deck(images)
        _shuffle_state['snapshot'] = current_names

    pick = _shuffle_state['queue'].pop(0)
    _shuffle_state['last_sent'] = pick['name']
    return pick

# ── GitHub helpers ─────────────────────────────────────────────────────────────

def _gh_headers() -> dict:
    """Headers for GitHub API requests; adds auth if a token is set."""
    h = {'Accept': 'application/vnd.github.v3+json'}
    if GITHUB_TOKEN:
        h['Authorization'] = f'token {GITHUB_TOKEN}'
    return h


async def fetch_responses(session: aiohttp.ClientSession) -> dict:
    """
    Load keyword → sentence map from responses.json on GitHub.
    Results are cached for CACHE_TTL seconds.
    """
    now = time.monotonic()
    cached = _cache['responses']
    if cached['data'] is not None and now - cached['ts'] < CACHE_TTL:
        return cached['data']

    url = (
        f'https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}'
        f'/{GITHUB_BRANCH}/{RESPONSES_PATH}'
    )
    try:
        async with session.get(url) as r:
            if r.status == 200:
                raw = await r.text()
                data = json.loads(raw)
                # Normalise keys to lowercase so matching is case-insensitive
                data = {k.lower().strip(): v for k, v in data.items()}
                _cache['responses'] = {'data': data, 'ts': now}
                log.info('Responses refreshed — %d entries loaded.', len(data))
                return data
            log.warning('responses.json fetch → HTTP %s', r.status)
    except Exception as exc:
        log.error('fetch_responses error: %s', exc)

    # Return stale cache if available, otherwise empty dict
    return cached['data'] or {}


async def fetch_image_list(session: aiohttp.ClientSession) -> list:
    """
    Return list of GitHub file objects (dict with download_url, name, etc.)
    from the images folder. Results are cached for CACHE_TTL seconds.
    """
    now = time.monotonic()
    cached = _cache['images']
    if cached['data'] is not None and now - cached['ts'] < CACHE_TTL:
        return cached['data']

    url = (
        f'https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}'
        f'/contents/{IMAGES_FOLDER}?ref={GITHUB_BRANCH}'
    )
    try:
        async with session.get(url, headers=_gh_headers()) as r:
            if r.status == 200:
                files = await r.json()
                imgs = [
                    f for f in files
                    if f.get('type') == 'file'
                    and os.path.splitext(f['name'].lower())[1] in IMAGE_EXTS
                ]
                _cache['images'] = {'data': imgs, 'ts': now}
                log.info('Image list refreshed — %d files found.', len(imgs))
                return imgs
            log.warning('Image list fetch → HTTP %s  (check IMAGES_FOLDER path)', r.status)
    except Exception as exc:
        log.error('fetch_image_list error: %s', exc)

    return cached['data'] or []

# ── Bot ────────────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)


@bot.event
async def on_ready():
    log.info('✅  Bot is online as %s  (id: %s)', bot.user, bot.user.id)
    log.info('    GitHub source: %s/%s  [branch: %s]', GITHUB_OWNER, GITHUB_REPO, GITHUB_BRANCH)
    log.info('    Images folder: %s  |  Responses: %s', IMAGES_FOLDER, RESPONSES_PATH)


@bot.event
async def on_message(message: discord.Message):
    # Ignore other bots
    if message.author.bot:
        return

    raw = message.content.strip()

    # Only process messages that begin with the prefix (case-insensitive)
    if not raw.lower().startswith(PREFIX):
        return

    # Everything after "wcibd", stripped and lowercased → keyword
    keyword = raw[len(PREFIX):].strip().lower()

    # ── Resolve reply target ────────────────────────────────────────────────
    # If the wcibd message is itself a reply, respond to the *original* message.
    # Otherwise respond in the same channel (replying to the wcibd sender).
    reply_to: discord.Message = message
    if message.reference:
        try:
            resolved = message.reference.resolved
            if resolved is None:
                resolved = await message.channel.fetch_message(
                    message.reference.message_id
                )
            if resolved:
                reply_to = resolved
        except discord.NotFound:
            pass   # original message deleted — fall back to replying to wcibd sender
        except Exception as exc:
            log.warning('Could not resolve reply reference: %s', exc)

    # ── Hit GitHub and respond ──────────────────────────────────────────────
    async with aiohttp.ClientSession() as session:

        # 1. Check keyword → sentence
        if keyword:
            responses = await fetch_responses(session)
            if keyword in responses:
                sentence = str(responses[keyword])
                try:
                    await reply_to.reply(sentence, mention_author=True)
                except discord.HTTPException as exc:
                    log.error('Failed to send sentence reply: %s', exc)
                return   # Done — no image needed

        # 2. No matching keyword → send a random image
        images = await fetch_image_list(session)
        if not images:
            await message.channel.send(
                '⚠️  No images found. Make sure the `images/` folder exists in your GitHub repo.'
            )
            return

        pick = get_next_image(images)
        log.info('Sending image: %s  (%d left in deck)', pick['name'], len(_shuffle_state['queue']))

        try:
            async with session.get(pick['download_url']) as r:
                if r.status != 200:
                    await message.channel.send('⚠️  Couldn\'t download that image, try again.')
                    return
                img_bytes = await r.read()

            img_file = discord.File(io.BytesIO(img_bytes), filename=pick['name'])
            await reply_to.reply(file=img_file, mention_author=True)

        except discord.HTTPException as exc:
            log.error('Failed to send image reply: %s', exc)

# ── Run ────────────────────────────────────────────────────────────────────────

bot.run(DISCORD_TOKEN)
