import anthropic
import tweepy
import os
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
    consumer_key=os.getenv("TWITTER_CLIENT_ID"),
    consumer_secret=os.getenv("TWITTER_CLIENT_SECRET"),
    access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
    access_token_secret=os.getenv("TWITTER_ACCESS_TOKEN_SECRET"),
)

# ── Config ────────────────────────────────────────────────────
DAILY_REPLY_LIMIT   = 3          # max replies per day
MIN_DELAY_SECS      = 300        # 5 min minimum between replies
MAX_DELAY_SECS      = 900        # 15 min maximum between replies
COUNTER_FILE        = "reply_counter.json"
REPLIED_IDS_FILE    = "replied_ids.json"

# ── Target accounts ───────────────────────────────────────────
TARGET_ACCOUNTS = [
    # Markets & finance
    "NSEIndia", "BSEIndia", "RBI", "zerodhaonline", "Nithin0dha", "monikahalan",
    # News & journalism
    "ANI", "ndtv", "timesofindia", "the_hindu", "IndianExpress", "suchindra",
    # Tech & startups
    "Inc42Media", "nikhilkamathcio", "StartupIndia",
    # History & culture
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

# ── Replied ID tracking (avoid replying to same tweet twice) ──
def get_replied_ids():
    try:
        with open(REPLIED_IDS_FILE, "r") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_replied_id(tweet_id):
    ids = list(get_replied_ids())
    ids.append(str(tweet_id))
    ids = ids[-500:]          # keep last 500 only
    with open(REPLIED_IDS_FILE, "w") as f:
        json.dump(ids, f)

# ── Generate reply ────────────────────────────────────────────
def generate_reply(tweet_text, username):
    today = datetime.now().strftime("%A, %d %B %Y")

    response = claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=300,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{
            "role": "user",
            "content": f"""Today is {today}.

@{username} just tweeted: "{tweet_text}"

Write a reply tweet (under 240 chars) for @HeartbeatIN_ that:
1. Starts with a relevant "Did you know that on this day [X years ago]..." historical fact
2. Connects naturally and specifically to what they tweeted about
3. Adds genuine value — a real fact, stat, or surprising angle
4. Feels like a smart human adding context, not a bot

Search for a real historical event on today's exact date that genuinely 
connects to the topic they tweeted about.

If no relevant "on this day" connection exists, reply with exactly: NO_MATCH

CRITICAL: Output ONLY the tweet text or NO_MATCH. No thinking, no "let me search",
no "based on results", no explanation. Just the reply text. Nothing else."""
        }]
    )

    return "".join(
        b.text for b in response.content if b.type == "text"
    ).strip()

# ── Get latest tweet from account ────────────────────────────
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
    tweet_id_posted = result.data["id"]
    logging.info(f"Reply posted to @{username} tweet {tweet_id} — reply ID {tweet_id_posted}")
    print(f"  ✅ Reply posted to @{username}!")
    return tweet_id_posted

# ── Main ──────────────────────────────────────────────────────
def main():
    print(f"\n🤖 reply_bot starting [{datetime.now().strftime('%A %d %B %Y · %H:%M')}]")
    logging.info("reply_bot session started")

    # Check daily limit
    count = get_today_count()
    if count >= DAILY_REPLY_LIMIT:
        print(f"✋ Daily limit reached ({count}/{DAILY_REPLY_LIMIT}). Exiting.")
        logging.info(f"Daily limit already reached ({count}/{DAILY_REPLY_LIMIT}), exiting")
        return

    replied_ids  = get_replied_ids()
    accounts     = TARGET_ACCOUNTS.copy()
    random.shuffle(accounts)   # different order every run = more natural
    posted_today = count

    for username in accounts:
        if posted_today >= DAILY_REPLY_LIMIT:
            print(f"\n✅ Hit daily limit ({DAILY_REPLY_LIMIT} replies). Done for today.")
            break

        print(f"\n  Checking @{username}...")
        tweet = get_latest_tweet(username)

        if not tweet:
            continue

        # Skip if already replied to this tweet
        if str(tweet.id) in replied_ids:
            print(f"  ↳ Already replied to this tweet, skipping.")
            continue

        # Generate reply
        try:
            reply = generate_reply(tweet.text, username)
        except Exception as e:
            logging.error(f"Claude error for @{username}: {e}")
            continue

        if reply == "NO_MATCH" or not reply or len(reply) < 20:
            print(f"  ↳ No relevant 'On This Day' match found, skipping.")
            logging.info(f"No match for @{username} tweet {tweet.id}")
            continue

        if len(reply) > 280:
            print(f"  ↳ Reply too long ({len(reply)} chars), skipping.")
            continue

        print(f"\n  📌 @{username}: {tweet.text[:80]}...")
        print(f"  💬 Reply ({len(reply)} chars): {reply}")

        # Post reply
        try:
            post_reply(reply, tweet.id, username)
            posted_today = increment_count()
            print(f"  📊 Daily count: {posted_today}/{DAILY_REPLY_LIMIT}")
        except Exception as e:
            logging.error(f"Failed to post reply to @{username}: {e}")
            print(f"  ❌ Post failed: {e}")
            continue

        # Random delay between replies — looks natural, avoids spam flags
        if posted_today < DAILY_REPLY_LIMIT:
            delay = random.randint(MIN_DELAY_SECS, MAX_DELAY_SECS)
            mins  = delay // 60
            print(f"\n  ⏳ Waiting {mins} min before next reply...")
            logging.info(f"Sleeping {delay}s before next reply")
            time.sleep(delay)

    print(f"\n🏁 Session complete. Replies posted today: {posted_today}/{DAILY_REPLY_LIMIT}")
    logging.info(f"Session complete. Posted {posted_today}/{DAILY_REPLY_LIMIT}")

if __name__ == "__main__":
    main()