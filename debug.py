import anthropic
import tweepy
import os
import re
import sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

twitter = tweepy.Client(
    consumer_key=os.getenv("TWITTER_CLIENT_ID"),
    consumer_secret=os.getenv("TWITTER_CLIENT_SECRET"),
    access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
    access_token_secret=os.getenv("TWITTER_ACCESS_TOKEN_SECRET"),
)

today = datetime.now().strftime("%A, %d %B %Y")

SYSTEM = """You are a reply writer for @HeartbeatIN_, an India news account.
Search for a real historical event on today's exact date connected to the tweet topic.
Then write a short reply using that fact.

Content rules:
- Verified historical facts only. Nothing speculative
- Neutral tone — no political bias, no religion or caste commentary
- No personal attacks or sensational language

Output rule — ALWAYS wrap your reply in XML tags:
<reply>
your reply here
</reply>

If no relevant historical event exists for today's date write:
<reply>NO_MATCH</reply>

Write ONLY inside the tags. Nothing outside."""

# ── Account to test against ───────────────────────────────────
# Change this to test against different accounts
TEST_ACCOUNT = sys.argv[1] if len(sys.argv) > 1 else "NSEIndia"

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
        print(f"❌ Could not fetch @{username}: {e}")
    return None

# ── Run ───────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"DEBUG MODE — REPLY BOT — {today}")
print(f"Testing against: @{TEST_ACCOUNT}")
print(f"{'='*60}")

# Fetch latest tweet
print(f"\n🔍 Fetching latest tweet from @{TEST_ACCOUNT}...")
tweet = get_latest_tweet(TEST_ACCOUNT)

if not tweet:
    print(f"❌ Could not fetch tweet from @{TEST_ACCOUNT}")
    sys.exit(1)

print(f"\n📌 Tweet fetched (ID: {tweet.id}):")
print(f"   {tweet.text}\n")
print(f"{'='*60}")

# Build prompt
prompt = f"""Today is {today}.
@{TEST_ACCOUNT} tweeted: "{tweet.text}"

Search for a real historical event on today's exact date connected to this tweet.
Write a reply under 240 chars starting with "Did you know that on this day [X years ago]..."
Wrap in <reply> tags."""

print(f"\n📤 PROMPT SENT:\n{prompt}\n")
print(f"{'='*60}")

# Call API
response = claude.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=400,
    system=SYSTEM,
    tools=[{"type": "web_search_20250305", "name": "web_search"}],
    messages=[{"role": "user", "content": prompt}]
)

# Print raw blocks
print(f"\n📦 RAW CONTENT BLOCKS:\n")
for i, block in enumerate(response.content):
    print(f"  Block {i+1}: type={block.type}")
    if block.type == "text":
        print(f"  Text:\n{block.text}\n")

# Join text blocks
raw = "".join(
    b.text for b in response.content if b.type == "text"
).strip()

print(f"{'='*60}")
print(f"\n📝 FULL TEXT OUTPUT:\n{raw}\n")
print(f"{'='*60}")

# Try XML extraction
match = re.search(r'<reply>(.*?)</reply>', raw, re.DOTALL)
if match:
    result = match.group(1).strip()
    if result == "NO_MATCH":
        print(f"\n⚠️  Claude returned NO_MATCH — no historical event found for today")
    else:
        print(f"\n✅ XML EXTRACTION SUCCESS ({len(result)} chars):")
        print(f"\n{result}\n")
else:
    print(f"\n❌ NO <reply> TAGS FOUND — running prefill extraction...")
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

    print(f"\n📤 PREFILL EXTRACTION RESULT ({len(extracted)} chars):")
    print(f"\n{extracted}\n")

print(f"{'='*60}")
print("✅ Debug complete — nothing was posted to Twitter")
print(f"{'='*60}\n")