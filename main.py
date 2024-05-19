from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
import uvicorn
import tensorflow as tf
from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing.image import img_to_array, load_img
import numpy as np
import io
from PIL import Image

app = FastAPI()

# Load the trained model
model = load_model('palm_disease_classifier.keras.hdf5')

# Define the labels
labels_dict = {0: 'Healthy', 1: 'Infected', 2: 'Last Stage'}

@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    try:
        # Read the image file
        contents = await file.read()
        image = Image.open(io.BytesIO(contents)).convert("RGB")
        
        # Preprocess the image
        image = image.resize((200, 200))
        image = img_to_array(image)
        image = np.expand_dims(image, axis=0)
        
        # Make a prediction
        prediction = model.predict(image)
        predicted_class = np.argmax(prediction[0])
        predicted_label = labels_dict[predicted_class]
        
        return JSONResponse(content={"prediction": predicted_label})
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
