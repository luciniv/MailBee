from dotenv import load_dotenv
import os

# Holding place for emojis
mantis = os.getenv("EMOJI")
emoji_map = {
    "new": "🆕",
    "alert": "❗️",
    "wait": "⏳"
}