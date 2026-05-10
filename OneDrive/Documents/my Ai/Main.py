from asyncio import run
from dotenv import dotenv_values
from Backend.Automation import Automation
from Backend.Chatbot import ChatBot
from Backend.ImageGeneration import GenerateImages
from Backend.Model import FirstLayerDMM
from Backend.RealtimeSearchEngine import realtime_search_engine
from Backend.realtime_search.intent_local import upgrade_general_to_realtime
from Backend.SIE import try_society_intelligence
env_vars = dotenv_values(".env")
USERNAME = env_vars.get("Username", "User")
ASSISTANT_NAME = env_vars.get("Assistantname", "Assistant")
AUTOMATION_PREFIXES = (
    "open ",
    "close ",
    "play ",
    "system ",
    "content ",
    "google search ",
    "youtube search ",
)
def normalize_query(text: str) -> str:
    return " ".join(text.strip().split())
def handle_intent(query: str) -> str:
    try:
        sie_reply = try_society_intelligence(query)
    except Exception as exc:
        sie_reply = None

    if sie_reply is not None:
        return str(sie_reply)

    try:
        decision = FirstLayerDMM(query)
    except Exception as exc:
        return f"Intent parsing error: {exc}"

    if decision:
        decision = upgrade_general_to_realtime(list(decision), query)

    if not decision:
        try:
            answer = ChatBot(query)
            return str(answer)
        except Exception as exc:
            return f"Chat error: {exc}"

    if any(task.startswith("exit") for task in decision):
        return "Goodbye!"

    if any(task.startswith(AUTOMATION_PREFIXES) for task in decision):
        try:
            run(Automation(list(decision)))
            return "Automation tasks executed successfully."
        except Exception as exc:
            return f"Automation error: {exc}"

    for task in decision:
        if task.startswith("generate image"):
            prompt = task.replace("generate image", "", 1).strip() or query
            try:
                GenerateImages(prompt)
                return f"Generating images for '{prompt}'..."
            except Exception as exc:
                return f"Image generation error: {exc}"

    general_or_realtime = [
        task for task in decision if task.startswith("general") or task.startswith("realtime")
    ]

    if not general_or_realtime:
        return "No general or realtime tasks found in decision."

    if any(task.startswith("realtime") for task in general_or_realtime):
        merged_query = " and ".join(
            " ".join(task.split()[1:]).strip() for task in general_or_realtime
        ).strip()
        try:
            answer = realtime_search_engine(normalize_query(merged_query or query))
            return str(answer)
        except Exception as exc:
            return f"Realtime search error: {exc}"

    for task in general_or_realtime:
        if task.startswith("general"):
            pure_query = task.replace("general", "", 1).strip()
            try:
                answer = ChatBot(normalize_query(pure_query or query))
                return str(answer)
            except Exception as exc:
                return f"Chat error: {exc}"

    return "I'm sorry, I couldn't process that request."

def MainExecution(query: str) -> str:
    """Wrapper for the API to get the AI response."""
    return handle_intent(query)

def main() -> None:
    print(f"{ASSISTANT_NAME} CLI ready for {USERNAME}. Type 'exit' to quit.\n")
    while True:
        try:
            query = input(f"{USERNAME}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{ASSISTANT_NAME}: Goodbye!")
            break
        if not query:
            continue
        if query.lower() in {"exit", "quit", "bye"}:
            print(f"{ASSISTANT_NAME}: Goodbye!")
            break
        
        response = MainExecution(query)
        print(f"{ASSISTANT_NAME}: {response}\n")
        
        if response == "Goodbye!":
            break

if __name__ == "__main__":
    main()
if __name__ == "__main__":
    main()


