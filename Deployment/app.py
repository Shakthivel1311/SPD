import os
import time
import threading
import numpy as np
import requests
import firebase_admin
from firebase_admin import credentials, db
from flask import Flask, render_template, request, jsonify
from PIL import Image
from io import BytesIO
import tensorflow as tf
from tensorflow.keras.models import load_model
import gdown
from utils import (
    initialize_firebase,
    preprocess_image,
    update_bin_status,
    get_bin_levels,
    validate_image,
    format_response
)

# Initialize Flask App
app = Flask(__name__)

# Firebase Initialization
initialize_firebase()

# Define class labels
labels = {0: 'biodegradable', 1: 'non-biodegradable'}

# Bin location (example coordinates)
BIN_LOCATION = {
    'latitude': 13.005459,
    'longitude': 77.569199
}

# Function to download model from Google Drive
def download_model():
    model_path = "model.keras"
    if not os.path.exists(model_path):
        print("Attempting to download model from Google Drive...")
        try:
            url = "https://drive.google.com/uc?id=19DC9dL2PRqd9OM7VYy2aTcLJ3msZd8Mw"
            gdown.download(url, model_path, quiet=False)
        except Exception as e:
            print(f"Failed to download model automatically: {str(e)}")
            print("\nPlease download the model manually:")
            print("1. Visit: https://drive.google.com/uc?id=19DC9dL2PRqd9OM7VYy2aTcLJ3msZd8Mw")
            print("2. Download the file")
            print("3. Save it as 'model.keras' in the project directory")
            print("4. Restart the application")
            return None
    return model_path

# Function to load the model
def load_waste_model():
    try:
        model_path = download_model()
        if model_path is None:
            print("Model file not found. Please download it manually as instructed above.")
            return None
        
        print("Loading model...")
        model = load_model(model_path)
        print("Model loaded successfully")
        return model
    except Exception as e:
        print(f"Error loading model: {str(e)}")
        return None

# Load the model
model = load_waste_model()

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
        bin_data = get_bin_levels()
        if bin_data:
            return jsonify(bin_data)
        return jsonify({"error": "Failed to get bin levels"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/bin-location")
def get_bin_location():
    return jsonify(BIN_LOCATION)

@app.route("/predict", methods=["POST"])
def predict():
    if "file" in request.files:
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No selected file"}), 400
        
        # Validate image
        is_valid, message = validate_image(file)
        if not is_valid:
            return jsonify({"error": message}), 400
        
        try:
            image = Image.open(file)
            img = preprocess_image(image)
            if img is None:
                return jsonify({"error": "Failed to preprocess image"}), 400
            
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
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    elif "url" in request.json:
        img_url = request.json["url"]
        try:
            response = requests.get(img_url)
            image = Image.open(BytesIO(response.content))
            img = preprocess_image(image)
            if img is None:
                return jsonify({"error": "Failed to preprocess image"}), 400
            
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
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    
    else:
        return jsonify({"error": "No image provided"}), 400

if __name__ == "__main__":
    app.run(debug=True)
