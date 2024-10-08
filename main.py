from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI()

@app.get("/scrape")
async def scrape():
    url = "https://www.ibaraki-ct.ac.jp/info/archives/65544"
    date_pattern = r"\d{1,2}／\d{1,2}（.*?）"
    # Webページの内容を取得
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    paragraphs = soup.find_all('p')
    new_list = []
    for p in paragraphs:
        if re.search(date_pattern, p.get_text()):
            new_list.append(p.get_text())

    print(new_list)
    return {"result": new_list}

@app.get("/")
async def root():
    return {"greeting": "Hello, World!", "message": "Welcome to FastAPI!"}