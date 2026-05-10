from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
from Main import MainExecution
import os

app = FastAPI()

class ChatRequest(BaseModel):
    message: str

@app.get("/")
def home():
    return {"status": "Jagruti AI Running"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.post("/chat")
async def chat(req: ChatRequest):
    user_message = req.message
    
    # Call the AI function
    response = MainExecution(user_message)

    return {"response": response}

if __name__ == "__main__":
    # Use the PORT environment variable if available, otherwise default to 10000
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
