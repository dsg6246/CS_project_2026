


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
        You are converting study material into flashcards.

        Task:
        Create a JSON array of flashcards from the input data.

        Rules:
        - Return only valid JSON.
        - Do not include markdown, explanations, or extra text.
        - Each flashcard must be an object with:
        - "english": the English word, phrase, or question
        - "spanish": the Spanish translation or answer
        - If the input is a study guide, extract important terms and convert them into flashcards.
        - If the input is a list of words, translate each word into Spanish.
        - Keep the output concise and accurate.

        Output format example:
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

     
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]
        return json.loads(text)

    except Exception as e:
        print("Error generating guide:", e)
        return None


# ============================================================
# FUNCTION 3: Display one result to the user
# ============================================================




# ============================================================
# MAIN: Menu loop
# ============================================================

def main():
    """Main menu loop for the app."""
    # Print app title

   
    #   1. Process new item (get input → send to Gemini → display → add to collected)
    #   2. View all collected results
    #   3. Save & Quit
    with open ("words.in","r") as f:
        words=f.readlines()
        words=" ".join(words)
        
    flashcards=generate_guide(words)
        
    

    pass


main()