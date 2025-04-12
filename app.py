import streamlit as st
import cv2
import numpy as np
import sqlite3
from PIL import Image
import io
import os
import smtplib
from email.message import EmailMessage
from datetime import datetime
import base64
import time
import uuid

# Initialize session state variables
if 'passkey_attempts' not in st.session_state:
    st.session_state.passkey_attempts = 0

if 'access_granted' not in st.session_state:
    st.session_state.access_granted = False

if 'show_main_options' not in st.session_state:
    st.session_state.show_main_options = False

if 'dataset_info' not in st.session_state:
    st.session_state.dataset_info = {'name': '', 'age': '', 'address': ''}

if 'crud_operation_verified' not in st.session_state:
    st.session_state.crud_operation_verified = False

if 'operation_type' not in st.session_state:
    st.session_state.operation_type = None

if 'selected_user_id' not in st.session_state:
    st.session_state.selected_user_id = None

if 'user_to_edit' not in st.session_state:
    st.session_state.user_to_edit = {'id': None, 'name': '', 'age': '', 'address': ''}

if 'authenticated_user' not in st.session_state:
    st.session_state.authenticated_user = None

if 'auth_method' not in st.session_state:
    st.session_state.auth_method = None

# Load Haar Cascade for face detection
cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
faceCascade = cv2.CascadeClassifier(cascade_path)

if faceCascade.empty():
    st.error("Error: Haar Cascade XML file could not be loaded.")
    st.stop()

# Load LBPH Recognizer
recognizer = cv2.face.LBPHFaceRecognizer_create()

# Database connection function
def get_db_connection():
    try:
        conn = sqlite3.connect('face_recognition.db')
        conn.row_factory = sqlite3.Row  # This enables column access by name
        return conn
    except Exception as e:
        st.error(f"Database connection error: {e}")
        return None

# Initialize database if it doesn't exist
def init_database():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create users table if it doesn't exist
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            age TEXT,
            address TEXT
        )
        ''')
        
        # Create face_images table to store facial images as binary data
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS face_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            image_data BLOB,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        ''')
        
        # Create settings table to store classifier and other settings
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE,
            value BLOB
        )
        ''')
        
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Database initialization error: {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            conn.close()

# Load classifier if it exists in the database
def load_classifier():
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'classifier'")
        classifier_data = cursor.fetchone()
        
        if classifier_data:
            # Save the classifier data temporarily to a file
            temp_file = "temp_classifier.xml"
            with open(temp_file, "wb") as f:
                f.write(classifier_data[0])
            
            # Load the classifier from the temporary file
            recognizer.read(temp_file)
            
            # Remove the temporary file
            os.remove(temp_file)
            return True
        else:
            return False
    except Exception as e:
        st.warning(f"Error loading classifier: {e}")
        return False
    finally:
        conn.close()

# Save classifier to database
def save_classifier():
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        # Save the classifier to a temporary file
        temp_file = "temp_classifier.xml"
        recognizer.write(temp_file)
        
        # Read the file as binary data
        with open(temp_file, "rb") as f:
            classifier_data = f.read()
        
        # Save to database
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                      ("classifier", classifier_data))
        conn.commit()
        
        # Remove the temporary file
        os.remove(temp_file)
        return True
    except Exception as e:
        st.error(f"Error saving classifier: {e}")
        return False
    finally:
        conn.close()

# Email Alert Function
def send_email_alert(person_name, confidence, img_data):
    try:
        email_sender = "samyak.1403@gmail.com"
        email_password = "jpcngoqvqeapstnz"  # Consider using environment variables for this
        email_receiver = "samyak.1403@gmail.com"

        subject = "🔔 Face Detection Alert"
        body = f"Person Detected: {person_name}\nConfidence Level: {confidence}%\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        msg = EmailMessage()
        msg['From'] = email_sender
        msg['To'] = email_receiver
        msg['Subject'] = subject
        msg.set_content(body)

        # Add the image directly from binary data
        msg.add_attachment(img_data, maintype='image', subtype='jpeg', filename='detected_face.jpg')

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(email_sender, email_password)
            server.send_message(msg)

        st.info(f"Email alert sent for {person_name}")
        return True
    except Exception as e:
        st.error(f"Email sending error: {e}")
        return False

# Detect Face Function
def detect_face():
    # Check if classifier exists in database
    classifier_exists = load_classifier()
    
    if not classifier_exists:
        st.error("Face recognition model not trained yet. Please add users and train classifier first.")
        return False
    
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        st.error("Error: Cannot access the webcam. Check your camera permissions!")
        return False

    stframe = st.empty()
    status_placeholder = st.empty()
    start_time = datetime.now()
    
    status_placeholder.info("Detecting face... Look at the camera")
    
    # Track if we've found a valid face
    face_detected = False
    person_name = None
    best_confidence = 0
    user_found_in_db = False  # Track if the user exists in database

    while (datetime.now() - start_time).seconds < 20:  # Maximum 20 seconds timeout
        ret, img = cap.read()
        if not ret:
            status_placeholder.error("Failed to read frame from webcam.")
            break

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = faceCascade.detectMultiScale(gray, 1.1, 5)

        for (x, y, w, h) in faces:
            cv2.rectangle(img, (x, y), (x+w, y+h), (255, 0, 0), 2)
            
            face_roi = gray[y:y+h, x:x+w]
            
            try:
                id, pred = recognizer.predict(face_roi)
                confidence = int(100 * (1 - pred / 300))
                
                conn = get_db_connection()
                if not conn:
                    status_placeholder.error("Could not connect to database")
                    continue
                    
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM users WHERE id=?", (id,))
                user_data = cursor.fetchone()
                cursor.close()
                conn.close()

                if user_data:
                    current_name = user_data[0]
                    cv2.putText(img, f"{current_name} ({confidence}%)", (x, y-10), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (36, 255, 12), 2)
                    
                    # Track the best confidence we've seen
                    if confidence > best_confidence:
                        best_confidence = confidence
                        person_name = current_name
                        user_found_in_db = True  # Mark that we found a valid user
                        
                    # Only set face_detected if we exceed the threshold
                    if confidence > 70:
                        face_detected = True
                else:
                    cv2.putText(img, f"Unknown ({confidence}%)", (x, y-10), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
                    
                    # Save unknown face and send alert after a few seconds
                    if (datetime.now() - start_time).seconds > 5:
                        # Convert the image to JPEG for email
                        _, buffer = cv2.imencode('.jpg', img)
                        img_data = buffer.tobytes()
                        
                        send_email_alert("Unknown", confidence, img_data)
                        status_placeholder.error("Unauthorized Person Detected. Alert Sent.")
                        # Set user_found_in_db to False even if confidence is high
                        user_found_in_db = False

            except Exception as e:
                status_placeholder.error(f"Recognition Error: {e}")

        # Convert color for display
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        stframe.image(img_rgb, caption="Face Detection", use_column_width=True)
        
        # Check if we've found a valid face with high confidence
        if face_detected:
            # Wait a bit longer to ensure we have a stable reading
            if (datetime.now() - start_time).seconds > 3:
                break

    cap.release()
    
    # Only grant access if a valid face was detected AND the user exists in database
    if face_detected and best_confidence > 70 and user_found_in_db:
        st.session_state.access_granted = True
        # Store the authenticated user's name
        st.session_state.authenticated_user = person_name
        # Set authentication method to face recognition
        st.session_state.auth_method = "face"
        # With face recognition, CRUD operations are pre-verified
        st.session_state.crud_operation_verified = True
        status_placeholder.success(f"Access Granted to {person_name} with {best_confidence}% confidence")
        return True
    else:
        if best_confidence > 0:
            if not user_found_in_db:
                status_placeholder.warning(f"Face detected but not found in database. Access denied.")
            else:
                status_placeholder.warning(f"Face detected but confidence too low ({best_confidence}%). Access denied.")
        else:
            status_placeholder.warning("No recognized face detected. Access denied.")
        return False
        
# Dataset Generation Function
def generate_dataset(user_id):
    name = st.session_state.dataset_info['name']
    
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        st.error("Error: Cannot access the webcam. Check your camera permissions!")
        return False
        
    counter = 0
    total_samples = 30
    progress_bar = st.progress(0)
    status_text = st.empty()
    frame_display = st.empty()
    
    status_text.info(f"Capturing face samples for {name}. Please look at the camera and move your head slightly.")
    
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        while counter < total_samples:
            ret, img = cap.read()
            if not ret:
                st.error("Error capturing image from webcam.")
                break
                
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = faceCascade.detectMultiScale(gray, 1.1, 5)
            
            if len(faces) > 0:  # Only save if a face is detected
                for (x, y, w, h) in faces:
                    cv2.rectangle(img, (x, y), (x+w, y+h), (0, 255, 0), 2)
                    
                    # Save only the face region
                    face_img = gray[y:y+h, x:x+w]
                    
                    # Convert the numpy array to a binary blob
                    _, buffer = cv2.imencode('.jpg', face_img)
                    img_data = buffer.tobytes()
                    
                    # Save to database
                    cursor.execute('''
                        INSERT INTO face_images (user_id, image_data) VALUES (?, ?)
                    ''', (user_id, img_data))
                    conn.commit()
                    
                    counter += 1
                    progress_bar.progress(counter / total_samples)
                    status_text.info(f"Capturing sample {counter}/{total_samples}")
                    
                    if counter >= total_samples:
                        break
                    
            # Display the frame
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            frame_display.image(img_rgb, caption="Capturing face data", use_column_width=True)
                
        cap.release()
        
        if counter >= total_samples:
            status_text.success(f"Dataset generated successfully with {counter} samples")
            return True
        else:
            status_text.error(f"Only captured {counter}/{total_samples} samples. Try again.")
            return False
    except Exception as e:
        st.error(f"Error generating dataset: {e}")
        return False
    finally:
        conn.close()

# Train Classifier Function
def train_classifier():
    status = st.empty()
    status.info("Training classifier...")
    
    face_samples = []
    face_ids = []
    
    # Connect to database to get user IDs and face images
    conn = get_db_connection()
    if not conn:
        status.error("Could not connect to database for training")
        return False
        
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM users")
        db_users = cursor.fetchall()
        
        # Exit if no users
        if not db_users:
            status.error("No users found in database. Add users first.")
            return False
        
        # Load all face samples for each user
        for user in db_users:
            user_id = user['id']
            name = user['name']
            
            status.info(f"Loading training data for {name}...")
            
            # Get all face images for this user
            cursor.execute("SELECT image_data FROM face_images WHERE user_id=?", (user_id,))
            face_images = cursor.fetchall()
            
            if not face_images:
                status.warning(f"No face images found for {name} (ID: {user_id})")
                continue
                
            for img_data in face_images:
                # Convert the binary data back to a face image
                nparr = np.frombuffer(img_data['image_data'], np.uint8)
                face_img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
                
                if face_img is not None:
                    face_samples.append(face_img)
                    face_ids.append(user_id)
        
        if not face_samples:
            status.error("No face samples found. Generate datasets first.")
            return False
        
        # Train the recognizer
        status.info(f"Training with {len(face_samples)} images...")
        recognizer.train(face_samples, np.array(face_ids))
        
        # Save trained model to database
        if save_classifier():
            status.success("Classifier trained successfully and saved to database!")
            return True
        else:
            status.error("Failed to save classifier to database.")
            return False
            
    except Exception as e:
        status.error(f"Error training classifier: {e}")
        return False
    finally:
        conn.close()

# Add user to database
def add_user_to_db():
    name = st.session_state.dataset_info['name']
    age = st.session_state.dataset_info['age']
    address = st.session_state.dataset_info['address']
    
    if not name or not age or not address:
        st.error("Please provide complete details before submitting.")
        return None
    
    conn = get_db_connection()
    if not conn:
        return None
        
    try:
        cursor = conn.cursor()
        
        # Insert the new user
        cursor.execute('''
            INSERT INTO users (name, age, address) 
            VALUES (?, ?, ?)
        ''', (name, age, address))
        conn.commit()
        
        # Get the ID of the newly inserted user
        user_id = cursor.lastrowid
        
        st.success(f"User {name} added to database with ID: {user_id}")
        return user_id
    except Exception as e:
        st.error(f"Error adding user to database: {e}")
        return None
    finally:
        conn.close()

# Update user in database
def update_user_in_db(user_id, name, age, address):
    conn = get_db_connection()
    if not conn:
        return False
        
    try:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET name = ?, age = ?, address = ? 
            WHERE id = ?
        ''', (name, age, address, user_id))
        conn.commit()
        
        if cursor.rowcount > 0:
            st.success(f"User {name} (ID: {user_id}) updated successfully")
            return True
        else:
            st.warning(f"No changes made to user {name} (ID: {user_id})")
            return False
    except Exception as e:
        st.error(f"Error updating user: {e}")
        return False
    finally:
        conn.close()

# Delete user from database and their face images
def delete_user_from_db(user_id):
    conn = get_db_connection()
    if not conn:
        return False
        
    try:
        cursor = conn.cursor()
        
        # Get user name for confirmation
        cursor.execute("SELECT name FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            st.error(f"User with ID {user_id} not found")
            return False
            
        user_name = user['name']
        
        # Delete user's face images first (because of foreign key constraint)
        cursor.execute("DELETE FROM face_images WHERE user_id = ?", (user_id,))
        
        # Delete user from database
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        
        st.success(f"User {user_name} (ID: {user_id}) deleted successfully along with all face data")
        return True
    except Exception as e:
        st.error(f"Error deleting user: {e}")
        return False
    finally:
        conn.close()

# Get user by ID
def get_user_by_id(user_id):
    conn = get_db_connection()
    if not conn:
        return None
        
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, age, address FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        return dict(user) if user else None
    except Exception as e:
        st.error(f"Error fetching user: {e}")
        return None
    finally:
        conn.close()

# Verify passkey for CRUD operations
def verify_passkey_for_crud():
    st.subheader("Authentication Required")
    st.warning("Please enter the passkey to access admin functions")
    
    passkey = st.text_input("Enter Admin Passkey", type="password", key="crud_passkey")
    
    if st.button("Verify Passkey"):
        if passkey == "securepass123":
            st.session_state.crud_operation_verified = True
            st.success("Passkey verified. You can now perform any operation.")
            st.experimental_rerun()
        else:
            st.error("Incorrect passkey. Access denied.")

# Initialize database on app start
init_database()
load_classifier()  # Try to load classifier from database

# Main App
st.title("Face Recognition System")

# Add some CSS for animations
st.markdown("""
<style>
@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}

.fadeIn {
    animation: fadeIn 1s ease-in-out;
}

@keyframes slideIn {
    from { transform: translateX(-100%); }
    to { transform: translateX(0); }
}

.slideIn {
    animation: slideIn 0.5s ease-in-out;
}

.stButton>button {
    background-color: #4CAF50;
    color: white;
    padding: 10px 20px;
    border: none;
    border-radius: 5px;
    cursor: pointer;
    transition: background-color 0.3s ease;
}

.stButton>button:hover {
    background-color: #45a049;
}

.stTextInput>div>div>input {
    padding: 10px;
    border-radius: 5px;
    border: 1px solid #ccc;
    transition: border-color 0.3s ease;
}

.stTextInput>div>div>input:focus {
    border-color: #4CAF50;
    outline: none;
}

.stProgress>div>div>div {
    background-color: #4CAF50;
}

.stAlert {
    padding: 10px;
    border-radius: 5px;
    margin-bottom: 10px;
}

.stAlert.success {
    background-color: #d4edda;
    color: #155724;
    border: 1px solid #c3e6cb;
}

.stAlert.error {
    background-color: #f8d7da;
    color: #721c24;
    border: 1px solid #f5c6cb;
}

.stAlert.warning {
    background-color: #fff3cd;
    color: #856404;
    border: 1px solid #ffeeba;
}

.stAlert.info {
    background-color: #d1ecf1;
    color: #0c5460;
    border: 1px solid #bee5eb;
}
</style>
""", unsafe_allow_html=True)

if not st.session_state.access_granted:
    option = st.radio("Choose Authentication Method", ["Face Recognition", "Passkey"])

    if option == "Face Recognition":
        if st.button("Detect Face"):
            with st.spinner("Detecting face..."):
                detect_face()

    elif option == "Passkey":
        passkey = st.text_input("Enter Passkey", type="password")

        if st.button("Submit Passkey"):
            if passkey == "securepass123":
                st.session_state.access_granted = True
                # Set authenticated user as Admin for passkey login
                st.session_state.authenticated_user = "Admin"
                # Set authentication method to passkey
                st.session_state.auth_method = "passkey"
                # Note: CRUD operations still need verification
                st.session_state.crud_operation_verified = False
                st.success("Access Granted via Passkey")
            else:
                st.session_state.passkey_attempts += 1
                st.error(f"Incorrect Passkey. Access Denied. ({st.session_state.passkey_attempts}/3 attempts)")

            if st.session_state.passkey_attempts >= 3:
                st.error("Too many failed attempts. Switching to face recognition.")
                detect_face()

if st.session_state.access_granted:
    st.title("Authorized User Dashboard")
    
    # Display authenticated user name in a container above the tabs
    user_info_col1, user_info_col2 = st.columns([3, 1])
    with user_info_col1:
        if st.session_state.authenticated_user:
            st.info(f"Welcome, {st.session_state.authenticated_user}!")
    
    with user_info_col2:
        if st.button("Log Out"):
            st.session_state.access_granted = False
            st.session_state.show_main_options = False
            st.session_state.operation_type = None
            st.session_state.crud_operation_verified = False
            st.session_state.selected_user_id = None
            st.session_state.authenticated_user = None
            st.session_state.auth_method = None
            st.experimental_rerun()
    
    # Check if this is passkey authentication and verification is still needed
    if st.session_state.auth_method == "passkey" and not st.session_state.crud_operation_verified:
        verify_passkey_for_crud()
    else:
        # User is verified (either by face or passkey+verification), show all tabs and operations
        tabs = st.tabs(["Add User", "Train System", "User Management"])
        
        with tabs[0]:
            st.header("Add New User")
            
            st.session_state.dataset_info['name'] = st.text_input("Name")
            st.session_state.dataset_info['age'] = st.text_input("Age")
            st.session_state.dataset_info['address'] = st.text_area("Address")

            if st.button("Add User to System"):
                with st.spinner("Adding user..."):
                    user_id = add_user_to_db()
                    if user_id:
                        if generate_dataset(user_id):
                            st.success(f"User {st.session_state.dataset_info['name']} added successfully.")
                            st.info("Remember to train the classifier after adding users.")
        
        with tabs[1]:
            st.header("Train Recognition System")
            if st.button("Train Classifier"):
                with st.spinner("Training classifier..."):
                    train_classifier()
        
        with tabs[2]:
            st.header("User Management")
            
            # Create subtabs for different operations
            user_tabs = st.tabs(["View Users", "Edit User", "Delete User"])
            
            with user_tabs[0]:
                if st.button("View Registered Users", key="view_users"):
                    conn = get_db_connection()
                    if conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT id, name, age, address FROM users")
                        users = cursor.fetchall()
                        
                        if users:
                            # Convert rows to list of dicts
                            user_list = [dict(row) for row in users]
                            
                            # Create a dataframe-like table
                            data = {
                                "ID": [user['id'] for user in user_list],
                                "Name": [user['name'] for user in user_list],
                                "Age": [user['age'] for user in user_list],
                                "Address": [user['address'] for user in user_list]
                            }
                            st.table(data)
                        else:
                            st.info("No users registered in the system.")
                        conn.close()
            
            with user_tabs[1]:
                st.subheader("Edit User Information")
                
                conn = get_db_connection()
                if conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id, name FROM users")
                    users = cursor.fetchall()
                    conn.close()
                    
                    if users:
                        user_options = [f"{user['id']}: {user['name']}" for user in users]
                        selected_user = st.selectbox("Select user to edit:", user_options)
                        
                        # Extract user ID from selection
                        user_id = int(selected_user.split(":")[0])
                        
                        # Get user data for editing
                        user = get_user_by_id(user_id)
                        
                        if user:
                            # Pre-fill form with user data
                            new_name = st.text_input("Name", value=user['name'], key="edit_name")
                            new_age = st.text_input("Age", value=user['age'], key="edit_age")
                            new_address = st.text_area("Address", value=user['address'], key="edit_address")
                            
                            if st.button("Update User"):
                                with st.spinner("Updating user..."):
                                    if update_user_in_db(user_id, new_name, new_age, new_address):
                                        st.success(f"User {new_name} updated successfully")
                        else:
                            st.error(f"User data not found")
                    else:
                        st.info("No users registered in the system.")
            
            with user_tabs[2]:
                st.subheader("Delete User")
                
                conn = get_db_connection()
                if conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id, name FROM users")
                    users = cursor.fetchall()
                    conn.close()
                    
                    if users:
                        user_options = [f"{user['id']}: {user['name']}" for user in users]
                        selected_user = st.selectbox("Select user to delete:", user_options, key="delete_user")
                        
                        # Extract user ID from selection
                        user_id = int(selected_user.split(":")[0])
                        
                        st.warning(f"Are you sure you want to delete this user? This will permanently remove the user and all associated face data.")
                        
                        if st.button("Confirm Delete"):
                            with st.spinner("Deleting user..."):
                                if delete_user_from_db(user_id):
                                    st.success("User deleted. You should retrain the classifier.")
                                    
                                    # Suggest retraining
                                    if st.button("Retrain Classifier Now"):
                                        with st.spinner("Retraining classifier..."):
                                            train_classifier()
                    else:
                        st.info("No users registered in the system.")


# ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

# import streamlit as st
# import cv2
# import numpy as np
# import mysql.connector
# from PIL import Image
# import os
# import smtplib
# from email.message import EmailMessage
# from datetime import datetime
# import shutil
# import time
# import uuid


# # Initialize session state variables
# if 'passkey_attempts' not in st.session_state:
#     st.session_state.passkey_attempts = 0

# if 'access_granted' not in st.session_state:
#     st.session_state.access_granted = False

# if 'show_main_options' not in st.session_state:
#     st.session_state.show_main_options = False

# if 'dataset_info' not in st.session_state:
#     st.session_state.dataset_info = {'name': '', 'age': '', 'address': ''}

# if 'crud_operation_verified' not in st.session_state:
#     st.session_state.crud_operation_verified = False

# if 'operation_type' not in st.session_state:
#     st.session_state.operation_type = None

# if 'selected_user_id' not in st.session_state:
#     st.session_state.selected_user_id = None

# if 'user_to_edit' not in st.session_state:
#     st.session_state.user_to_edit = {'id': None, 'name': '', 'age': '', 'address': ''}

# if 'authenticated_user' not in st.session_state:
#     st.session_state.authenticated_user = None

# if 'auth_method' not in st.session_state:
#     st.session_state.auth_method = None

# # Create data directory if it doesn't exist
# data_dir = "data"
# if not os.path.exists(data_dir):
#     os.makedirs(data_dir)

# # Load Haar Cascade for face detection
# cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
# faceCascade = cv2.CascadeClassifier(cascade_path)

# if faceCascade.empty():
#     st.error("Error: Haar Cascade XML file could not be loaded.")
#     st.stop()

# # Load LBPH Recognizer
# recognizer = cv2.face.LBPHFaceRecognizer_create()

# # Load classifier if it exists
# classifier_exists = False
# try:
#     recognizer.read("classifier.xml")
#     classifier_exists = True
# except Exception as e:
#     st.warning("Classifier not found. Train the model before detecting faces.")

# # Database connection function
# def get_db_connection():
#     try:
#         conn = mysql.connector.connect(
#             host="localhost",
#             user="root",
#             passwd="",
#             database="Authorized_users"
#         )
#         return conn
#     except Exception as e:
#         st.error(f"Database connection error: {e}")
#         return None

# # Initialize database if it doesn't exist
# def init_database():
#     try:
#         conn = mysql.connector.connect(
#             host="localhost",
#             user="root",
#             passwd=""
#         )
#         cursor = conn.cursor()
        
#         # Create database if it doesn't exist
#         cursor.execute("CREATE DATABASE IF NOT EXISTS Authorized_users")
#         cursor.execute("USE Authorized_users")
        
#         # Check if table exists
#         cursor.execute("SHOW TABLES LIKE 'my_table'")
#         table_exists = cursor.fetchone()
        
#         # Create table if it doesn't exist with explicit AUTO_INCREMENT definition
#         if not table_exists:
#             cursor.execute("""
#             CREATE TABLE my_table (
#                 id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
#                 name VARCHAR(255) NOT NULL,
#                 age VARCHAR(50),
#                 address TEXT
#             ) ENGINE=InnoDB AUTO_INCREMENT=1
#             """)
        
#         conn.commit()
#         return True
#     except Exception as e:
#         st.error(f"Database initialization error: {e}")
#         return False
#     finally:
#         if 'conn' in locals() and conn.is_connected():
#             cursor.close()
#             conn.close()

# # Email Alert Function
# def send_email_alert(person_name, confidence, img_path):
#     try:
#         email_sender = "samyak.1403@gmail.com"
#         email_password = "jpcngoqvqeapstnz"  # Consider using environment variables for this
#         email_receiver = "samyak.1403@gmail.com"

#         subject = "🔔 Face Detection Alert"
#         body = f"Person Detected: {person_name}\nConfidence Level: {confidence}%\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

#         msg = EmailMessage()
#         msg['From'] = email_sender
#         msg['To'] = email_receiver
#         msg['Subject'] = subject
#         msg.set_content(body)

#         with open(img_path, 'rb') as f:
#             img_data = f.read()
#             msg.add_attachment(img_data, maintype='image', subtype='jpeg', filename='detected_face.jpg')

#         with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
#             server.login(email_sender, email_password)
#             server.send_message(msg)

#         st.info(f"Email alert sent for {person_name}")
#         return True
#     except Exception as e:
#         st.error(f"Email sending error: {e}")
#         return False

# # Detect Face Function
# def detect_face():
#     if not classifier_exists:
#         st.error("Face recognition model not trained yet. Please add users and train classifier first.")
#         return False
    
#     cap = cv2.VideoCapture(0)
#     if not cap.isOpened():
#         st.error("Error: Cannot access the webcam. Check your camera permissions!")
#         return False

#     stframe = st.empty()
#     status_placeholder = st.empty()
#     start_time = datetime.now()
    
#     status_placeholder.info("Detecting face... Look at the camera")
    
#     # Track if we've found a valid face
#     face_detected = False
#     person_name = None
#     best_confidence = 0
#     user_found_in_db = False  # Track if the user exists in database

#     while (datetime.now() - start_time).seconds < 20:  # Maximum 20 seconds timeout
#         ret, img = cap.read()
#         if not ret:
#             status_placeholder.error("Failed to read frame from webcam.")
#             break

#         gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
#         faces = faceCascade.detectMultiScale(gray, 1.1, 5)

#         for (x, y, w, h) in faces:
#             cv2.rectangle(img, (x, y), (x+w, y+h), (255, 0, 0), 2)
            
#             face_roi = gray[y:y+h, x:x+w]
            
#             try:
#                 id, pred = recognizer.predict(face_roi)
#                 confidence = int(100 * (1 - pred / 300))
                
#                 conn = get_db_connection()
#                 if not conn:
#                     status_placeholder.error("Could not connect to database")
#                     continue
                    
#                 cursor = conn.cursor()
#                 cursor.execute(f"SELECT name FROM my_table WHERE id={id}")
#                 user_data = cursor.fetchone()
#                 cursor.close()
#                 conn.close()

#                 if user_data:
#                     current_name = user_data[0]
#                     cv2.putText(img, f"{current_name} ({confidence}%)", (x, y-10), 
#                                 cv2.FONT_HERSHEY_SIMPLEX, 0.9, (36, 255, 12), 2)
                    
#                     # Track the best confidence we've seen
#                     if confidence > best_confidence:
#                         best_confidence = confidence
#                         person_name = current_name
#                         user_found_in_db = True  # Mark that we found a valid user
                        
#                     # Only set face_detected if we exceed the threshold
#                     if confidence > 70:
#                         face_detected = True
#                 else:
#                     cv2.putText(img, f"Unknown ({confidence}%)", (x, y-10), 
#                                 cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
                    
#                     # Save unknown face and send alert after a few seconds
#                     if (datetime.now() - start_time).seconds > 5:
#                         img_path = os.path.join(data_dir, "unknown_" + datetime.now().strftime("%Y%m%d%H%M%S") + ".jpg")
#                         cv2.imwrite(img_path, img)
#                         send_email_alert("Unknown", confidence, img_path)
#                         status_placeholder.error("Unauthorized Person Detected. Alert Sent.")
#                         # Set user_found_in_db to False even if confidence is high
#                         user_found_in_db = False

#             except Exception as e:
#                 status_placeholder.error(f"Recognition Error: {e}")

#         # Convert color for display
#         img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
#         stframe.image(img_rgb, caption="Face Detection", use_column_width=True)
        
#         # Check if we've found a valid face with high confidence
#         if face_detected:
#             # Wait a bit longer to ensure we have a stable reading
#             if (datetime.now() - start_time).seconds > 3:
#                 break

#     cap.release()
    
#     # Only grant access if a valid face was detected AND the user exists in database
#     if face_detected and best_confidence > 70 and user_found_in_db:
#         st.session_state.access_granted = True
#         # Store the authenticated user's name
#         st.session_state.authenticated_user = person_name
#         # Set authentication method to face recognition
#         st.session_state.auth_method = "face"
#         # With face recognition, CRUD operations are pre-verified
#         st.session_state.crud_operation_verified = True
#         status_placeholder.success(f"Access Granted to {person_name} with {best_confidence}% confidence")
#         return True
#     else:
#         if best_confidence > 0:
#             if not user_found_in_db:
#                 status_placeholder.warning(f"Face detected but not found in database. Access denied.")
#             else:
#                 status_placeholder.warning(f"Face detected but confidence too low ({best_confidence}%). Access denied.")
#         else:
#             status_placeholder.warning("No recognized face detected. Access denied.")
#         return False
        
# # Dataset Generation Function
# def generate_dataset(user_id):
#     name = st.session_state.dataset_info['name']
    
#     # Create directory for user images
#     person_dir = os.path.join(data_dir, f"user_{user_id}")
#     if not os.path.exists(person_dir):
#         os.makedirs(person_dir)
    
#     cap = cv2.VideoCapture(0)
#     if not cap.isOpened():
#         st.error("Error: Cannot access the webcam. Check your camera permissions!")
#         return False
        
#     counter = 0
#     total_samples = 30
#     progress_bar = st.progress(0)
#     status_text = st.empty()
#     frame_display = st.empty()
    
#     status_text.info(f"Capturing face samples for {name}. Please look at the camera and move your head slightly.")
    
#     while counter < total_samples:
#         ret, img = cap.read()
#         if not ret:
#             st.error("Error capturing image from webcam.")
#             break
            
#         gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
#         faces = faceCascade.detectMultiScale(gray, 1.1, 5)
        
#         if len(faces) > 0:  # Only save if a face is detected
#             for (x, y, w, h) in faces:
#                 cv2.rectangle(img, (x, y), (x+w, y+h), (0, 255, 0), 2)
                
#                 # Save only the face region
#                 face_img = gray[y:y+h, x:x+w]
#                 img_path = os.path.join(person_dir, f"{counter}.jpg")
#                 cv2.imwrite(img_path, face_img)
                
#                 counter += 1
#                 progress_bar.progress(counter / total_samples)
#                 status_text.info(f"Capturing sample {counter}/{total_samples}")
                
#                 if counter >= total_samples:
#                     break
                
#         # Display the frame
#         img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
#         frame_display.image(img_rgb, caption="Capturing face data", use_column_width=True)
            
#     cap.release()
    
#     if counter >= total_samples:
#         status_text.success(f"Dataset generated successfully with {counter} samples")
#         return True
#     else:
#         status_text.error(f"Only captured {counter}/{total_samples} samples. Try again.")
#         return False

# # Train Classifier Function
# def train_classifier():
#     global classifier_exists  # Properly declare global variable
    
#     status = st.empty()
#     status.info("Training classifier...")
    
#     face_samples = []
#     face_ids = []
    
#     # Connect to database to get user IDs
#     conn = get_db_connection()
#     if not conn:
#         status.error("Could not connect to database for training")
#         return False
        
#     cursor = conn.cursor()
#     cursor.execute("SELECT id, name FROM my_table")
#     db_users = cursor.fetchall()
#     cursor.close()
#     conn.close()
    
#     # Exit if no users
#     if not db_users:
#         status.error("No users found in database. Add users first.")
#         return False
    
#     # Load all face samples
#     for user_id, name in db_users:
#         user_dir = os.path.join(data_dir, f"user_{user_id}")
#         if not os.path.exists(user_dir):
#             status.warning(f"No data directory found for {name} (ID: {user_id})")
#             continue
            
#         status.info(f"Loading training data for {name}...")
        
#         for img_file in os.listdir(user_dir):
#             if not img_file.endswith('.jpg'):
#                 continue
                
#             img_path = os.path.join(user_dir, img_file)
#             face_img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
            
#             if face_img is not None:
#                 face_samples.append(face_img)
#                 face_ids.append(user_id)
    
#     if not face_samples:
#         status.error("No face samples found. Generate datasets first.")
#         return False
    
#     # Train the recognizer
#     status.info(f"Training with {len(face_samples)} images...")
#     recognizer.train(face_samples, np.array(face_ids))
    
#     # Save trained model
#     recognizer.write("classifier.xml")
#     classifier_exists = True  # Set after successful training
#     status.success("Classifier trained successfully!")
#     return True

# # Add user to database
# def add_user_to_db():
#     name = st.session_state.dataset_info['name']
#     age = st.session_state.dataset_info['age']
#     address = st.session_state.dataset_info['address']
    
#     if not name or not age or not address:
#         st.error("Please provide complete details before submitting.")
#         return None
    
#     conn = get_db_connection()
#     if not conn:
#         return None
        
#     try:
#         cursor = conn.cursor()
        
#         # Find the smallest available ID (gap)
#         cursor.execute("SELECT MIN(t1.id + 1) AS next_id FROM my_table t1 LEFT JOIN my_table t2 ON t1.id + 1 = t2.id WHERE t2.id IS NULL")
#         next_id = cursor.fetchone()[0]
        
#         # If no gaps, use the next sequential ID
#         if next_id is None:
#             cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM my_table")
#             next_id = cursor.fetchone()[0]
        
#         # Insert the new user with the calculated ID
#         query = "INSERT INTO my_table (id, name, age, address) VALUES (%s, %s, %s, %s)"
#         values = (next_id, name, age, address)
#         cursor.execute(query, values)
#         conn.commit()
        
#         st.success(f"User {name} added to database with ID: {next_id}")
#         return next_id
#     except Exception as e:
#         st.error(f"Error adding user to database: {e}")
#         return None
#     finally:
#         if 'cursor' in locals():
#             cursor.close()
#         conn.close()


# # Update user in database
# def update_user_in_db(user_id, name, age, address):
#     conn = get_db_connection()
#     if not conn:
#         return False
        
#     try:
#         cursor = conn.cursor()
#         query = "UPDATE my_table SET name = %s, age = %s, address = %s WHERE id = %s"
#         values = (name, age, address, user_id)
#         cursor.execute(query, values)
#         conn.commit()
        
#         if cursor.rowcount > 0:
#             st.success(f"User {name} (ID: {user_id}) updated successfully")
#             return True
#         else:
#             st.warning(f"No changes made to user {name} (ID: {user_id})")
#             return False
#     except Exception as e:
#         st.error(f"Error updating user: {e}")
#         return False
#     finally:
#         if 'cursor' in locals():
#             cursor.close()
#         conn.close()


# # Delete user from database and remove their images
# def delete_user_from_db(user_id):
#     # First get user info for confirmation
#     conn = get_db_connection()
#     if not conn:
#         return False
        
#     try:
#         cursor = conn.cursor()
        
#         # Get user name for confirmation
#         cursor.execute("SELECT name FROM my_table WHERE id = %s", (user_id,))
#         user = cursor.fetchone()
        
#         if not user:
#             st.error(f"User with ID {user_id} not found")
#             return False
            
#         user_name = user[0]
        
#         # Delete user from database
#         cursor.execute("DELETE FROM my_table WHERE id = %s", (user_id,))
#         conn.commit()
        
#         # Reorganize IDs to fill the gap
#         cursor.execute("SET @count = 0")
#         cursor.execute("UPDATE my_table SET id = @count:= @count + 1 ORDER BY id")
#         cursor.execute("ALTER TABLE my_table AUTO_INCREMENT = 1")
#         conn.commit()
        
#         # Delete user's image directory
#         user_dir = os.path.join(data_dir, f"user_{user_id}")
#         if os.path.exists(user_dir):
#             shutil.rmtree(user_dir)
            
#         st.success(f"User {user_name} (ID: {user_id}) deleted successfully along with all face data")
#         return True
#     except Exception as e:
#         st.error(f"Error deleting user: {e}")
#         return False
#     finally:
#         if 'cursor' in locals():
#             cursor.close()
#         conn.close()


# # Get user by ID
# def get_user_by_id(user_id):
#     conn = get_db_connection()
#     if not conn:
#         return None
        
#     try:
#         cursor = conn.cursor(dictionary=True)
#         cursor.execute("SELECT id, name, age, address FROM my_table WHERE id = %s", (user_id,))
#         user = cursor.fetchone()
#         return user
#     except Exception as e:
#         st.error(f"Error fetching user: {e}")
#         return None
#     finally:
#         if 'cursor' in locals():
#             cursor.close()
#         conn.close()
# # Verify passkey for CRUD operations
# def verify_passkey_for_crud():
#     st.subheader("Authentication Required")
#     st.warning("Please enter the passkey to access admin functions")
    
#     passkey = st.text_input("Enter Admin Passkey", type="password", key="crud_passkey")
    
#     if st.button("Verify Passkey"):
#         if passkey == "securepass123":
#             st.session_state.crud_operation_verified = True
#             st.success("Passkey verified. You can now perform any operation.")
#             st.experimental_rerun()
#         else:
#             st.error("Incorrect passkey. Access denied.")

# # Initialize database on app start
# init_database()

# # Main App
# st.title("Face Recognition System")

# # Add some CSS for animations
# st.markdown("""
# <style>
# @keyframes fadeIn {
#     from { opacity: 0; }
#     to { opacity: 1; }
# }

# .fadeIn {
#     animation: fadeIn 1s ease-in-out;
# }

# @keyframes slideIn {
#     from { transform: translateX(-100%); }
#     to { transform: translateX(0); }
# }

# .slideIn {
#     animation: slideIn 0.5s ease-in-out;
# }

# .stButton>button {
#     background-color: #4CAF50;
#     color: white;
#     padding: 10px 20px;
#     border: none;
#     border-radius: 5px;
#     cursor: pointer;
#     transition: background-color 0.3s ease;
# }

# .stButton>button:hover {
#     background-color: #45a049;
# }

# .stTextInput>div>div>input {
#     padding: 10px;
#     border-radius: 5px;
#     border: 1px solid #ccc;
#     transition: border-color 0.3s ease;
# }

# .stTextInput>div>div>input:focus {
#     border-color: #4CAF50;
#     outline: none;
# }

# .stProgress>div>div>div {
#     background-color: #4CAF50;
# }

# .stAlert {
#     padding: 10px;
#     border-radius: 5px;
#     margin-bottom: 10px;
# }

# .stAlert.success {
#     background-color: #d4edda;
#     color: #155724;
#     border: 1px solid #c3e6cb;
# }

# .stAlert.error {
#     background-color: #f8d7da;
#     color: #721c24;
#     border: 1px solid #f5c6cb;
# }

# .stAlert.warning {
#     background-color: #fff3cd;
#     color: #856404;
#     border: 1px solid #ffeeba;
# }

# .stAlert.info {
#     background-color: #d1ecf1;
#     color: #0c5460;
#     border: 1px solid #bee5eb;
# }
# </style>
# """, unsafe_allow_html=True)

# if not st.session_state.access_granted:
#     option = st.radio("Choose Authentication Method", ["Face Recognition", "Passkey"])

#     if option == "Face Recognition":
#         if st.button("Detect Face"):
#             with st.spinner("Detecting face..."):
#                 detect_face()

#     elif option == "Passkey":
#         passkey = st.text_input("Enter Passkey", type="password")

#         if st.button("Submit Passkey"):
#             if passkey == "securepass123":
#                 st.session_state.access_granted = True
#                 # Set authenticated user as Admin for passkey login
#                 st.session_state.authenticated_user = "Admin"
#                 # Set authentication method to passkey
#                 st.session_state.auth_method = "passkey"
#                 # Note: CRUD operations still need verification
#                 st.session_state.crud_operation_verified = False
#                 st.success("Access Granted via Passkey")
#             else:
#                 st.session_state.passkey_attempts += 1
#                 st.error(f"Incorrect Passkey. Access Denied. ({st.session_state.passkey_attempts}/3 attempts)")

#             if st.session_state.passkey_attempts >= 3:
#                 st.error("Too many failed attempts. Switching to face recognition.")
#                 detect_face()

# if st.session_state.access_granted:
#     st.title("Authorized User Dashboard")
    
#     # Display authenticated user name in a container above the tabs
#     user_info_col1, user_info_col2 = st.columns([3, 1])
#     with user_info_col1:
#         if st.session_state.authenticated_user:
#             st.info(f"Welcome, {st.session_state.authenticated_user}!")
    
#     with user_info_col2:
#         if st.button("Log Out"):
#             st.session_state.access_granted = False
#             st.session_state.show_main_options = False
#             st.session_state.operation_type = None
#             st.session_state.crud_operation_verified = False
#             st.session_state.selected_user_id = None
#             st.session_state.authenticated_user = None
#             st.session_state.auth_method = None
#             st.experimental_rerun()
    
#     # Check if this is passkey authentication and verification is still needed
#     if st.session_state.auth_method == "passkey" and not st.session_state.crud_operation_verified:
#         verify_passkey_for_crud()
#     else:
#         # User is verified (either by face or passkey+verification), show all tabs and operations
#         tabs = st.tabs(["Add User", "Train System", "User Management"])
        
#         with tabs[0]:
#             st.header("Add New User")
            
#             st.session_state.dataset_info['name'] = st.text_input("Name")
#             st.session_state.dataset_info['age'] = st.text_input("Age")
#             st.session_state.dataset_info['address'] = st.text_area("Address")

#             if st.button("Add User to System"):
#                 with st.spinner("Adding user..."):
#                     user_id = add_user_to_db()
#                     if user_id:
#                         if generate_dataset(user_id):
#                             st.success(f"User {st.session_state.dataset_info['name']} added successfully.")
#                             st.info("Remember to train the classifier after adding users.")
        
#         with tabs[1]:
#             st.header("Train Recognition System")
#             if st.button("Train Classifier"):
#                 with st.spinner("Training classifier..."):
#                     train_classifier()
        
#         with tabs[2]:
#             st.header("User Management")
            
#             # Create subtabs for different operations
#             user_tabs = st.tabs(["View Users", "Edit User", "Delete User"])
            
#             with user_tabs[0]:
#                 if st.button("View Registered Users", key="view_users"):
#                     conn = get_db_connection()
#                     if conn:
#                         cursor = conn.cursor()
#                         cursor.execute("SELECT id, name, age, address FROM my_table")
#                         users = cursor.fetchall()
#                         cursor.close()
#                         conn.close()
                        
#                         if users:
#                             user_df = np.array(users)
#                             st.table({
#                                 "ID": user_df[:, 0],
#                                 "Name": user_df[:, 1],
#                                 "Age": user_df[:, 2],
#                                 "Address": user_df[:, 3]
#                             })
#                         else:
#                             st.info("No users registered in the system.")
            
#             with user_tabs[1]:
#                 st.subheader("Edit User Information")
                
#                 conn = get_db_connection()
#                 if conn:
#                     cursor = conn.cursor()
#                     cursor.execute("SELECT id, name FROM my_table")
#                     users = cursor.fetchall()
#                     cursor.close()
#                     conn.close()
                    
#                     if users:
#                         user_options = [f"{user[0]}: {user[1]}" for user in users]
#                         selected_user = st.selectbox("Select user to edit:", user_options)
                        
#                         # Extract user ID from selection
#                         user_id = int(selected_user.split(":")[0])
                        
#                         # Get user data for editing
#                         user = get_user_by_id(user_id)
                        
#                         if user:
#                             # Pre-fill form with user data
#                             new_name = st.text_input("Name", value=user['name'], key="edit_name")
#                             new_age = st.text_input("Age", value=user['age'], key="edit_age")
#                             new_address = st.text_area("Address", value=user['address'], key="edit_address")
                            
#                             if st.button("Update User"):
#                                 with st.spinner("Updating user..."):
#                                     if update_user_in_db(user_id, new_name, new_age, new_address):
#                                         st.success(f"User {new_name} updated successfully")
#                         else:
#                             st.error(f"User data not found")
#                     else:
#                         st.info("No users registered in the system.")
            
#             with user_tabs[2]:
#                 st.subheader("Delete User")
                
#                 conn = get_db_connection()
#                 if conn:
#                     cursor = conn.cursor()
#                     cursor.execute("SELECT id, name FROM my_table")
#                     users = cursor.fetchall()
#                     cursor.close()
#                     conn.close()
                    
#                     if users:
#                         user_options = [f"{user[0]}: {user[1]}" for user in users]
#                         selected_user = st.selectbox("Select user to delete:", user_options, key="delete_user")
                        
#                         # Extract user ID from selection
#                         user_id = int(selected_user.split(":")[0])
                        
#                         st.warning(f"Are you sure you want to delete this user? This will permanently remove the user and all associated face data.")
                        
#                         if st.button("Confirm Delete"):
#                             with st.spinner("Deleting user..."):
#                                 if delete_user_from_db(user_id):
#                                     st.success("User deleted. You should retrain the classifier.")
                                    
#                                     # Suggest retraining
#                                     if st.button("Retrain Classifier Now"):
#                                         with st.spinner("Retraining classifier..."):
#                                             train_classifier()
#                     else:
#                         st.info("No users registered in the system.")
