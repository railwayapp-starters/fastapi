from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"greeting": "Hellno, World!", "message": "Welcome to FastAPI!"}
