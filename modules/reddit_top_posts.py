import requests
import time
import json
import os
import re

CACHE_FILE = "reddit_cache.json"
CACHE_DURATION = 300  # seconds (5 minutes)

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)

def strip_emojis(text):
    # Remove emojis / non-ASCII characters
    return re.sub(r'[^\x00-\x7F]+', '', text)

def get_top_posts(subreddit, limit=5):
    # Load cache
    cache = load_cache()
    now = time.time()
    if subreddit in cache and now - cache[subreddit]["timestamp"] < CACHE_DURATION:
        return cache[subreddit]["posts"]

    url = f"https://old.reddit.com/r/{subreddit}/top/.json?limit={limit}&t=day"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36"
    }

    posts = []
    for attempt in range(3):  # retry up to 3 times
        try:
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                children = data["data"]["children"]
                if children:
                    for post in children[:limit]:
                        title = strip_emojis(post["data"]["title"])
                        link = "https://reddit.com" + post["data"]["permalink"]
                        # Use <link> style to prevent preview
                        posts.append(f"{title} <{link}>")
                    break
        except Exception as e:
            print(f"Error fetching {subreddit}: {e}")
        time.sleep(1)  # wait before retrying

    # Save to cache
    cache[subreddit] = {"timestamp": now, "posts": posts}
    save_cache(cache)
    return posts

if __name__ == "__main__":
    top_posts = get_top_posts("Amazing", 5)
    if not top_posts:
        print("No posts available.")
    else:
        for i, post in enumerate(top_posts, start=1):
            print(f"{i}. {post}")
