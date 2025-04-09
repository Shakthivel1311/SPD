import os
import time  # Added for delay
import threading
import numpy as np
import requests
import firebase_admin
from firebase_admin import credentials, db
from flask import Flask, render_template, request, jsonify
from PIL import Image
from io import BytesIO
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Dropout, GlobalAveragePooling2D
from tensorflow.keras.applications import MobileNetV2

# Initialize Flask App
app = Flask(__name__)

# Firebase Initialization
cred = credentials.Certificate("smart-waste-s1257-firebase-adminsdk-fbsvc-e9b1bd9cb2.json")  
firebase_admin.initialize_app(cred, {
    "databaseURL": "https://smart-waste-s1257-default-rtdb.firebaseio.com"
})

# Define class labels
labels = {0: 'biodegradable', 1: 'non-biodegradable'}

# Bin location (example coordinates)
BIN_LOCATION = {
    'latitude': 13.005459,
    'longitude': 77.569199
}

# Function to preprocess the image
def preprocess(image):
    image = image.resize((300, 300))
    image = np.array(image) / 255.0  # Normalize pixel values
    return image

# Function to load the model
def load_model():
    base_model = MobileNetV2(input_shape=(300, 300, 3), include_top=False, weights='imagenet')
    base_model.trainable = False  # Freeze the base model
    model = Sequential([
        base_model,
        GlobalAveragePooling2D(),
        Dense(128, activation='relu'),
        Dropout(0.5),
        Dense(1, activation='sigmoid')
    ])
    model.load_weights("modelnew.keras")  # Load pre-trained weights
    return model

model = load_model()

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/bin-status")
def bin_status():
    return render_template("bin-status.html")

@app.route("/bin-location")
def bin_location():
    return render_template("bin-location.html")

@app.route("/api/bin-level")
def get_bin_level():
    try:
        ref = db.reference("garbage_bin")
        bin_data = ref.get()
        return jsonify({
            "biodegradable_level": bin_data.get("BiodegradableBin", {}).get("level", 0),
            "non_biodegradable_level": bin_data.get("NonBiodegradableBin", {}).get("level", 0)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/bin-location")
def get_bin_location():
    return jsonify(BIN_LOCATION)

# Function to update Firebase asynchronously
def update_bin_status(predicted_class):
    biodegradable_bin_status = predicted_class == "biodegradable"
    non_biodegradable_bin_status = not biodegradable_bin_status

    # Open the bin
    db.reference("garbage_bin").update({
        "waste_type": predicted_class,
        "lid_status": "open",
        "BiodegradableBin/Open": biodegradable_bin_status,
        "NonBiodegradableBin/Open": non_biodegradable_bin_status
    })
    
    time.sleep(10)  # Keep bin open for 10 seconds

    # Close the bin
    db.reference("garbage_bin").update({
        "lid_status": "closed",
        "BiodegradableBin/Open": False,
        "NonBiodegradableBin/Open": False
    })

@app.route("/predict", methods=["POST"])
def predict():
    if "file" in request.files:
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No selected file"}), 400
        image = Image.open(file)
    
    elif "url" in request.json:
        img_url = request.json["url"]
        try:
            response = requests.get(img_url)
            image = Image.open(BytesIO(response.content))
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    
    else:
        return jsonify({"error": "No image provided"}), 400

    img = preprocess(image)
    prediction = model.predict(img[np.newaxis, ...])
    predicted_class = labels[int(np.round(prediction[0]))]

    # Start a separate thread for Firebase updates
    threading.Thread(target=update_bin_status, args=(predicted_class,)).start()

    return jsonify({
        "waste_type": predicted_class,
        "lid_status": "open",
        "BiodegradableBin_Open": predicted_class == "biodegradable",
        "NonBiodegradableBin_Open": predicted_class == "non-biodegradable"
    })

if __name__ == "__main__":
    app.run(debug=True)
