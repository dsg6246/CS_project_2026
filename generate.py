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
import random
from dataclasses import dataclass, field
from time import time
load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")  # or whatever name you used in .env
if not API_KEY:
    raise ValueError("API key not found in .env")

URL = (
    "https://generativelanguage.googleapis.com"
    "/v1beta/models/gemini-2.5-flash:generateContent"
    f"?key={API_KEY}"
)

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
                interval INT NOT NULL,
                ease INT NOT NULL,
                next_due INT NOT NULL,
                FOREIGN KEY(deck_id) REFERENCES decks(id)
            );
        """)

        conn.commit()

def clear_table():
    conn = sqlite3.connect(DB_FILE)
    try:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM cards")
        conn.commit()
    finally:
        conn.close()
        
def run(sql):
   
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        for row in rows:
            print(row)
        print(f"({len(rows)} rows)\n")
        
@dataclass
class Card:
    id: int
    front: str
    back: str
    interval: float=1.0
    ease: float=2.5
    next_due: float = field(default_factory=lambda: time())
    
def pick_card(cards):
    due = [c for c in cards if c.next_due<=time()]
    if due:
        return random.choice(due)
    weights = [1/c.interval for c in cards]
    return random.choices(cards, weights=weights, k=1)[0]

def update_card(card, correct):
    now = time()
    if correct:
        card.interval=min(card.interval*card.ease, 365)
        card.ease=min(card.ease+0.05, 3.0)
    else:
        card.interval=1.0
        card.ease=max(card.ease-0.2, 1.3)
    card.next_due=now+card.interval*86400
    return None
def load_deck(chosen):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, english, spanish, interval, ease, next_due
            FROM cards
            WHERE deck_id = ?;
        """, (chosen,))
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
def display_choose():
   
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT deck_id FROM cards;
        """)
        deck_names = [row[0] for row in cursor.fetchall()]
        if not deck_names:
            print("No decks found")
            return None
        print("Deck names:")
        for i in deck_names:
            print("   ",i)
        chosen=input("Choose your deck: ")
        if chosen not in deck_names:
            print("The deck you chose does not exist")
            return None
        
        cards=load_deck(chosen)
        if not cards:
            print("The deck has no cards")
            return None
        return cards
       


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


# def choose_deck()

def save_flashcards(flashcards,deck_id):
    if not flashcards:
        print("No flashcards to save.")
        return

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()

        # Create a new deck
        cursor.execute("INSERT INTO decks DEFAULT VALUES;")
       

        # Insert cards
        for card in flashcards:
            english = card.get("english")
            spanish = card.get("spanish")
            if english and spanish:
                cursor.execute(
                    "INSERT INTO cards (deck_id,english,spanish,interval,ease,next_due) VALUES (?,?,?,?,?,?);",
                    (deck_id, english, spanish, 1.0, 2.5, time())
                )

        conn.commit()
        print(f"Saved {len(flashcards)} flashcards into deck {deck_id}.")



def save_card(card: Card):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE cards
            SET interval = ?, ease = ?, next_due = ?
            WHERE id = ?;
        """, (card.interval, card.ease, card.next_due, card.id))
        conn.commit()


# ============================================================
# MAIN: Menu loop
# ============================================================

    
def main():
    """Main menu loop for the app."""
    init_db()  # make sure tables exist
    cards=[]
    with open("words.in", "r") as f:
        words = f.readlines()
        words = " ".join(words)

    print("1. Choose an existing card deck")
    print("2. Make a new card deck")
    print("3. Clear decks")
    option=input("Choose an option #: ")
    if option=="1":
        cards = display_choose()
        print("Write quit to end your session")
        while True:
            card = pick_card(cards)
            print(card.front)
            user_answer = input("> ").strip().lower()

            if user_answer == card.back.lower():
                print("Correct!")
                correct = True
            elif user_answer=="quit":
                print("Thank you for using our website")
                break
            else:
                print(f"Wrong. The correct answer is: {card.back}")
                correct = False
 
            update_card(card, correct)
            save_card(card)
        
        
        
        
        
        
    elif option=="2":
        flashcards = generate_guide(words)
        print(flashcards)
        print("What would you like to name the deck? ")
        deck_id=input("Name: ")
        if flashcards is not None:
            save_flashcards(flashcards,deck_id)
        else:
            print("Failed to generate flashcards.")
    elif option=="3":
        clear_table()


main()


# cards = [
#     Card("hola", "hello"),
#     Card("adiós", "goodbye"),
#     # ...
# ]

# while True:
#     card = pick_card(cards)
#     print(card.front)
#     user_answer = input("> ")
#     correct = (user_answer.strip().lower() == card.back.lower())
#     update_card(card, correct)
