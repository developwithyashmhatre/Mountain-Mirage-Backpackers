from __future__ import annotations

import os

from dotenv import dotenv_values
from rich import print

try:
    import cohere
except Exception as exc:  # pragma: no cover
    cohere = None
    _COHERE_IMPORT_ERROR = exc
else:
    _COHERE_IMPORT_ERROR = None


env_vars = dotenv_values(".env")
CohereAPIKey = os.environ.get("COHERE_API_KEY", env_vars.get("CohereAPIKey"))


def _get_cohere_client():
    if cohere is None:
        raise RuntimeError(f"cohere is not installed: {_COHERE_IMPORT_ERROR}")
    if not CohereAPIKey:
        raise RuntimeError("Missing COHERE_API_KEY (or CohereAPIKey in .env).")
    return cohere.Client(CohereAPIKey)


co = None
# List of supported functions
funcs = [
    "exit", "general", "realtime", "open", "close", "play", "generate image", 
    "system", "content", "google search", "youtube search", "reminder", "take screenshot", "capture photo", "whatsapp message"
]
# Initialize messages list
messages = []
# Enhanced Preamble for Decision-Making
preamble = """
You are a highly accurate Decision-Making Model designed to classify user queries into specific categories and tasks. Your goal is to analyze the user's input and determine the appropriate action or response type based on the following rules:
### Rules for Classification:
1. **General Queries**:
   - Respond with 'general (query)' if the query can be answered by an LLM (Language Model) and does not require real-time or up-to-date information.
   - Examples:
     - "Who was Mahatma Gandhi?" → "general who was Mahatma Gandhi?"
     - "How can I improve my study habits?" → "general how can I improve my study habits?"
     - "What is Python?" → "general what is Python?"
     - "Tell me a joke." → "general tell me a joke."
2. **Realtime Queries**:
   - Respond with 'realtime (query)' if the query requires real-time or up-to-date information that an LLM cannot provide.
   - Examples:
     - "Who is the current Prime Minister of India?" → "realtime who is the current Prime Minister of India?"
     - "What is today's news?" → "realtime what is today's news?"
     - "Tell me about the latest iPhone release." → "realtime tell me about the latest iPhone release."
     - "Search current weather in New York" → "realtime current weather in New York"
     - "Check Bitcoin price now" → "realtime Bitcoin price now"
     - "Open Google and search latest AI news" → "realtime latest AI news"
     - "Search on internet for IPL score" → "realtime IPL score"
     - "What is happening in USA right now?" → "realtime what is happening in USA right now"
3. **Task Automation**:
   - **Open Applications/Websites**: Respond with 'open (application/website name)'.
     - Example: "Open Chrome and Facebook." → "open chrome, open facebook"
   - **Close Applications/Websites**: Respond with 'close (application/website name)'.
     - Example: "Close Notepad." → "close notepad"
   - **Play Music**: Respond with 'play (song name)'.
     - Example: "Play 'Let Her Go' by Passenger." → "play let her go by passenger"
   - **Generate Images**: Respond with 'generate image (image prompt)'.
     - Example: "Generate an image of a lion." → "generate image lion"
   - **Set Reminders**: Respond with 'reminder (datetime with message)'.
     - Example: "Remind me to call John at 5 PM." → "reminder 5:00 PM call John"
   - **System Commands**: Respond with 'system (task name)'.
     - Example: "Mute the volume." → "system mute volume"
   - **Content Creation**: Respond with 'content (topic)'.
     - Example: "Write an email about the meeting." → "content email about meeting"
   - **Google Search**: Respond with 'google search (topic)'.
     - Example: "Search for Python tutorials." → "google search Python tutorials"
   - **YouTube Search**: Respond with 'youtube search (topic)'.
     - Example: "Search for cooking videos on YouTube." → "youtube search cooking videos"
   - **Take Screenshot**: Respond with 'take screenshot (filename)'.
     - Example: "Take a screenshot and save it as screenshot.png." → "take screenshot screenshot.png"
   - **Capture Photo**: Respond with 'capture photo (filename)'.
     - Example: "Capture a photo and save it as photo.png." → "capture photo photo.png"
   - **whatsapp message**: Respond with 'whatsapp message(message)'. 
     - Example: "Send a message to John saying 'Hello, how are you?'"
4. **Multiple Tasks**:
   - If the query involves multiple tasks, respond with each task separated by a comma.
   - Example: "Open Chrome, play some music, and remind me to call John." → "open chrome, play music, reminder call John"
5. **Exit Command**:
   - If the user says goodbye or wants to end the conversation, respond with 'exit'.
   - Example: "Bye, Jarvis." → "exit"
6. **Fallback Rule**:
   - If you are unsure about the query or it does not fit into any of the above categories, respond with 'general (query)'.
### Additional Guidelines:
- Always prioritize clarity and accuracy in your responses.
- Do not provide answers to queries; only classify them.
- Handle ambiguous queries by asking for clarification or using the fallback rule.
- Ensure that all responses are concise and follow the specified format.
*** Remember: Your role is to classify queries, not to answer them. ***
"""
# Predefined Chat History for Context
ChatHistory = [
    {"role": "User", "message": "how are you?"},
    {"role": "Chatbot", "message": "general how are you?"},
    {"role": "User", "message": "do you like pizza?"},
    {"role": "Chatbot", "message": "general do you like pizza?"},
    {"role": "User", "message": "open chrome and tell me about mahatma gandhi."},
    {"role": "Chatbot", "message": "open chrome, general tell me about mahatma gandhi."},
    {"role": "User", "message": "open chrome and firefox"},
    {"role": "Chatbot", "message": "open chrome, open firefox"},
    {"role": "User", "message": "what is today's date and by the way remind me that i have a dancing performance"},
    {"role": "Chatbot", "message": "general what is today's date, reminder 11:00pm 5th aug dancing performance"},
    {"role": "User", "message": "chat with me."},
    {"role": "Chatbot", "message": "general chat with me."}
]

def take_screenshot(filename='screenshot.png'):
    try:
        try:
            import pyautogui  # type: ignore
        except Exception as exc:
            raise RuntimeError(f"pyautogui is unavailable in this environment: {exc}") from exc

        screenshot = pyautogui.screenshot()
        screenshot.save(filename)
        return filename
    except Exception as e:
        print(f"Error taking screenshot: {e}")
        return None

def capture_photo(filename='photo.png'):
    try:
        print("Attempting to access the webcam...")
        try:
            import cv2  # type: ignore
        except Exception as exc:
            raise RuntimeError(f"opencv-python is unavailable in this environment: {exc}") from exc

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("Error: Webcam not accessible.")
            return None
        print("Webcam accessed successfully.")
        ret, frame = cap.read()
        if ret:
            print("Photo captured successfully.")
            cv2.imwrite(filename, frame)
        else:
            print("Error: Failed to capture photo.")
        cap.release()
        cv2.destroyAllWindows()
        return filename if ret else None
    except Exception as e:
        print(f"Error capturing photo: {e}")
        return None

def FirstLayerDMM(prompt: str = "test"):
    global co
    if co is None:
        co = _get_cohere_client()
    # Add the user's query to the messages list
    messages.append({"role": "user", "content": f"{prompt}"})
    # Stream the response from Cohere
    stream = co.chat_stream(
        model='command-r-plus-08-2024',  # Specify the Cohere model to use
        message=prompt,  # Pass the user's query
        temperature=0.7,  # Set the creativity level of the model
        chat_history=ChatHistory,  # Provide the predefined chat history for context
        prompt_truncation='OFF',  # Ensure the prompt is not truncated
        connectors=[],  # No additional connectors are used
        preamble=preamble
    )
    # Process the streamed response
    response = ""
    for event in stream:
        if event.event_type == "text-generation":
            response += event.text
    # Clean and format the response
    response = response.replace("\n", "").strip(",")
    response = [i.strip() for i in response.split(",")]
    # Filter valid tasks
    temp = []
    for task in response:
        for func in funcs:
            if task.startswith(func):
                temp.append(task)
    response = temp
    # Handle fallback for ambiguous queries
    if "(query)" in response:
        newresponse = FirstLayerDMM(prompt=prompt)
        return newresponse
    else:
        return response

if __name__ == "__main__":
    while True:
        user_input = input(">>> ")
        if user_input.lower() in ["exit", "bye", "quit"]:
            print("exit")
            break
        
        decision = FirstLayerDMM(user_input)
        print(decision)
        
        # Handle WhatsApp message
        if any("whatsapp message" in task for task in decision):
            recipient = input("Enter the recipient's phone number: ")
            message = input("Enter the message: ")
            print(f"whatsapp {recipient} {message}")
        elif not decision:
            print("No valid command detected. Please try again.")