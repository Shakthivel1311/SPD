from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Conv2D, MaxPooling2D, Flatten, Dense, Dropout
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.preprocessing.image import ImageDataGenerator
import numpy as np
from PIL import Image
import os
import time
import json
import logging
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, db

# Enable OneDNN optimizations
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '1'

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Firebase initialization
def initialize_firebase():
    """Initialize Firebase with credentials"""
    try:
        # Check if Firebase app is already initialized
        if not firebase_admin._apps:
            cred = credentials.Certificate("smart-waste-s1257-firebase-adminsdk-fbsvc-e9b1bd9cb2.json")
            firebase_admin.initialize_app(cred, {
                "databaseURL": "https://smart-waste-s1257-default-rtdb.firebaseio.com"
            })
            logger.info("Firebase initialized successfully")
        else:
            logger.info("Firebase already initialized")
        return True
    except Exception as e:
        logger.error(f"Firebase initialization failed: {str(e)}")
        # Check if it's an authentication error
        if "invalid_grant" in str(e):
            logger.error("Authentication error. Please check your Firebase credentials file.")
            logger.error("Make sure the service account JSON file is valid and has the correct permissions.")
        return False

# Image processing utilities
def preprocess_image(image):
    """Preprocess image for model prediction"""
    try:
        # Resize image to 300x300
        image = image.resize((300, 300))
        # Convert to array and normalize
        image_array = np.array(image) / 255.0
        return image_array
    except Exception as e:
        logger.error(f"Image preprocessing failed: {str(e)}")
        return None

def save_uploaded_image(file, upload_folder='uploads'):
    """Save uploaded image to specified folder"""
    try:
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"waste_{timestamp}.jpg"
        filepath = os.path.join(upload_folder, filename)
        
        file.save(filepath)
        logger.info(f"Image saved successfully: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Failed to save image: {str(e)}")
        return None

# Firebase database operations
def update_bin_status(waste_type):
    """Update bin status in Firebase"""
    try:
        ref = db.reference("garbage_bin")
        biodegradable_bin_status = waste_type == "biodegradable"
        non_biodegradable_bin_status = not biodegradable_bin_status

        # Update bin status
        ref.update({
            "waste_type": waste_type,
            "lid_status": "open",
            "BiodegradableBin/Open": biodegradable_bin_status,
            "NonBiodegradableBin/Open": non_biodegradable_bin_status,
            "timestamp": datetime.now().isoformat()
        })
        
        logger.info(f"Bin status updated for {waste_type} waste")
        return True
    except Exception as e:
        logger.error(f"Failed to update bin status: {str(e)}")
        return False

def get_bin_levels():
    """Get current bin levels from Firebase"""
    try:
        if not firebase_admin._apps:
            logger.error("Firebase not initialized")
            return None
            
        ref = db.reference("garbage_bin")
        bin_data = ref.get()
        
        if bin_data:
            return {
                "biodegradable_level": bin_data.get("BiodegradableBin", {}).get("level", 0),
                "non_biodegradable_level": bin_data.get("NonBiodegradableBin", {}).get("level", 0),
                "timestamp": bin_data.get("timestamp", "")
            }
        return None
    except Exception as e:
        logger.error(f"Failed to get bin levels: {str(e)}")
        if "invalid_grant" in str(e):
            logger.error("Authentication error. Please check your Firebase credentials.")
        return None

def update_bin_levels(bin_type, level):
    """Update bin levels in Firebase"""
    try:
        ref = db.reference(f"garbage_bin/{bin_type}/level")
        ref.set(level)
        logger.info(f"Updated {bin_type} bin level to {level}")
        return True
    except Exception as e:
        logger.error(f"Failed to update bin level: {str(e)}")
        return False

# Error handling and validation
def validate_image(file):
    """Validate uploaded image"""
    try:
        # Check if file exists
        if not file:
            return False, "No file uploaded"
        
        # Check file extension
        allowed_extensions = {'png', 'jpg', 'jpeg'}
        if not '.' in file.filename or \
           file.filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
            return False, "Invalid file type"
        
        # Check file size (max 5MB)
        if len(file.read()) > 5 * 1024 * 1024:
            return False, "File too large"
        
        file.seek(0)  # Reset file pointer
        return True, "Valid image"
    except Exception as e:
        logger.error(f"Image validation failed: {str(e)}")
        return False, str(e)

# Response formatting
def format_response(success, message, data=None):
    """Format API response"""
    response = {
        "success": success,
        "message": message,
        "timestamp": datetime.now().isoformat()
    }
    if data:
        response["data"] = data
    return response

# Cleanup utilities
def cleanup_old_images(upload_folder='uploads', max_age_hours=24):
    """Clean up old uploaded images"""
    try:
        if not os.path.exists(upload_folder):
            return
        
        current_time = time.time()
        for filename in os.listdir(upload_folder):
            filepath = os.path.join(upload_folder, filename)
            if os.path.getmtime(filepath) < current_time - (max_age_hours * 3600):
                os.remove(filepath)
                logger.info(f"Deleted old image: {filepath}")
    except Exception as e:
        logger.error(f"Cleanup failed: {str(e)}")

def gen_labels():
    # Define the training dataset path
    train = 'C:/Users/Shakthivel/OneDrive/Documents/Christ/Project/Smart Waste/Data/Train'
    
    # Initialize ImageDataGenerator and flow data from the directory
    train_generator = ImageDataGenerator(rescale=1/255)
    train_generator = train_generator.flow_from_directory(
        train,
        target_size=(300, 300),
        batch_size=32,
        class_mode='sparse'
    )
    
    # Get class labels and reverse the dictionary (indices -> labels)
    labels = train_generator.class_indices
    labels = dict((v, k) for k, v in labels.items())
    
    return labels

def preprocess(image):
    """
    Preprocess the image for the model.
    This function resizes the image to 300x300, normalizes it to [0, 1],
    and ensures the image is in the appropriate format for model prediction.
    """

    # Convert the image to RGB (in case it's not in RGB format, e.g., grayscale or RGBA)
    image = image.convert('RGB')
    
    # Resize image to 300x300 using Image.Resampling.LANCZOS (high-quality resampling)
    image = np.array(image.resize((300, 300), Image.Resampling.LANCZOS))
    
    # Normalize the image to [0, 1]
    image = image.astype('float32') / 255.0
    
    # Ensure the image has the shape (height, width, channels)
    if image.ndim == 2:  # If it's grayscale, convert it to 3 channels
        image = np.stack([image] * 3, axis=-1)
    
    return image

def model_arc():
    # Initialize a Sequential model
    model = Sequential()

    # Convolution blocks
    model.add(Conv2D(32, kernel_size=(3, 3), padding='same', input_shape=(300, 300, 3), activation='relu'))
    model.add(MaxPooling2D(pool_size=2))

    model.add(Conv2D(64, kernel_size=(3, 3), padding='same', activation='relu'))
    model.add(MaxPooling2D(pool_size=2))

    model.add(Conv2D(128, kernel_size=(3, 3), padding='same', activation='relu'))  # Increased feature maps
    model.add(MaxPooling2D(pool_size=2))

    # Flatten the output and pass through fully connected layers
    model.add(Flatten())

    model.add(Dense(64, activation='relu'))
    model.add(Dropout(0.5))  # Increased dropout rate to prevent overfitting
    model.add(Dense(32, activation='relu'))

    model.add(Dropout(0.5))  # Increased dropout rate
    model.add(Dense(6, activation='softmax'))  # Output layer with 6 classes

    # Compile the model with Adam optimizer and sparse categorical crossentropy loss
    model.compile(optimizer=Adam(), loss='sparse_categorical_crossentropy', metrics=['accuracy'])
    
    return model
