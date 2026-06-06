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

MORNING = f"""Today is {today}. Write a single tweet (max 270 chars) summarizing
the top 3 India morning news stories. Concise, factual, engaging. Add 2 hashtags.
Search the web for real news from today. Plain text only, no markdown."""

AFTERNOON = f"""Today is {today}. Write a single tweet (max 270 chars) about the
biggest Indian market or business news right now. Include Sensex/Nifty movement
if relevant. Search the web for real data. Add 1-2 hashtags. Plain text only."""

EVENING = f"""Today is {today}. You are writing for @HeartbeatIN_, an India news account.

Create a "Did You Know? On This Day" Twitter thread (6 tweets) about something
significant that happened on this exact date in history, with an India angle.

Thread format — number each tweet exactly as [1/6], [2/6] etc.:
[1/6] Hook — "Did you know? On this day X years ago..." one dramatic opening line
[2/6] Set the scene — what was India/the world like at that time
[3/6] The event itself — what actually happened
[4/6] Immediate impact — reactions, consequences at the time
[5/6] The surprising angle — something most people don't know about it
[6/6] Connect to today's trending India news. End with a question. Add 1-2 hashtags.

Rules:
- Search the web for a real historical event on today's exact date with India relevance
- Also search today's trending India topics to make the [6/6] connection natural
- Each tweet must be under 280 characters
- Tell it like a story, not a Wikipedia entry
- Make [1/6] so compelling readers MUST continue"""

# ── Generate tweet ────────────────────────────────────────────
def generate_tweet(prompt):
    response = claude.messages.create(
        model="claude-sonnet-4-20250514",
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
    tweets = parse_thread(text)
    if len(tweets) == 1:
        result = twitter.create_tweet(text=tweets[0])
        logging.info(f"Posted single tweet ID: {result.data['id']}")
        print(f"✅ Tweet posted: {result.data['id']}")
    else:
        last_id = None
        for i, tweet in enumerate(tweets):
            payload = {"text": tweet}
            if last_id:
                payload["in_reply_to_tweet_id"] = last_id
            result = twitter.create_tweet(**payload)
            last_id = result.data["id"]
            logging.info(f"Thread [{i+1}/{len(tweets)}] posted ID: {last_id}")
            print(f"✅ Thread [{i+1}/{len(tweets)}] posted: {last_id}")
            import time; time.sleep(2)

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