import anthropic
import tweepy
import os
import sys
import re
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    filename="bot.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# ── Clients ───────────────────────────────────────────────────
claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

twitter = tweepy.Client(
    consumer_key=os.getenv("TWITTER_CLIENT_ID"),
    consumer_secret=os.getenv("TWITTER_CLIENT_SECRET"),
    access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
    access_token_secret=os.getenv("TWITTER_ACCESS_TOKEN_SECRET"),
)

# ── Prompts ───────────────────────────────────────────────────
today = datetime.now().strftime("%A, %d %B %Y")

DISCLAIMER = "\n—\n🤖 AI generated | #HeartbeatIN"

GUIDELINES = """
Strict content rules — follow these without exception:
- Report only verified facts. No rumours, speculation, or unconfirmed claims
- If a story is disputed or developing, use "reports suggest" or "sources say"
- Strictly neutral tone — no political bias left, right, or centre
- No commentary on religion, caste, community, or ethnicity
- No personal attacks or negative language about individuals
- Avoid emotionally charged or sensational language
- No opinions — only facts and context"""

MORNING = f"""Today is {today}.

Search the web for today's top India news and write a tweet up to 650 characters.

Cover ONLY these topics — politics, government, national affairs, social issues,
weather, crime, sports. Do NOT mention stock markets, Sensex, Nifty, or business.

Format: use emoji anchors, cover 3-4 stories, short punchy lines per story,
natural line breaks. Add 2 relevant hashtags at the end.
{GUIDELINES}

CRITICAL: Output ONLY the tweet text. No thinking, no "let me search",
no "based on results", no explanation. Just the tweet. Nothing else.
Do not include a disclaimer — it will be added automatically."""

AFTERNOON = f"""Today is {today}.

Search the web for today's India markets and business news and write a tweet
up to 650 characters.

Cover ONLY these topics — Sensex, Nifty, RBI, startup funding, corporate earnings,
economy, trade, budget. Do NOT repeat any politics or national news from the morning.

Format: use emoji anchors, cover 3-4 stories, short punchy lines per story,
natural line breaks. Add 1-2 relevant hashtags at the end.
{GUIDELINES}

CRITICAL: Output ONLY the tweet text. No thinking, no "let me search",
no "based on results", no explanation. Just the tweet. Nothing else.
Do not include a disclaimer — it will be added automatically."""

EVENING = f"""Today is {today}. You are writing for @HeartbeatIN_, an India news account.

Search the web for a real event that happened on today's exact date in history
with an India angle. Also search today's trending India topics.

Write a "Did You Know? On This Day" Twitter thread — exactly 6 tweets numbered
[1/6] through [6/6]. Each tweet up to 270 characters:

[1/6] Hook — "Did you know? On this day X years ago..." one dramatic opening line
[2/6] Set the scene — what was India or the world like at that time
[3/6] The event itself — what actually happened
[4/6] Immediate impact — reactions and consequences at the time
[5/6] The surprising angle — something most people don't know
[6/6] Connect to a trending India topic today. End with a question. Add 1-2 hashtags.
{GUIDELINES}

CRITICAL: Output ONLY the 6 numbered tweets. No thinking, no "let me search",
no "based on results", no explanation before or after. Nothing else.
Do not include a disclaimer — it will be added automatically to the first tweet."""

# ── Generate tweet ────────────────────────────────────────────
def generate_tweet(prompt):
    response = claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )
    return "".join(
        b.text for b in response.content if b.type == "text"
    ).strip()

# ── Parse thread ──────────────────────────────────────────────
def parse_thread(text):
    matches = re.findall(r'\[\d+/\d+\][^\[]+', text)
    if matches and len(matches) > 1:
        return [t.strip() for t in matches]
    return [text]

# ── Post tweet or thread ──────────────────────────────────────
def post_tweet(text):
    import time
    tweets = parse_thread(text)

    if len(tweets) == 1:
        # Append disclaimer to single tweet
        final = tweets[0] + DISCLAIMER
        result = twitter.create_tweet(text=final)
        logging.info(f"Posted single tweet ID: {result.data['id']}")
        print(f"✅ Tweet posted: {result.data['id']}")
    else:
        last_id = None
        for i, tweet in enumerate(tweets):
            # Append disclaimer to first tweet of thread only
            final = (tweet + DISCLAIMER) if i == 0 else tweet
            payload = {"text": final}
            if last_id:
                payload["in_reply_to_tweet_id"] = last_id
            result = twitter.create_tweet(**payload)
            last_id = result.data["id"]
            logging.info(f"Thread [{i+1}/{len(tweets)}] posted ID: {last_id}")
            print(f"✅ Thread [{i+1}/{len(tweets)}] posted: {last_id}")
            time.sleep(2)

# ── Main ──────────────────────────────────────────────────────
def main():
    slot = sys.argv[1] if len(sys.argv) > 1 else "morning"
    prompts = {
        "morning": MORNING,
        "afternoon": AFTERNOON,
        "evening": EVENING,
    }

    if slot not in prompts:
        print(f"❌ Unknown slot '{slot}'. Use: morning / afternoon / evening")
        sys.exit(1)

    print(f"\n🤖 Running {slot} tweet [{datetime.now().strftime('%H:%M IST')}]")
    logging.info(f"Starting {slot} slot")

    try:
        text = generate_tweet(prompts[slot])
        print(f"📝 Generated:\n{text}\n")
        post_tweet(text)
        logging.info(f"Completed {slot} slot successfully")
    except Exception as e:
        logging.error(f"Error in {slot} slot: {e}")
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()