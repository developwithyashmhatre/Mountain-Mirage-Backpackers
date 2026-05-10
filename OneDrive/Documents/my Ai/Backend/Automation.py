from __future__ import annotations

import asyncio
import os
import subprocess
import webbrowser
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup
from dotenv import dotenv_values
from groq import Groq
from rich import print

try:
    import keyboard  # type: ignore
except Exception:
    keyboard = None

try:
    from AppOpener import close, open as appopen  # type: ignore
except Exception:
    close = None
    appopen = None

try:
    from pywhatkit import playonyt, search  # type: ignore
except Exception:
    playonyt = None
    search = None

# Load environment variables from the .env file
env_vars = dotenv_values(".env")
GroqAPIKey = os.environ.get("GROQ_API_KEY", env_vars.get("GroqAPIKey"))
Username = env_vars.get("Username", os.environ.get("USERNAME", "User"))

# Define CSS classes for parsing specific elements in HTML content
classes = ["zCubwf", "hgKElc", "LTK00 sY7ric", "Z0LcW", "gsrt vk_bk FzvWSb YwPhnf", "pclqee", "tw-Data-text tw-text-small tw-ta",
           "IZ6rdc", "05uR6d LTK00", "vlzY6d", "webanswers-webanswers_table_webanswers-table", "dDoNo ikb4Bb gsrt", "sXLa0e",
           "LWkfKe", "VQF4g", "qv3Wpe", "kno-rdesc", "SPZz6b"]

# Define a user-agent for making web requests
useragent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'

# Initialize the Groq client with the API key
client = Groq(api_key=GroqAPIKey)

# Predefined professional responses for user interactions
professional_responses = [
    "Your satisfaction is my top priority; feel free to reach out if there's anything else I can help you with.",
    "I'm at your service for any additional questions or support you may need-don't hesitate to ask.",
]

# List to store chatbot messages
messages = []

# System message to provide context to the chatbot
SystemChatBot = [{"role": "system", "content": f"Hello, I am {Username}, You're a content writer. You have to write content like letters, articles, and more."}]

# Function to perform a Google search
def GoogleSearch(Topic):
    if search is None:
        raise RuntimeError("pywhatkit is not installed; GoogleSearch is unavailable.")
    search(Topic)
    return True

# Function to generate content using AI and save it to a file
def Content(Topic):
    def OpenNotepad(File):
        default_text_editor = 'notepad.exe'
        subprocess.Popen([default_text_editor, File])

    def ContentWriterAI(prompt):
        messages.append({"role": "user", "content": f"{prompt}"})
        completion = client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=SystemChatBot + messages,
            max_tokens=2048,
            temperature=0.7,
            top_p=1,
            stream=True,
            stop=None
        )
        Answer = ""
        for chunk in completion:
            if chunk.choices[0].delta.content:
                Answer += chunk.choices[0].delta.content
        Answer = Answer.replace("</s>", "")
        messages.append({"role": "assistant", "content": Answer})
        return Answer

    Topic = Topic.replace("Content", "")
    ContentByAI = ContentWriterAI(Topic)
    with open(rf"Data\{Topic.lower().replace(' ', '')}.txt", "w", encoding="utf-8") as file:
        file.write(ContentByAI)
    OpenNotepad(rf"Data\{Topic.lower().replace(' ', '')}.txt")
    return True

# Function to search on YouTube
def YouTubeSearch(Topic):
    Url4Search = f"https://www.youtube.com/results?search_query={Topic}"
    webbrowser.open(Url4Search)
    return True

# Function to play a video on YouTube
def PlayYoutube(query):
    if playonyt is None:
        raise RuntimeError("pywhatkit is not installed; PlayYoutube is unavailable.")
    playonyt(query)
    return True

def _extract_google_result_links(html):
    if html is None:
        return []
    soup = BeautifulSoup(html, "html.parser")
    links = soup.find_all("a", {"jsname": "UWckNb"})
    out = []
    for link in links:
        href = link.get("href")
        if href and href.startswith("http"):
            out.append(href)
    return out


def _search_google_html(query, sess: requests.Session):
    url = f"https://www.google.com/search?q={quote_plus(query)}"
    headers = {"User-Agent": useragent}
    response = sess.get(url, headers=headers, timeout=15)
    if response.status_code == 200:
        return response.text
    print(f"Failed to retrieve search results (HTTP {response.status_code}).")
    return None


# Function to open an application or a relevant webpage
def OpenApp(app, sess=requests.Session()):
    app_name = (app or "").strip()
    if not app_name:
        print("[Automation] Open app: empty name.")
        return False

    try:
        if appopen is None:
            raise RuntimeError("AppOpener is not installed; OpenApp is unavailable.")
        appopen(app_name, match_closest=True, output=True, throw_error=True)
        return True
    except Exception as exc:
        print(f"[Automation] AppOpener could not open '{app_name}': {exc}")

    if os.name == "nt":
        try:
            subprocess.Popen(
                ["cmd", "/c", "start", "", app_name],
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception as exc:
            print(f"[Automation] Windows start fallback failed: {exc}")

    try:
        html = _search_google_html(f"{app_name} official download", sess)
        links = _extract_google_result_links(html)
        if links:
            webopen(links[0])
            return True
        print(f"[Automation] No web results to open for '{app_name}'.")
    except Exception as exc:
        print(f"[Automation] Web fallback failed: {exc}")

    return False

# Function to close an application
def CloseApp(app):
    if "chrome" in app:
        pass
    else:
        try:
            if close is None:
                raise RuntimeError("AppOpener is not installed; CloseApp is unavailable.")
            close(app, match_closest=True, output=True, throw_error=True)
            return True
        except:
            return False

# Function to execute system-level commands
def System(command):
    def mute():
        if keyboard is None:
            raise RuntimeError("keyboard is not installed; System commands are unavailable.")
        keyboard.press_and_release("volume mute")

    def unmute():
        if keyboard is None:
            raise RuntimeError("keyboard is not installed; System commands are unavailable.")
        keyboard.press_and_release("volume mute")

    def volume_up():
        if keyboard is None:
            raise RuntimeError("keyboard is not installed; System commands are unavailable.")
        keyboard.press_and_release("volume up")

    def volume_down():
        if keyboard is None:
            raise RuntimeError("keyboard is not installed; System commands are unavailable.")
        keyboard.press_and_release("volume down")

    if command == "mute":
        mute()
    elif command == "unmute":
        unmute()
    elif command == "volume up":
        volume_up()
    elif command == "volume down":
        volume_down()
    return True

# Asynchronous function to translate and execute user commands
async def TranslateAndExecute(commands: list[str]):
    funcs = []
    for command in commands:
        if command.startswith("open "):
            if "open it" in command or "open file" == command:
                pass
            else:
                fun = asyncio.to_thread(OpenApp, command.removeprefix("open "))
                funcs.append(fun)
        elif command.startswith("general") or command.startswith("realtime "):
            pass
        elif command.startswith("close"):
            fun = asyncio.to_thread(CloseApp, command.removeprefix("close"))
            funcs.append(fun)
        elif command.startswith("play "):
            fun = asyncio.to_thread(PlayYoutube, command.removeprefix("play "))
            funcs.append(fun)
        elif command.startswith("content"):
            fun = asyncio.to_thread(Content, command.removeprefix("content"))
            funcs.append(fun)
        elif command.startswith("google search "):
            fun = asyncio.to_thread(GoogleSearch, command.removeprefix("google search "))
            funcs.append(fun)
        elif command.startswith("youtube search "):
            fun = asyncio.to_thread(YouTubeSearch, command.removeprefix("youtube search "))
            funcs.append(fun)
        elif command.startswith("system"):
            fun = asyncio.to_thread(System, command.removeprefix("system "))
            funcs.append(fun)
        else:
            print(f"No Function Found. For {command}")
    results = await asyncio.gather(*funcs)
    for result in results:
        if isinstance(result, str):
            yield result
        else:
            yield result

# Asynchronous function to automate command execution
async def Automation(commands: list[str]):
    async for result in TranslateAndExecute(commands):
        pass
    return True