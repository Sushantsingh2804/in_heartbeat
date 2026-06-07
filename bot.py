import anthropic
import tweepy
import os
import sys
import re
import time
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

# ── Config ────────────────────────────────────────────────────
today = datetime.now().strftime("%A, %d %B %Y")
DISCLAIMER = "\n—\n🤖 AI generated | #HeartbeatIN"

# ── System prompt ─────────────────────────────────────────────
SYSTEM = """You are a tweet writer for @HeartbeatIN_, an India news account.
Search the web for today's news, then write the tweet.

Content rules:
- Verified facts only. Use "reports suggest" for unconfirmed stories
- Strictly neutral — no political bias, no religion or caste commentary
- No personal attacks, no sensational language
- For sports: ONLY report results that have already happened today.
  Never report upcoming matches as if they are happening today.
  If unsure whether a match has happened, skip it.

Output rule — ALWAYS wrap your tweet in XML tags:
<tweet>
your tweet text here
</tweet>

Write ONLY inside the tags. Nothing outside."""

# ── Slot prompts ──────────────────────────────────────────────
SLOTS = {
    "morning": f"""Today is {today}.
Search for today's top India news — politics, government, national affairs, weather, sports.
Write a tweet up to 650 chars. Use emoji anchors, cover 3-4 stories, short punchy lines.
Add 2 hashtags. Wrap in <tweet> tags.""",

    "afternoon": f"""Today is {today}.
Search for today's India markets and business news — Sensex, Nifty, RBI, startups, economy.
Write a tweet up to 650 chars. Use emoji anchors, cover 3-4 stories, short punchy lines.
Add 1-2 hashtags. Wrap in <tweet> tags.""",

    "evening": f"""Today is {today}.
Search for a real historical event on today's exact date with an India angle.
Also search today's top trending India topic.
Write a "Did You Know? On This Day" thread — exactly 6 tweets [1/6] to [6/6], each under 270 chars:
[1/6] Hook — "Did you know? On this day X years ago..." one dramatic line
[2/6] Set the scene — what was India like at that time
[3/6] The event — what actually happened
[4/6] Immediate impact — reactions and consequences
[5/6] Surprising angle — something most people don't know
[6/6] Connect to today's trending India topic. End with a question. Add 1-2 hashtags.
Wrap all 6 tweets in <tweet> tags."""
}

# ── Generate tweet ────────────────────────────────────────────
def generate_tweet(slot):
    response = claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1200,
        system=SYSTEM,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": SLOTS[slot]}]
    )

    raw = "".join(
        b.text for b in response.content if b.type == "text"
    ).strip()

    # Try XML extraction first
    match = re.search(r'<tweet>(.*?)</tweet>', raw, re.DOTALL)
    if match:
        return match.group(1).strip()

    # No XML tags — prefill extraction fallback
    logging.warning(f"No <tweet> tags for {slot}, running extraction call")
    extract = claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=800,
        messages=[
            {
                "role": "user",
                "content": f"Extract ONLY the final tweet text from this. Nothing else:\n\n{raw}"
            },
            {
                "role": "assistant",
                "content": "<tweet>"
            }
        ]
    )

    extracted = "".join(
        b.text for b in extract.content if b.type == "text"
    ).strip().replace("</tweet>", "").strip()

    return extracted

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
        result = twitter.create_tweet(text=tweets[0] + DISCLAIMER)
        logging.info(f"Posted tweet ID: {result.data['id']}")
        print(f"✅ Posted: {result.data['id']}")
    else:
        last_id = None
        for i, tweet in enumerate(tweets):
            final = (tweet + DISCLAIMER) if i == 0 else tweet
            payload = {"text": final}
            if last_id:
                payload["in_reply_to_tweet_id"] = last_id
            result = twitter.create_tweet(**payload)
            last_id = result.data["id"]
            logging.info(f"Thread [{i+1}/{len(tweets)}] ID: {last_id}")
            print(f"✅ Thread [{i+1}/{len(tweets)}] posted: {last_id}")
            time.sleep(2)

# ── Main ──────────────────────────────────────────────────────
def main():
    slot = sys.argv[1] if len(sys.argv) > 1 else "morning"

    if slot not in SLOTS:
        print(f"❌ Unknown slot '{slot}'. Use: morning / afternoon / evening")
        sys.exit(1)

    print(f"\n🤖 {slot} [{datetime.now().strftime('%H:%M IST')}]")
    logging.info(f"Starting {slot}")

    try:
        text = generate_tweet(slot)
        print(f"\n📝 Generated:\n{text}\n")
        print(f"📝 Final with disclaimer:\n{text + DISCLAIMER}\n")
        post_tweet(text)
        logging.info(f"Completed {slot} successfully")
    except Exception as e:
        logging.error(f"Error in {slot}: {e}")
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()