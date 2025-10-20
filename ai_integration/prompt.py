from openai import AsyncOpenAI
from pathlib import Path
import os
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

API_KEY = os.getenv("OPENAI_API_KEY")

client = AsyncOpenAI(api_key=API_KEY)


def build_server_context(context: dict) -> str:
    """
    Build a string representation of the server context from a dictionary.
    """
    return "\n".join(
        [
            f"**Name:** {context['name']}",
            f"**Description:** {context['description']}",
            f"**Tone:** {context['tone']}",
            f"**Reply Guidelines:** {context['guidelines']}",
        ]
    )


async def generate_ticket_reply(
    transcript: str, server_context: str = "", ticket_context: str = ""
):
    messages = [
        {
            "role": "system",
            "content": """
            You are a helpful, polite Discord ticket support assistant.
            You may use minimal markdown formatting (bold, italics) in your reply.
            Do not make up information or assume anything. Refer only to given context.
            Only respond with the reply text, no explanations. Your replies will be sent
            directly to the ticket opener (the USER).
            """,
        },
        {"role": "system", "content": f"Server context:\n{server_context}"},
        {"role": "system", "content": f"Ticket context:\n{ticket_context}"},
        {
            "role": "user",
            "content": f"""
            Given the following transcript, write a clear, professional reply
            to the most recent USER message, adhering to the above context.
            COMMENT messages are internal notes and should not be referenced in
            your reply. Your message must be less than 3000 characters.

            --- Transcript ---
            {transcript}
            """,
        },
    ]

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.6,
            max_tokens=400,
        )

        return response.choices[0].message.content.strip()
    except Exception as e:
        return None
