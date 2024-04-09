from flask import Flask, request, jsonify
from flask_cors import CORS
import pdfplumber
import pandas as pd
import re
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text_from_pdf(pdf_path):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text()
    return text


@app.route('/upload', methods=['POST'])
def upload_and_process_pdf():
    if 'file' not in request.files:
        return jsonify({'message': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'message': 'No selected file'}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(pdf_path)

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
        return jsonify(result_array), 200
    else:
        return jsonify({'message': 'File type not allowed'}), 400


if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.run(debug=True)
