#define TRIG_BIO  2   // Biodegradable TRIG
#define ECHO_BIO  4   // Biodegradable ECHO
#define SERVO_BIO 13  // Biodegradable Servo

#define TRIG_NON_BIO  18   // Non-Biodegradable TRIG
#define ECHO_NON_BIO  19  // Non-Biodegradable ECHO
#define SERVO_NON_BIO 14  // Non-Biodegradable Servo

#define TRIG_PRESENCE  25   // Presence Detection TRIG
#define ECHO_PRESENCE  26  // Presence Detection ECHO

#include <ESP32Servo.h>
#include <WiFi.h>
#include <FirebaseESP32.h>

// WiFi Credentials
#define WIFI_SSID "iPhone"
#define WIFI_PASSWORD "00000000"

// Firebase Credentials
#define FIREBASE_HOST "https://smart-waste-s1257-default-rtdb.firebaseio.com/"
#define FIREBASE_AUTH "AIzaSyBbkPoI3RVO9VIOGdOVFVZFFdK_nc7J4_w"

FirebaseData firebaseData;
FirebaseAuth firebaseAuth;
FirebaseConfig firebaseConfig;

Servo servoBio;
Servo servoNonBio;

const int binHeight = 21; // Height of the bin in cm
const unsigned long trashOpenDuration = 7000; // Time to keep the bin open (7 seconds)
unsigned long trashOpenTime = 0; // Timer for bin open duration
bool isBioOpen = false; // Track if biodegradable bin is open
bool isNonBioOpen = false; // Track if non-biodegradable bin is open

void setup() {
    Serial.begin(115200);

    // Connect to WiFi
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.print("Connecting to WiFi");
    while (WiFi.status() != WL_CONNECTED) {
        Serial.print(".");
        delay(500);
    }
    Serial.println("\nConnected!");

    // Initialize Firebase
    firebaseConfig.host = FIREBASE_HOST;
    firebaseConfig.signer.tokens.legacy_token = FIREBASE_AUTH;
    Firebase.begin(&firebaseConfig, &firebaseAuth);
    Firebase.reconnectWiFi(true);
    Serial.println("Firebase Initialized!");

    // Setup pins
    pinMode(TRIG_BIO, OUTPUT);
    pinMode(ECHO_BIO, INPUT);
    pinMode(TRIG_NON_BIO, OUTPUT);
    pinMode(ECHO_NON_BIO, INPUT);
    pinMode(TRIG_PRESENCE, OUTPUT);
    pinMode(ECHO_PRESENCE, INPUT);

    // Initialize servos
    servoBio.attach(SERVO_BIO);
    servoBio.write(0); // Close biodegradable bin
    delay(500);
    servoBio.detach();

    servoNonBio.attach(SERVO_NON_BIO);
    servoNonBio.write(0); // Close non-biodegradable bin
    delay(500);
    servoNonBio.detach();
}

// Function to get distance from ultrasonic sensor
long getDistance(int trigPin, int echoPin) {
    digitalWrite(trigPin, LOW);
    delayMicroseconds(2);
    digitalWrite(trigPin, HIGH);
    delayMicroseconds(10);
    digitalWrite(trigPin, LOW);

    long duration = pulseIn(echoPin, HIGH, 100000); // Timeout after 100ms
    if (duration == 0) {
        Serial.println("Sensor Timeout! Check Connections.");
        return -1; // Return -1 if sensor fails
    }
    return (duration / 2) / 29.1;  // Convert to cm
}

// Function to calculate bin level percentage
int calculateBinLevel(long distance) {
    if (distance < 0) return 0; // If sensor fails, assume bin is empty
    int level = map(distance, binHeight, 0, 0, 100); // Map distance to percentage
    return constrain(level, 0, 100); // Constrain to 0-100%
}

// Function to check if someone is in front of the bin
bool isSomeoneInFront() {
    long distance = getDistance(TRIG_PRESENCE, ECHO_PRESENCE);

    Serial.print("Presence Sensor Distance: ");
    Serial.println(distance);

    if (distance > 0 && distance <= 4) {  // Adjust the threshold to 4 cm
        Serial.println("Person detected within 4 cm of the bin!");
        return true;
    }
    return false;
}

void loop() {
    // Measure bin distances
    long bioDistance = getDistance(TRIG_BIO, ECHO_BIO);
    long nonBioDistance = getDistance(TRIG_NON_BIO, ECHO_NON_BIO);

    // Handle non-biodegradable sensor issue
    if (nonBioDistance > binHeight || nonBioDistance == -1) {
        Serial.println("Non-Biodegradable Ultrasonic Sensor Issue Detected!");
        nonBioDistance = binHeight;  // Assume empty bin if sensor fails
    }

    // Calculate bin levels
    int bioLevel = calculateBinLevel(bioDistance);
    int nonBioLevel = calculateBinLevel(nonBioDistance);

    Serial.print("Biodegradable Bin Level: ");
    Serial.print(bioLevel);
    Serial.println("%");

    Serial.print("Non-Biodegradable Bin Level: ");
    Serial.print(nonBioLevel);
    Serial.println("%");

    // Update Firebase bin levels
    Firebase.setInt(firebaseData, "/BiodegradableBin/Level", bioLevel);
    Firebase.setInt(firebaseData, "/NonBiodegradableBin/Level", nonBioLevel);

    // Get waste type from Firebase
    String wasteType;
    if (Firebase.getString(firebaseData, "/garbage_bin/waste_type", &wasteType)) {
        Serial.print("Waste Type: ");
        Serial.println(wasteType);
    } else {
        Serial.println("Failed to get waste type from Firebase!");
    }

    // Get lid status from Firebase
    String lidStatus;
    if (Firebase.getString(firebaseData, "/garbage_bin/lid_status", &lidStatus)) {
        Serial.print("Lid Status: ");
        Serial.println(lidStatus);
    } else {
        Serial.println("Failed to get lid status from Firebase!");
    }

    // If someone is within 4 cm, open the biodegradable bin
    if (isSomeoneInFront()) {
        servoBio.attach(SERVO_BIO);
        servoBio.write(180); // Open biodegradable bin
        isBioOpen = true;
        trashOpenTime = millis(); // Start timer
        Serial.println("Biodegradable Bin Opens Automatically!");
    }

    // Open and close bins based on waste type and lid status
    if (wasteType == "biodegradable" && lidStatus == "open" && !isBioOpen) {
        servoBio.attach(SERVO_BIO);
        servoBio.write(180); // Open biodegradable bin
        isBioOpen = true;
        servoNonBio.write(0); // Ensure non-biodegradable bin is closed
        isNonBioOpen = false;
        delay(500);
        servoNonBio.detach();
        trashOpenTime = millis(); // Start timer
        Serial.println("Biodegradable Bin Opens!");
    } else if (wasteType == "biodegradable" && lidStatus == "closed" && isBioOpen) {
        servoBio.write(0); // Close biodegradable bin
        delay(500);
        servoBio.detach();
        isBioOpen = false;
        Serial.println("Biodegradable Bin Closes!");
    }

    if (wasteType == "non-biodegradable" && lidStatus == "open" && !isNonBioOpen) {
        servoNonBio.attach(SERVO_NON_BIO);
        servoNonBio.write(180); // Open non-biodegradable bin
        isNonBioOpen = true;
        servoBio.write(0); // Ensure biodegradable bin is closed
        isBioOpen = false;
        delay(500);
        servoBio.detach();
        trashOpenTime = millis(); // Start timer
        Serial.println("Non-Biodegradable Bin Opens!");
    } else if (wasteType == "non-biodegradable" && lidStatus == "closed" && isNonBioOpen) {
        servoNonBio.write(0); // Close non-biodegradable bin
        delay(500);
        servoNonBio.detach();
        isNonBioOpen = false;
        Serial.println("Non-Biodegradable Bin Closes!");
    }

    // Close bins after timeout
    if (isBioOpen && millis() - trashOpenTime >= trashOpenDuration) {
        servoBio.write(0); // Close biodegradable bin
        delay(500);
        servoBio.detach();
        isBioOpen = false;
        Serial.println("Biodegradable Bin Closes after timeout!");
    }
    
    if (isNonBioOpen && millis() - trashOpenTime >= trashOpenDuration) {
        servoNonBio.write(0); // Close non-biodegradable bin
        delay(500);
        servoNonBio.detach();
        isNonBioOpen = false;
        Serial.println("Non-Biodegradable Bin Closes after timeout!");
    }

    delay(1000); // Wait 1 second before next loop
}