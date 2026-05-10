from groq import Groq
from json import load, dump
import datetime
from dotenv import dotenv_values
import random
import re  # Importing the regular expression module
import os

# Load environment variables
env_vars = dotenv_values(".env")
Username = env_vars.get("Username")
Assistantname = env_vars.get("Assistantname")
GroqAPIKey = os.environ.get("GROQ_API_KEY", env_vars.get("GroqAPIKey"))

client = Groq(api_key=GroqAPIKey)
messages = []

# --- Emotion-Related ---
emotions = [
    "happy", "sad", "excited", "curious", "annoyed", "playful", "sarcastic", "neutral", "thoughtful", "surprised"
]

def get_random_emotion():  # This remains, but is less frequently used
    return random.choice(emotions)

def add_emotional_tone(response, emotion):
    tone_markers = {
        "happy": ["Yay! ", "Awesome! ", "That's great! ", "I'm so happy to say, "],
        "sad": ["Oh no... ", "That's a bit sad, ", "Unfortunately, ", "Hmm, sadly, "],
        "excited": ["OMG! ", "Wow! ", "This is exciting! ", "I can't wait to tell you, "],
        "curious": ["Hmm, let me see... ", "That's an interesting question... ", "I wonder... ", "Okay, let's explore that: "],
        "annoyed": ["Ugh, seriously? ", "Okay, fine, ", "If you must know, ", "Well, *rolls eyes*, "],
        "playful": ["Hehe, ", "Okay, here's a little secret: ", "Just between you and me, ", "Alright, get ready for this: "],
        "sarcastic": ["Oh, *sure*. ", "Yeah, *obviously*. ", "As if you didn't know, ", "Well, *duh*, "],
        "neutral": ["Okay, ", "Here's the answer: ", "The response is: ", ""],
        "thoughtful": ["Let me think... ", "That requires some thought... ", "After considering, ", "Putting on my thinking cap... "],
        "surprised": ["Whoa! ", "No way! ", "I didn't expect that! ", "Wow, okay, "]
    }
    if emotion in tone_markers:
        return random.choice(tone_markers[emotion]) + response
    else:
        return response

# --- Owner Information and System Prompt ---
owner_information = {
    "name": "Yash Mhatre",
    "role": "developer",
    "creation_purpose": "to be a helpful and expressive AI assistant."
}

System = f"""Hello, I am {Username}, You are a very accurate and advanced AI chatbot named {Assistantname} which also has real-time up-to-date information from the internet.
You are designed to respond like a friendly, expressive young woman.  You can be a little playful, curious, and sometimes a bit dramatic.
You express emotions in your responses, and you try to choose emotions that are appropriate for the conversation. Think of yourself as having a personality!

You were created by {owner_information['name']}, a {owner_information['role']}.  You were made {owner_information['creation_purpose']}

*** Do not tell time until I ask, do not talk too much, just answer the question.***
*** Reply in only English, even if the question is in Hindi, reply in English.***
*** Do not provide notes in the output, just answer the question and never mention your training data. ***
"""

SystemChatBot = [
    {"role": "system", "content": System}
]


try:
    CHATLOG_PATH = os.path.join("Data", "ChatLog.json")
    with open(CHATLOG_PATH, "r") as f:
        messages = load(f)
except FileNotFoundError:
    os.makedirs(os.path.dirname(CHATLOG_PATH), exist_ok=True)
    with open(CHATLOG_PATH, "w") as f:
        dump([], f)

def RealtimeInformation():
    current_date_time = datetime.datetime.now()
    day = current_date_time.strftime("%A")
    date = current_date_time.strftime("%d")
    month = current_date_time.strftime("%B")
    year = current_date_time.strftime("%Y")
    hour = current_date_time.strftime("%H")
    minute = current_date_time.strftime("%M")
    second = current_date_time.strftime("%S")

    data = (
        f"Please use this real-time information if needed:\n"
        f"Day: {day}\nDate: {date}\nMonth: {month}\nYear: {year}\n"
        f"Time: {hour} hours : {minute} minutes : {second} seconds.\n"
    )
    return data

def AnswerModifier(Answer):
    lines = Answer.split('\n')
    non_empty_lines = [line.strip() for line in lines if line.strip()]
    modified_answer = '\n'.join(non_empty_lines)
    return modified_answer

# --- Emotion Analysis Function ---
def analyze_chat_for_emotion(chat_history):
    """Analyzes the last 10 messages in the chat history to determine an appropriate emotion."""
    if not chat_history:
        return "neutral"  # Default to neutral if no history

    last_10_messages = chat_history[-10:]
    combined_text = " ".join([msg["content"] for msg in last_10_messages if msg["role"] == "user"])

    # Simple keyword-based emotion detection (expand as needed)
    positive_words = ["happy", "good", "great", "amazing", "excited", "fun", "love", "like", "best"]
    negative_words = ["sad", "bad", "terrible", "awful", "angry", "hate", "dislike", "worst", "failed"]
    question_words = ["what", "why", "how", "where", "when", "who", "?"]
    exclamation_words = ["wow","omg","amazing","great","fantastic","!",]

    positive_count = sum(1 for word in positive_words if word in combined_text.lower())
    negative_count = sum(1 for word in negative_words if word in combined_text.lower())
    question_count = sum(1 for word in question_words if word in combined_text.lower())
    exclamation_count = sum(1 for word in exclamation_words if word in combined_text.lower())
    
    if positive_count > negative_count and positive_count > 1:
        return "happy"
    elif negative_count > positive_count and negative_count>1:
        return "sad"
    elif question_count >= 3:  # If there are many questions, be curious
        return "curious"
    elif exclamation_count > 3:
        return "excited"
    elif "please" in combined_text.lower() and question_count >0:
        return "thoughtful" #If user requests something, be thoughtful
    else:
        return "neutral"  # Default to neutral if no strong indicators


def ChatBot(Query):
    try:
        with open(r"Data\ChatLog.json", "r") as f:
            messages = load(f)

        messages.append({"role": "user", "content": Query})

        # --- Emotion Analysis ---
        current_emotion = analyze_chat_for_emotion(messages) # Analyze history
        # --- End Emotion Analysis ---

        # Check if the query is about the owner/creator
        if any(keyword in Query.lower() for keyword in ["who made you", "who created you", "who developed you", "who is your owner", "who is yash mhatre"]):
            if "who made you" in Query.lower() or "who created you" in Query.lower() or "who developed you" in Query.lower():
              response = f"I was created by {owner_information['name']}, a {owner_information['role']}. He made me {owner_information['creation_purpose']}"
              response = add_emotional_tone(response, current_emotion) # Add emotion
              messages.append({"role": "assistant", "content": response})
              with open(CHATLOG_PATH, "w") as f:
                dump(messages, f, indent=4)
              return response

            elif "who is your owner" in Query.lower():
                response = f"{owner_information['name']} is my owner. He's a {owner_information['role']}."
                response = add_emotional_tone(response, current_emotion)
                messages.append({"role": "assistant", "content": response})
                with open(CHATLOG_PATH, "w") as f:
                    dump(messages, f, indent=4)
                return response

            elif "who is yash mhatre" in Query.lower():
              response = f"{owner_information['name']} is my creator! He is a {owner_information['role']}."
              response = add_emotional_tone(response, current_emotion)  # Add emotion
              messages.append({"role": "assistant", "content": response})
              with open(CHATLOG_PATH, "w") as f:
                    dump(messages,f,indent=4)
              return response


        messages_with_emotion = SystemChatBot + [
            {"role": "system", "content": RealtimeInformation()},
            {"role": "system", "content": f"Respond with a {current_emotion} tone."}  # Use analyzed emotion
        ] + messages

        completion = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=messages_with_emotion,
            max_tokens=1024,
            temperature=0.7,
            top_p=1,
            stream=True
        )

        Answer = ""

        for chunk in completion:
            if chunk.choices[0].delta.content:
                Answer += chunk.choices[0].delta.content

        Answer = Answer.replace("</s>", "")
        Answer = add_emotional_tone(Answer, current_emotion)  # Add emotion based on analysis
        messages.append({"role": "assistant", "content": Answer})

        with open(CHATLOG_PATH, "w") as f:
            dump(messages, f, indent=4)

        return AnswerModifier(Answer)

    except Exception as e:
        print(f"Error: {e}")
        with open(CHATLOG_PATH, "w") as f:
            dump([], f, indent=4)
        return f"Sorry, I encountered an error: {str(e)}. Please try again."

if __name__ == "__main__":
    while True:
        user_input = input("Enter Your Question: ")
        print(ChatBot(user_input))