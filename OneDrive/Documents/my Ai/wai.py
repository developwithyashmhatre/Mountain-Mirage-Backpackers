import time
import pyttsx3
import pyautogui
import win32gui
import re
from win10toast import ToastNotifier
from Backend.SpeechToText import speech_recognition  # Custom speech-to-text module
from groq import Groq
from dotenv import dotenv_values

# Load AI Assistant Config
env_vars = dotenv_values(".env")
GroqAPIKey = env_vars.get("GroqAPIKey")
client = Groq(api_key=GroqAPIKey)

# Initialize
engine = pyttsx3.init()
notifier = ToastNotifier()
last_notification = None
message_queue = []  # Stores incoming messages for continuous voice interaction

def speak_text(text):
    """Convert text to speech."""
    engine.say(text)
    engine.runAndWait()

def get_whatsapp_notification():
    """Detect WhatsApp notification and extract sender + message."""
    def enum_handler(hwnd, result):
        global last_notification
        if win32gui.IsWindowVisible(hwnd):
            window_text = win32gui.GetWindowText(hwnd)
            if "WhatsApp" in window_text:
                if window_text != last_notification:
                    last_notification = window_text
                    result.append(window_text)

    windows = []
    win32gui.EnumWindows(enum_handler, windows)
    notification = windows[0] if windows else None
    
    if notification:
        match = re.match(r"(.+?): (.+)", notification)
        if match:
            sender, message = match.groups()
            return sender.strip(), message.strip()
    return None, None

def listen_for_command():
    """Continuously listens for user commands using speech-to-text from Backend.SpeechToText."""
    print("Listening for command...")
    speak_text("Main sun raha hoon. Aap kya poochna chahte hain?")
    command = speech_recognition()  # Using the custom speech-to-text function
    if command:
        print("User Command:", command)
        return command.lower()
    return None

def generate_ai_reply(sender, message, reaction):
    """Generate a context-aware AI reply based on sender, message, and reaction."""
    prompt = f"User received a WhatsApp message from {sender}: '{message}'. User reacted: '{reaction}'. Generate a professional and context-aware reply."
    try:
        completion = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.7
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"AI Agent Error: {e}")
        return "Main jawab nahi bana saka."

def auto_reply(sender, message):
    """Reply to a specific WhatsApp contact."""
    pyautogui.hotkey('win', 's')  # Open Windows search
    time.sleep(1)
    pyautogui.write("WhatsApp")
    time.sleep(1)
    pyautogui.press("enter")  # Open WhatsApp
    time.sleep(5)

    pyautogui.hotkey('ctrl', 'f')  # Open search in WhatsApp
    time.sleep(1)
    pyautogui.write(sender)  # Type sender's name
    time.sleep(2)
    pyautogui.press("enter")  # Open chat
    time.sleep(2)

    pyautogui.write(message)  # Type reply message
    pyautogui.press("enter")  # Send message

    print(f"{sender} ko jawab diya: {message}")
    speak_text(f"{sender} ko jawab diya: {message}")

def monitor_notifications():
    """Continuously check for WhatsApp notifications and process user commands."""
    global last_notification
    while True:
        sender, message = get_whatsapp_notification()
        
        if sender and message and last_notification != f"{sender}: {message}":
            print(f"Naya Message: {sender} - {message}")
            speak_text(f"Aapko ek WhatsApp sandesh aaya hai.")
            message_queue.append((sender, message))  # Store for interaction
            last_notification = f"{sender}: {message}"

            notifier.show_toast("WhatsApp Alert", f"{sender}: {message}", duration=5)

        # Listen for user command
        command = listen_for_command()
        if command:
            if "message" in command or "kaun" in command or "kisne" in command:
                if message_queue:
                    latest_sender, latest_message = message_queue[-1]
                    if "kaun" in command or "kisne" in command:
                        response = f"Sandesh bhejne wala hai {latest_sender}."
                    elif "message" in command:
                        response = f"Sandesh hai: {latest_message}"
                    else:
                        response = "Mujhe samajh nahi aaya."
                    print(response)
                    speak_text(response)
