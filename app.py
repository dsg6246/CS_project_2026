from flask import Flask, render_template, request, jsonify
import requests
import json
import os
import sqlite3
from dotenv import load_dotenv
from dataclasses import dataclass, field
from time import time
import random

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("API key not found in .env")

URL = (
    "https://generativelanguage.googleapis.com"
    "/v1beta/models/gemini-2.5-flash:generateContent"
    f"?key={API_KEY}"
)

DB_FILE = "cards.db"

app = Flask(__name__)


def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS decks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deck_id INTEGER NOT NULL,
                english TEXT NOT NULL,
                spanish TEXT NOT NULL,
                interval REAL NOT NULL,
                ease REAL NOT NULL,
                next_due REAL NOT NULL,
                FOREIGN KEY(deck_id) REFERENCES decks(id)
            );
        """)

        conn.commit()

@dataclass
class Card:
    id: int
    front: str
    back: str
    interval: float = 1.0
    ease: float = 2.5
    next_due: float = field(default_factory=lambda: time())


def pick_card(cards):
    due = [c for c in cards if c.next_due <= time()]
    if due:
        return random.choice(due)
    weights = [1 / c.interval for c in cards]
    return random.choices(cards, weights=weights, k=1)[0]

def update_card(card, correct):
    now = time()
    if correct:
        card.interval = min(card.interval * card.ease, 365)
        card.ease = min(card.ease + 0.05, 3.0)
    else:
        card.interval = 1.0
        card.ease = max(card.ease - 0.2, 1.3)
    card.next_due = now + card.interval * 86400
    return None

def load_deck(deck_id):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, english, spanish, interval, ease, next_due
            FROM cards
            WHERE deck_id = ?;
        """, (deck_id,))
        rows = cursor.fetchall()

    cards = []
    for cid, english, spanish, interval, ease, next_due in rows:
        cards.append(Card(
            id=cid,
            front=english,
            back=spanish,
            interval=float(interval),
            ease=float(ease),
            next_due=float(next_due),
        ))
    return cards

def save_card(card: Card):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE cards
            SET interval = ?, ease = ?, next_due = ?
            WHERE id = ?;
        """, (card.interval, card.ease, card.next_due, card.id))
        conn.commit()


def generate_guide(material: str):
    prompt = f"""
You convert study material into flashcards.

Your task:
Return a JSON array of flashcards.

Output rules:
- Return ONLY valid JSON.
- Do NOT include markdown, code fences, or explanations.
- The output must be a JSON array.
- Each item must be an object with exactly these keys:
  - "english": string
  - "spanish": string

Behavior:
- If the input is a study guide, extract the most important terms and turn them into flashcards.
- If the input is a list of words, translate each word into Spanish.
- Be concise and accurate.

Example output format:
[
  {{
    "english": "apple",
    "spanish": "manzana"
  }}
]

Input:
{material}
""".strip()

    body = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "response_mime_type": "application/json"
        }
    }

    response = requests.post(URL, json=body, timeout=30)

    if response.status_code != 200:
        print(f"API error: {response.status_code} {response.text}")
        return None

    data = response.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

    if text.startswith("```"):
        text = text.split("\n", 1)
        text = text.rsplit("```", 1)[0]

    return json.loads(text)

def save_flashcards(flashcards, deck_name):
    if not flashcards:
        return 0

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()

        cursor.execute("INSERT OR IGNORE INTO decks (name) VALUES (?);", (deck_name,))
        cursor.execute("SELECT id FROM decks WHERE name = ?;", (deck_name,))
        deck_id = cursor.fetchone()[0]

        for card in flashcards:
            english = card.get("english")
            spanish = card.get("spanish")
            if english and spanish:
                cursor.execute(
                    "INSERT INTO cards (deck_id, english, spanish, interval, ease, next_due) "
                    "VALUES (?, ?, ?, ?, ?, ?);",
                    (deck_id, english, spanish, 1.0, 2.5, time())
                )

        conn.commit()
        return len(flashcards)

# ----------------- Flask routes -----------------

@app.route("/")
def index():
    # Render main page
    return render_template("index.html")

@app.route("/api/decks", methods=["GET"])
def list_decks():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM decks ORDER BY created_at DESC;")
        rows = cursor.fetchall()
    decks = [{"id": r[0], "name": r[1]} for r in rows]
    return jsonify(decks)

@app.route("/api/decks", methods=["POST"])
def create_deck():
    data = request.get_json()
    deck_name = data.get("name")
    material = data.get("material", "")

    if not deck_name or not material:
        return jsonify({"error": "name and material are required"}), 400

    flashcards = generate_guide(material)
    if flashcards is None:
        return jsonify({"error": "Failed to generate flashcards"}), 500

    count = save_flashcards(flashcards, deck_name)
    return jsonify({"message": "Deck created", "count": count})

@app.route("/api/next_card", methods=["GET"])
def get_next_card():
    deck_id = request.args.get("deck_id")
    if not deck_id:
        return jsonify({"error": "deck_id required"}), 400

    cards = load_deck(deck_id)
    if not cards:
        return jsonify({"error": "No cards in deck"}), 404

    card = pick_card(cards)
    return jsonify({
        "id": card.id,
        "front": card.front,
        "back": card.back
    })

@app.route("/api/check_answer", methods=["POST"])
def check_answer():
    data = request.get_json()
    deck_id = data.get("deck_id")
    card_id = data.get("card_id")
    user_answer = data.get("answer", "").strip().lower()

    if not (deck_id and card_id):
        return jsonify({"error": "deck_id and card_id required"}), 400

    # Load single card from DB
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, english, spanish, interval, ease, next_due
            FROM cards
            WHERE id = ? AND deck_id = ?;
        """, (card_id, deck_id))
        row = cursor.fetchone()

    if not row:
        return jsonify({"error": "Card not found"}), 404

    card = Card(
        id=row[0],
        front=row[1],
        back=row[2],
        interval=float(row[3]),
        ease=float(row[4]),
        next_due=float(row[5]),
    )

    correct = (user_answer == card.back.lower())
    update_card(card, correct)
    save_card(card)

    return jsonify({
        "correct": correct,
        "correct_answer": card.back
    })

if __name__ == "__main__":
    init_db()
    app.run(debug=True)