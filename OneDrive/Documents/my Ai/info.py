from googlesearch import search
from groq import Groq
from json import load, dump
import datetime
from dotenv import dotenv_values
import os

# Load environment variables
env_vars = dotenv_values(".env")
username = env_vars.get("Username")
assistantname = env_vars.get("Assistantname")
groq_api_key = env_vars.get("GroqAPIKey")

# Initialize Groq client
client = Groq(api_key=groq_api_key)

system_instructions = f"""Hello, I am {username}, You are a very accurate and advanced AI chatbot named {assistantname} which has real-time up-to-date information from the internet.
*** Provide Answers In a Professional Way, make sure to add full stops, commas, question marks, and use proper grammar.***
*** Summarize information concisely and clearly, synthesizing the most relevant information. ***
*** If presenting search results, format them clearly and indicate their source. ***
"""

# Chat log handling
try:
    with open(r"Data\ChatLog.json", "r") as f:
        messages = load(f)
except FileNotFoundError:
    with open(r"Data\ChatLog.json", "w") as f:
        dump([], f)
    messages = []

def google_search(query, num_results=5):
    """
    Performs a Google search and returns a formatted string of results.

    Args:
        query: The search query string.
        num_results: The number of results to retrieve.

    Returns:
        A formatted string containing the search results.
    """
    try:
        results = list(search(query, advanced=True, num_results=num_results, lang="en"))  # Added language for consistency
        answer = f"Search results for '{query}':\n\n"
        for i, result in enumerate(results):
            answer += f"Result {i+1}:\n"
            answer += f"  Title: {result.title}\n"
            answer += f"  Link: {result.url}\n"  # Use .url instead of .link
            answer += f"  Description: {result.description}\n\n"
        return answer

    except Exception as e:
        return f"An error occurred during the search: {e}"

def answer_modifier(answer):
    """Removes empty lines from the answer."""
    lines = answer.split('\n')
    non_empty_lines = [line for line in lines if line.strip()]
    return '\n'.join(non_empty_lines)


def get_information():
    """Gets current date and time information."""
    current_date_time = datetime.datetime.now()
    day = current_date_time.strftime("%A")
    date = current_date_time.strftime("%d")
    month = current_date_time.strftime("%B")
    year = current_date_time.strftime("%Y")
    hour = current_date_time.strftime("%H")
    minute = current_date_time.strftime("%M")
    second = current_date_time.strftime("%S")
    data = f"Current Date and Time:\n"
    data += f"  Day: {day}\n"
    data += f"  Date: {date}\n"
    data += f"  Month: {month}\n"
    data += f"  Year: {year}\n"
    data += f"  Time: {hour}:{minute}:{second}\n"
    return data


def realtime_search_engine(prompt):
    """
    Handles real-time search and response generation.

    Args:
      prompt: The user's input prompt.

    Returns:
      The generated response.
    """
    global messages

    # Load chat log
    with open(r"Data\ChatLog.json", "r") as f:
        messages = load(f)

    messages.append({"role": "user", "content": prompt})

    # Perform Google Search and format results
    search_results = google_search(prompt)

    # Combine system instructions, search results, current time, and chat history
    combined_messages = [
        {"role": "system", "content": system_instructions},
        {"role": "system", "content": search_results}, # Include search results directly
        {"role": "system", "content": get_information()},
        *messages  # Unpack the existing messages
    ]
    
    # Groq API call
    try:
        completion = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=combined_messages,
            temperature=0.7,
            max_tokens=2048,
            top_p=1,
            stream=True,
            stop=None
        )

        answer = ""
        for chunk in completion:
            if chunk.choices[0].delta.content:
                answer += chunk.choices[0].delta.content

        answer = answer.strip().replace("</s>", "")
        messages.append({"role": "assistant", "content": answer})

    except Exception as e:
        answer = f"An error occurred while processing the request: {e}"
        messages.append({"role": "assistant", "content": answer})

    # Save updated chat log
    with open(r"Data\ChatLog.json", "w") as f:
        dump(messages, f, indent=4)
    
    return answer_modifier(answer)



if __name__ == "__main__":
    # Initial conversation setup
    if not messages:  # Only add initial messages if the chat log is empty.
        messages.extend([
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello, how can I help you?"}
        ])
        with open(r"Data\ChatLog.json", "w") as f:  # Save it
            dump(messages, f, indent=4)


    while True:
        prompt = input("Enter your query: ")
        if prompt.lower() in ("exit", "quit", "bye"):  #Added exit conditions
            print("Goodbye!")
            break
        print(realtime_search_engine(prompt))