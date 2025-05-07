import praw
import requests
import time
import json
import os
from flask import Flask, render_template_string, request, jsonify
from dotenv import load_dotenv
import concurrent.futures

# Load environment variables from .env file
load_dotenv()

# ==== CONFIGURATION ====

# Reddit API credentials
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_SECRET = os.getenv("REDDIT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT")

# Perspective API
PERSPECTIVE_API_KEY = os.getenv("PERSPECTIVE_API_KEY")
PERSPECTIVE_API_URL = "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"

# Attributes to check
ATTRIBUTES = ["TOXICITY", "SEVERE_TOXICITY", "INSULT", "THREAT", "IDENTITY_ATTACK"]

# Score threshold
THRESHOLD = 0.2

# Log file path
LOG_FILE = "flagged_posts.json"

# =======================

# Flask app
app = Flask(__name__)

# Reddit instance
reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_SECRET,
    user_agent=REDDIT_USER_AGENT
)

def analyze_text_with_perspective(text):
    data = {
        "comment": {"text": text},
        "languages": ["en"],
        "requestedAttributes": {attr: {} for attr in ATTRIBUTES}
    }
    response = requests.post(
        f"{PERSPECTIVE_API_URL}?key={PERSPECTIVE_API_KEY}",
        json=data
    )
    return response.json()

def process_post(post):
    text = post.title + "\n" + (post.selftext or "")
    if len(text.strip()) < 20:
        return None

    result = analyze_text_with_perspective(text)
    if "attributeScores" not in result:
        return None

    scores = {
        attr: result["attributeScores"][attr]["summaryScore"]["value"]
        for attr in ATTRIBUTES
    }

    if any(score >= THRESHOLD for score in scores.values()):
        flagged_post = {
            "title": post.title,
            "url": post.url,
            "scores": scores
        }
        return flagged_post
    return None

def scan_subreddit(subreddit_name):
    subreddit = reddit.subreddit(subreddit_name)
    flagged = []
    posts = subreddit.new(limit=20)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(process_post, posts))

    flagged = [post for post in results if post is not None]
    return flagged

@app.route("/", methods=["GET", "POST"])
def dashboard():
    subreddit_name = request.args.get('subreddit', 'Conservative')  # default to 'Conservative'
    
    if request.method == "POST":
        subreddit_name = request.form.get('subreddit')

    posts = scan_subreddit(subreddit_name)

    with open(LOG_FILE, "w") as f:
        json.dump(posts, f, indent=2)

    return render_template_string("""
    <html>
    <head>
        <title>Hate Speech Detection Dashboard</title>
        <style>
            body { font-family: Arial; padding: 20px; }
            .card { border: 1px solid #ccc; padding: 15px; margin-bottom: 15px; border-radius: 8px; }
            .score { margin-left: 10px; font-weight: bold; }
            input[type="text"] { padding: 5px; font-size: 14px; }
            input[type="submit"] { padding: 5px 10px; font-size: 14px; }
        </style>
    </head>
    <body>
        <h1>🚨 Flagged Posts from r/{{ subreddit_name }}</h1>
        
        <form method="post" action="/">
            <label for="subreddit">Search Subreddit: </label>
            <input type="text" id="subreddit" name="subreddit" value="{{ subreddit_name }}">
            <input type="submit" value="Search">
        </form>
        
        {% for post in posts %}
            <div class="card">
                <h2><a href="{{ post.url }}" target="_blank">{{ post.title }}</a></h2>
                <p>
                {% for attr, score in post.scores.items() %}
                    <span>{{ attr }}: <span class="score">{{ '%.2f'|format(score) }}</span></span><br>
                {% endfor %}
                </p>
            </div>
        {% endfor %}
    </body>
    </html>
    """, posts=posts, subreddit_name=subreddit_name)

if __name__ == "__main__":
    print("🚀 Starting Flask dashboard on http://localhost:5000")
    app.run(debug=True)
