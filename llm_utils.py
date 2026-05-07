import openai
import re
import json
from typing import List, Optional, Tuple
from prompts.legacy_prompts import (
    situation_analysis, INTENTION_DETECTION_WHEN_NO_IMAGE,
    reply_drafting_or_advice, self_reflection_or_general,
    OCR_prompt, INTENTION_DETECTION_FROM_IMAGE_CAPTION,
    greeting_or_smalltalk, Synopsis, LLM_ONBOARD_PROMPT
)
from langchain.vectorstores import Chroma
from langchain.embeddings import OpenAIEmbeddings
from db_utils import get_previous_convo
from sqlalchemy.ext.asyncio import AsyncSession


CHROMA_DIR = "./chroma_db"

def get_gpt_vision_response(user_text: str, image_b64: str, mime_type: str, temperature: float = 0.0) -> str:
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": OCR_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_b64}",
                                "detail": "high"
                            },
                        },
                    ],
                },
            ],
            max_tokens=500,
            temperature=temperature,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("OpenAI Vision API Error:", e)
        return "Sorry, I couldn't process your image right now."


def get_intention_from_user_caption(user_input: str) -> str:
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",  # or "gpt-3.5-turbo"
            messages=[
                {"role": "system", "content": INTENTION_DETECTION_FROM_IMAGE_CAPTION},
                {"role": "user", "content": user_input}
            ]
        )
        print(response.choices[0].message.content.strip())
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("OpenAI API Error:", e)
        return "Sorry, I couldn't generate a response right now."


def get_intention_from_user_text(user_input: str) -> str:
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",  # or "gpt-3.5-turbo"
            messages=[
                {"role": "system", "content": INTENTION_DETECTION_WHEN_NO_IMAGE},
                {"role": "user", "content": user_input}
            ]
        )
        print(len(response.choices[0].message.content.strip()))
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("OpenAI API Error:", e)
        return "Sorry, I couldn't generate a response right now."
    

# <<< REVISED >>>
async def get_gpt_response(
    user_input: str,
    ocr: str = "",
    intention: str = "",
    session: AsyncSession = None,
    prev_context_id: str = None
) -> str:
    try:
        # 1) Choose the correct system prompt
        if intention == "situation_analysis":
            context_prompt = situation_analysis
        elif intention == "reply_drafting_or_advice":
            context_prompt = reply_drafting_or_advice
        elif intention == "self_reflection_or_general":
            context_prompt = self_reflection_or_general
        elif intention == "greeting_or_smalltalk":
            context_prompt = greeting_or_smalltalk
        else:
            context_prompt = reply_drafting_or_advice

        # 2) Prepare the “user_message” (include OCR if present)
        user_message = user_input
        if ocr:
            user_message += f"\n\n(ocr content: {ocr})"

        # 3) Run your RAG lookup (synchronous)
        rag_context = get_top_k_context(user_message, k=2)
        # (That returns a plain string, no await needed here.)

        # 4) Fetch previous conversation from the DB
        previous_text = ""
        if prev_context_id and session:
            previous_text = await get_previous_convo(prev_context_id, session)
        # If prev_context_id is None or session is None, `previous_text` stays empty.

        # 5) Build full prompt
        full_prompt = (
            f"Reference Examples:\n{rag_context}\n\n"
            f"{previous_text}\n\n"
            f"User:\n{user_message}"
        )

        # 6) Call OpenAI
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": context_prompt},
                {"role": "user", "content": full_prompt},
            ],
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        print("OpenAI API Error:", e)
        return "Sorry, I couldn't generate a response right now"
    

def chunk_by_word_boundary(text: str, max_length: int) -> List[str]:
    tokens = re.findall(r'\S+|\s+', text)  # Split into words and whitespace (including newlines)
    chunks = []
    current_chunk = ''

    for token in tokens:
        if len(current_chunk) + len(token) <= max_length:
            current_chunk += token
        else:
            if current_chunk:
                chunks.append(current_chunk)
            # If token itself is longer than max_length, still include it in a new chunk
            if len(token) > max_length:
                # break the token by hard slicing as last resort (rare)
                for i in range(0, len(token), max_length):
                    chunks.append(token[i:i + max_length])
                current_chunk = ''
            else:
                current_chunk = token

    if current_chunk:
        chunks.append(current_chunk)

    return [chunk.strip() for chunk in chunks if chunk.strip()]


async def split_replies(message: str) -> List[str]:
    """
    Splits a message into parts based on numbering (e.g., 1., 2., 3.)
    and returns a list of formatted replies.
    """
    # Split on patterns like "1.", "2." at the beginning of a line
    parts = re.split(r'\n(?=\d+\.\s)', message.strip())
    replies = []

    for part in parts:
        if re.match(r'^\d+\.\s', part):  # Ensure it starts with a number
            replies.append(part.strip())

    return replies



async def split_suggested_messages(message: str) -> List[str]:
    """
    Extracts suggested messages wrapped in <START>...</END> inside <SEP> blocks.
    """
    suggestions = []

    # Find the block between <SEP> ... <SEP>
    sep_blocks = re.findall(r"<SEP>(.*?)<SEP>", message, re.DOTALL | re.IGNORECASE)
    
    for block in sep_blocks:
        # Find all <START> ... <END> suggestions
        matches = re.findall(r"<START>(.*?)<END>", block, re.DOTALL)
        suggestions.extend([msg.strip() for msg in matches if msg.strip()])

    return suggestions


async def remove_suggested_messages_block(message: str) -> str:
    """
    Removes all <SEP>...<SEP> suggested message blocks from the message.
    """
    cleaned_message = re.sub(r"<SEP>.*?<SEP>", "", message, flags=re.DOTALL | re.IGNORECASE)
    return cleaned_message.strip()

def separate_ocr_name(response: str) -> Tuple[str, Optional[List[str]]]:
    """
    Extract names from the PERSON_NAME field formatted as:
    PERSON_NAME:[Victoria, John Gray]
    """
    # Match square bracket format
    name_match = re.search(r"PERSON_NAME:\s*\[([^\]]+)\]", response, re.IGNORECASE)
    raw_names = name_match.group(1).strip() if name_match else None
    names = [n.strip() for n in raw_names.split(",")] if raw_names else []

    return response, names[0] if names else None


def separate_name_intention(response: str):
    # Extract intention (e.g., (intention: reply_drafting_or_advice))
    intention_match = re.search(r"\(intention:\s*([a-z_]+)\)", response, re.IGNORECASE)
    intention = intention_match.group(1).strip() if intention_match else None
    print(intention)
    # Extract names (e.g., (name: Aakash, Tritya))
    name_match = re.search(r"\(name:\s*([^)]+)\)", response, re.IGNORECASE)
    raw_names = name_match.group(1).strip() if name_match else None
    names = [n.strip() for n in raw_names.split(",")] if raw_names else []
    name = names[0] if len(names) == 1 else names or None

    return name, intention


def get_top_k_context(query, k=5, rag= False):
    if rag:
        embedding = OpenAIEmbeddings(model="text-embedding-3-large")
        vectorstore = Chroma(
            persist_directory=CHROMA_DIR,
            embedding_function=embedding,
            collection_name="rag_books"
        )
        retriever = vectorstore.as_retriever(search_kwargs={"k": k})
        results = retriever.get_relevant_documents(query)

        # Format each chunk with optional metadata and separators
        formatted_chunks = []
        for i, doc in enumerate(results):
            source = doc.metadata.get("source", f"Chunk {i+1}")
            chunk_text = f"Source: {source}\n{doc.page_content.strip()}"
            formatted_chunks.append(chunk_text)

        return "\n\n--------------------\n\n".join(formatted_chunks)
    else:
        return " "



async def generate_user_synopsis(profile_data: dict) -> str:
    prompt = f"""
        You are an expert human matchmaker and narrative designer.
        Some fields like Date of Birth, Gender, or Sexual Orientation may be missing. In such cases, do your best to infer them from the Transcript context

        Name: {profile_data['name']}  
        Phone: {profile_data['phone']}  
        Date of Birth: {profile_data['dob']} (MM/DD/YYYY)
        Gender: {profile_data['gender']}  
        Sexual Orientation: {profile_data['orientation']}  

        Transcript:
        {profile_data['transcript']}
        """

    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": Synopsis },
            {"role": "user", "content": prompt}
        ],
        temperature=0.7
    )

    return response.choices[0].message.content.strip()




async def evaluate_onboarding_llm(bot_question: str, user_reply: str) -> dict:
    prompt = f"""
        BOT: {bot_question}
        USER: {user_reply}

        Respond with a JSON like this:
        {{
        "get_necessary_ans": true or false,
        "parsed_answer": "...",
        "response_message": "..."
        }}
        """
    chat_response = openai.chat.completions.create(
        model="gpt-4o",
        temperature=0.3,
        messages=[
            {"role": "system", "content": LLM_ONBOARD_PROMPT},
            {"role": "user", "content": prompt}
        ]
    )

    try:
        content = chat_response.choices[0].message.content
        parsed = json.loads(content)
        return parsed
    except Exception as e:
        print("❌ LLM response parsing failed:", e)
        return {
            "get_necessary_ans": False,
            "parsed_answer": None,
            "response_message": "Sorry, something went wrong. Could you rephrase that?"
        }