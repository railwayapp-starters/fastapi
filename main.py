from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pdfplumber
import pandas as pd
import re
from pathlib import Path

app = FastAPI()

# Setup CORS
origins = [
    "http://localhost",
    "http://localhost:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_FOLDER = Path('uploads')
ALLOWED_EXTENSIONS = {'pdf'}


def allowed_file(filename: str):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text_from_pdf(pdf_path):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text()
    return text


@app.post("/upload/")
async def upload_and_process_pdf(file: UploadFile = File(...)):
    if not allowed_file(file.filename):
        raise HTTPException(status_code=400, detail="File type not allowed")

    filename = Path(file.filename).name
    pdf_path = UPLOAD_FOLDER / filename

    with open(pdf_path, "wb") as buffer:
        buffer.write(await file.read())

    text = extract_text_from_pdf(pdf_path)

    ner = re.compile(r'([A-Za-z].*?) (\d+\.\d{2} +|\d+\.\d{1} +|\d+|\s+)')
    arr = {}
    for line in text.split('\n'):
        match = ner.match(line)
        if match:
            vand_name, vand_num = match.groups()
            arr[vand_name.strip()] = vand_num

    df = pd.DataFrame(list(arr.items()), columns=['Test', 'Result'])
    keywords = ['Haemoglobin', 'Hemoglobin', 'Iron', 'Vitamin D', 'Vitamin B12']
    filtered_df = df[df['Test'].str.contains('|'.join(keywords))]

    result_array = filtered_df.to_dict('records')
    return result_array


if __name__ == '__main__':
    if not UPLOAD_FOLDER.exists():
        UPLOAD_FOLDER.mkdir(parents=True)
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
