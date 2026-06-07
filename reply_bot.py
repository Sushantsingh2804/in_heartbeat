import anthropic
import tweepy
import os
import json
import re
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
DAILY_REPLY_LIMIT = 3
MIN_DELAY_SECS    = 300
MAX_DELAY_SECS    = 900
COUNTER_FILE      = "reply_counter.json"
REPLIED_IDS_FILE  = "replied_ids.json"

# ── Guidelines (same as bot.py) ───────────────────────────────
GUIDELINES = """CONTENT RULES — non-negotiable:
- Report only verified historical facts. No rumours or speculation
- Strictly neutral tone — no political bias left, right, or centre
- No commentary on religion, caste, community, or ethnicity
- No personal attacks or negative language about individuals
- Avoid emotionally charged or sensational language
- If uncertain about a fact, do not include it"""

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
    ids = ids[-500:]
    with open(REPLIED_IDS_FILE, "w") as f:
        json.dump(ids, f)

# ── Generate reply (two-step + XML extraction) ────────────────
def generate_reply(tweet_text, username):
    today = datetime.now().strftime("%A, %d %B %Y")

    # Step 1 — research only, find historical fact for today's date
    research = claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=800,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{
            "role": "user",
            "content": f"""Today is {today}.

@{username} tweeted: "{tweet_text}"

Search for a real historical event that happened on today's exact date
that connects to the topic of this tweet.

Return ONLY bullet points with:
- The historical event (what happened, when, key facts)
- How it connects to the tweet topic
- Any relevant numbers or statistics

If no relevant historical event exists for today's date, return exactly: NO_MATCH
No reply tweet. No commentary. Just the facts or NO_MATCH."""
        }]
    )

    facts = "".join(
        b.text for b in research.content if b.type == "text"
    ).strip()

    # If no match found in research, exit early
    if "NO_MATCH" in facts or len(facts) < 20:
        return "NO_MATCH"

    # Step 2 — write reply from facts, NO tools, XML tags for clean extraction
    reply_response = claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=300,
        system=f"""You are a reply writer for @HeartbeatIN_, an India news account.

{GUIDELINES}

OUTPUT FORMAT — you MUST wrap your reply in <reply> tags:
<reply>
Your reply tweet text goes here
</reply>

Write ONLY inside the tags. Nothing outside the tags.
If the facts don't support a strong reply, write NO_MATCH inside the tags.""",
        messages=[{
            "role": "user",
            "content": f"""Here are the researched historical facts:

{facts}

Using these facts, write a reply tweet (under 240 chars) that:
1. Starts with "Did you know that on this day [X years ago]..."
2. Connects naturally to what @{username} tweeted: "{tweet_text}"
3. Adds genuine value — real fact, stat, or surprising angle
4. Feels like a smart human adding context, not a bot

Wrap your reply in <reply></reply> tags."""
        }]
    )

    raw = "".join(
        b.text for b in reply_response.content if b.type == "text"
    ).strip()

    # Extract reply from XML tags
    match = re.search(r'<reply>(.*?)</reply>', raw, re.DOTALL)
    if match:
        result = match.group(1).strip()
        if not result or len(result) < 20 or "NO_MATCH" in result:
            return "NO_MATCH"
        return result

    logging.warning(f"No <reply> tags found for @{username}")
    return "NO_MATCH"

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
    logging.info(
        f"Reply posted to @{username} tweet {tweet_id} "
        f"— reply ID {result.data['id']}"
    )
    print(f"  ✅ Reply posted to @{username}!")
    return result.data["id"]

# ── Main ──────────────────────────────────────────────────────
def main():
    print(f"\n🤖 reply_bot starting [{datetime.now().strftime('%A %d %B %Y · %H:%M')}]")
    logging.info("reply_bot session started")

    count = get_today_count()
    if count >= DAILY_REPLY_LIMIT:
        print(f"✋ Daily limit reached ({count}/{DAILY_REPLY_LIMIT}). Exiting.")
        logging.info(f"Daily limit reached ({count}/{DAILY_REPLY_LIMIT}), exiting")
        return

    replied_ids  = get_replied_ids()
    accounts     = TARGET_ACCOUNTS.copy()
    random.shuffle(accounts)
    posted_today = count

    for username in accounts:
        if posted_today >= DAILY_REPLY_LIMIT:
            print(f"\n✅ Hit daily limit ({DAILY_REPLY_LIMIT} replies). Done for today.")
            break

        print(f"\n  Checking @{username}...")
        tweet = get_latest_tweet(username)

        if not tweet:
            continue

        if str(tweet.id) in replied_ids:
            print(f"  ↳ Already replied to this tweet, skipping.")
            continue

        print(f"  🔍 Researching historical connection...")
        try:
            reply = generate_reply(tweet.text, username)
        except Exception as e:
            logging.error(f"Claude error for @{username}: {e}")
            continue

        if reply == "NO_MATCH":
            print(f"  ↳ No relevant 'On This Day' match found, skipping.")
            logging.info(f"No match for @{username} tweet {tweet.id}")
            continue

        if len(reply) > 280:
            print(f"  ↳ Reply too long ({len(reply)} chars), skipping.")
            continue

        print(f"\n  📌 @{username}: {tweet.text[:80]}...")
        print(f"  💬 Reply ({len(reply)} chars): {reply}")

        try:
            post_reply(reply, tweet.id, username)
            posted_today = increment_count()
            print(f"  📊 Daily count: {posted_today}/{DAILY_REPLY_LIMIT}")
        except Exception as e:
            logging.error(f"Failed to post reply to @{username}: {e}")
            print(f"  ❌ Post failed: {e}")
            continue

        if posted_today < DAILY_REPLY_LIMIT:
            delay = random.randint(MIN_DELAY_SECS, MAX_DELAY_SECS)
            print(f"\n  ⏳ Waiting {delay // 60} min before next reply...")
            logging.info(f"Sleeping {delay}s before next reply")
            time.sleep(delay)

    print(
        f"\n🏁 Session complete. "
        f"Replies posted today: {posted_today}/{DAILY_REPLY_LIMIT}"
    )
    logging.info(f"Session complete. Posted {posted_today}/{DAILY_REPLY_LIMIT}")

if __name__ == "__main__":
    main()