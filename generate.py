import requests
import json
import math
import csv
import ast
import os
import sys
from dotenv import load_dotenv
import sqlite3
from datetime import date
load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")  # or whatever name you used in .env
if not API_KEY:
    raise ValueError("API key not found in .env")

URL = (
    "https://generativelanguage.googleapis.com"
    "/v1beta/models/gemini-2.5-flash:generateContent"
    f"?key={API_KEY}"
)

# ============================================================
# FUNCTION 2: Send data to Gemini and get structured JSON back
# ============================================================
DB_FILE="cards.db"

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS decks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deck_id INTEGER NOT NULL,
                english TEXT NOT NULL,
                spanish TEXT NOT NULL,
                FOREIGN KEY(deck_id) REFERENCES decks(id)
            );
        """)

        conn.commit()


def run(sql):
   
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        for row in rows:
            print(row)
        print(f"({len(rows)} rows)\n")


def generate_guide(material: str):
    # Build the prompt as a left-aligned triple-quoted string
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

    try:
        response = requests.post(URL, json=body, timeout=30)

        if response.status_code != 200:
            print(f"API error: {response.status_code} {response.text}")
            return None

        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

        # In theory response_mime_type should already prevent code fences,
        # but this keeps you safe if they appear.
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]

        return json.loads(text)

    except Exception as e:
        print("Error generating guide:", e)
        return None


def save_flashcards(flashcards):
    if not flashcards:
        print("No flashcards to save.")
        return

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()

        # Create a new deck
        cursor.execute("INSERT INTO decks DEFAULT VALUES;")
        deck_id = cursor.lastrowid

        # Insert cards
        for card in flashcards:
            english = card.get("english")
            spanish = card.get("spanish")
            if english and spanish:
                cursor.execute(
                    "INSERT INTO cards (deck_id, english, spanish) VALUES (?, ?, ?);",
                    (deck_id, english, spanish)
                )

        conn.commit()
        print(f"Saved {len(flashcards)} flashcards into deck {deck_id}.")

# ============================================================
# FUNCTION 3: Display one result to the user
# ============================================================




# ============================================================
# MAIN: Menu loop
# ============================================================

def main():
    """Main menu loop for the app."""
    init_db()  # make sure tables exist

    with open("words.in", "r") as f:
        words = f.readlines()
        words = " ".join(words)

    flashcards = generate_guide(words)

    if flashcards is not None:
        save_flashcards(flashcards)
    else:
        print("Failed to generate flashcards.")


main()