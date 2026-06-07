import anthropic
import tweepy
import os
import re
import json
import time
import random
import logging
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    filename="reply_bot.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# ── Clients ───────────────────────────────────────────────────
claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

twitter = tweepy.Client(
    bearer_token=os.getenv("TWITTER_BEARER_TOKEN"),
    consumer_key=os.getenv("TWITTER_CLIENT_ID"),
    consumer_secret=os.getenv("TWITTER_CLIENT_SECRET"),
    access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
    access_token_secret=os.getenv("TWITTER_ACCESS_TOKEN_SECRET"),
)

# ── Config ────────────────────────────────────────────────────
DAILY_REPLY_LIMIT = 3
MIN_DELAY_SECS    = 300
MAX_DELAY_SECS    = 900
COUNTER_FILE      = "reply_counter.json"
REPLIED_IDS_FILE  = "replied_ids.json"

# ── System prompt ─────────────────────────────────────────────
SYSTEM = """You are a reply writer for @HeartbeatIN_, an India news account.
Search the web for a relevant fact, stat, or insight about the tweet topic.
Then write a short reply that adds genuine value.

Content rules:
- Verified facts and stats only. Nothing speculative
- Neutral tone — no political bias, no religion or caste commentary
- No personal attacks or sensational language
- Do NOT repeat any information already mentioned in the tweet
- Add something NEW — a stat, trend, context, or angle not in the original tweet

Output rule — ALWAYS wrap your reply in XML tags:
<reply>
your reply here
</reply>

If you cannot find a relevant fact that adds new value, write:
<reply>NO_MATCH</reply>

Write ONLY inside the tags. Nothing outside."""

# ── Target accounts ───────────────────────────────────────────
TARGET_ACCOUNTS = [
    "NSEIndia", "BSEIndia", "RBI", "zerodhaonline", "Nithin0dha", "monikahalan",
    "ANI", "ndtv", "timesofindia", "the_hindu", "IndianExpress", "suchindra",
    "Inc42Media", "nikhilkamathcio", "StartupIndia",
    "IndiaHistoryPic", "zoo_bear",
]

# ── Daily counter ─────────────────────────────────────────────
def get_today_count():
    try:
        with open(COUNTER_FILE, "r") as f:
            data = json.load(f)
        if data.get("date") == str(date.today()):
            return data.get("count", 0)
    except Exception:
        pass
    return 0

def increment_count():
    count = get_today_count() + 1
    with open(COUNTER_FILE, "w") as f:
        json.dump({"date": str(date.today()), "count": count}, f)
    return count

# ── Replied ID tracking ───────────────────────────────────────
def get_replied_ids():
    try:
        with open(REPLIED_IDS_FILE, "r") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_replied_id(tweet_id):
    ids = list(get_replied_ids())
    ids.append(str(tweet_id))
    with open(REPLIED_IDS_FILE, "w") as f:
        json.dump(ids[-500:], f)

# ── Generate reply ────────────────────────────────────────────
def generate_reply(tweet_text, username):
    today = datetime.now().strftime("%A, %d %B %Y")

    response = claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=400,
        system=SYSTEM,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{
            "role": "user",
            "content": f"""Today is {today}.
@{username} tweeted: "{tweet_text}"

Step 1 — identify the main topic of this tweet.
Step 2 — search for a current, relevant fact or stat about that SAME topic.
Step 3 — write a reply under 240 chars that adds new insight.

Rules:
- Must be about the exact same topic as the tweet
- Must NOT repeat anything already said in the tweet
- Must add a new fact, stat, or angle the tweet didn't mention
- If no genuinely new insight found, output NO_MATCH

Wrap reply in <reply> tags."""
        }]
    )

    raw = "".join(
        b.text for b in response.content if b.type == "text"
    ).strip()

    # Try XML extraction
    match = re.search(r'<reply>(.*?)</reply>', raw, re.DOTALL)
    if match:
        result = match.group(1).strip()
        if result == "NO_MATCH" or len(result) < 20:
            return "NO_MATCH"
        return result

    # Prefill fallback
    logging.warning(f"No <reply> tags for @{username}, running prefill extraction")
    extract = claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=300,
        messages=[
            {
                "role": "user",
                "content": f"Extract ONLY the final reply tweet from this. Nothing else:\n\n{raw}"
            },
            {
                "role": "assistant",
                "content": "<reply>"
            }
        ]
    )

    extracted = "".join(
        b.text for b in extract.content if b.type == "text"
    ).strip().replace("</reply>", "").strip()

    if not extracted or len(extracted) < 20 or "NO_MATCH" in extracted:
        return "NO_MATCH"

    return extracted

# ── Get latest tweet ──────────────────────────────────────────
def get_latest_tweet(username):
    try:
        user = twitter.get_user(username=username)
        if not user.data:
            return None
        tweets = twitter.get_users_tweets(
            user.data.id,
            max_results=5,
            exclude=["retweets", "replies"]
        )
        if tweets.data:
            return tweets.data[0]
    except Exception as e:
        logging.warning(f"Could not fetch @{username}: {e}")
    return None

# ── Post reply ────────────────────────────────────────────────
def post_reply(reply_text, tweet_id, username):
    result = twitter.create_tweet(
        text=reply_text,
        in_reply_to_tweet_id=tweet_id
    )
    save_replied_id(tweet_id)
    logging.info(f"Reply posted to @{username} — ID {result.data['id']}")
    print(f"  ✅ Reply posted to @{username}!")
    return result.data["id"]

# ── Main ──────────────────────────────────────────────────────
def main():
    print(f"\n🤖 reply_bot [{datetime.now().strftime('%A %d %B %Y · %H:%M')}]")
    logging.info("reply_bot session started")

    count = get_today_count()
    if count >= DAILY_REPLY_LIMIT:
        print(f"✋ Daily limit reached ({count}/{DAILY_REPLY_LIMIT}). Exiting.")
        return

    replied_ids  = get_replied_ids()
    accounts     = TARGET_ACCOUNTS.copy()
    random.shuffle(accounts)
    posted_today = count

    for username in accounts:
        if posted_today >= DAILY_REPLY_LIMIT:
            print(f"\n✅ Daily limit hit. Done for today.")
            break

        print(f"\n  Checking @{username}...")
        tweet = get_latest_tweet(username)
        if not tweet:
            continue

        if str(tweet.id) in replied_ids:
            print(f"  ↳ Already replied, skipping.")
            continue

        try:
            reply = generate_reply(tweet.text, username)
        except Exception as e:
            logging.error(f"Claude error for @{username}: {e}")
            continue

        if reply == "NO_MATCH":
            print(f"  ↳ No relevant insight found, skipping.")
            continue

        if len(reply) > 280:
            print(f"  ↳ Too long ({len(reply)} chars), skipping.")
            continue

        print(f"  📌 @{username}: {tweet.text[:80]}...")
        print(f"  💬 Reply ({len(reply)} chars): {reply}")

        try:
            post_reply(reply, tweet.id, username)
            posted_today = increment_count()
            print(f"  📊 {posted_today}/{DAILY_REPLY_LIMIT} today")
        except Exception as e:
            logging.error(f"Post failed for @{username}: {e}")
            print(f"  ❌ Post failed: {e}")
            continue

        if posted_today < DAILY_REPLY_LIMIT:
            delay = random.randint(MIN_DELAY_SECS, MAX_DELAY_SECS)
            print(f"\n  ⏳ Waiting {delay // 60} min...")
            time.sleep(delay)

    print(f"\n🏁 Done. Posted {posted_today}/{DAILY_REPLY_LIMIT} today.")
    logging.info(f"Session complete. Posted {posted_today}/{DAILY_REPLY_LIMIT}")

if __name__ == "__main__":
    main()