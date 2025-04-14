# app.py
from flask import Flask, render_template, Response, request, redirect, url_for, flash, session
import cv2
import numpy as np
import sqlite3
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from datetime import datetime
import base64
import time

app = Flask(__name__)
app.secret_key = "facial_detection_secret_key"
app.config['UPLOAD_FOLDER'] = 'static/faces'
app.config['ADMIN_PASSWORD'] = 'admin123'  # Simple password for admin access

# Email configuration
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
EMAIL_ADDRESS = 'samyak.1403@gmail.com'  # Fixed email address (removed duplicate @gmail)
EMAIL_PASSWORD = 'jpcngoqvqeapstnz'  # Replace with your app password
RECEIVER_EMAIL = 'samyak.1403@gmail.com'  # Replace with admin email

# Database setup
def init_db():
    conn = sqlite3.connect('facial_recognition.db')
    cursor = conn.cursor()
    
    # Users table for storing authorized users
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        image_path TEXT NOT NULL,
        access_level TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Access logs table for tracking all access attempts
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS access_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        status TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    conn.commit()
    conn.close()

# Initialize the database
init_db()

# Function to save face to the database
def save_face(name, email, image_data, access_level):
    try:
        # Create directory if it doesn't exist
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
        
        # Save image to file
        timestamp = int(time.time())
        filename = f"{name}_{timestamp}.jpg"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Convert base64 image to file
        image_data_clean = image_data.split(',')[1] if ',' in image_data else image_data
        image_binary = base64.b64decode(image_data_clean)
        with open(filepath, 'wb') as f:
            f.write(image_binary)
        
        # Store in database
        conn = sqlite3.connect('facial_recognition.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (name, email, image_path, access_level) VALUES (?, ?, ?, ?)",
            (name, email, filepath, access_level)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error saving face: {e}")
        return False

# Function to get all users
def get_all_users():
    conn = sqlite3.connect('facial_recognition.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users ORDER BY created_at DESC")
    users = cursor.fetchall()
    conn.close()
    return users

# Function to get a user by ID
def get_user_by_id(user_id):
    conn = sqlite3.connect('facial_recognition.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

# Function to update user
def update_user(user_id, name, email, access_level, image_data=None):
    try:
        conn = sqlite3.connect('facial_recognition.db')
        cursor = conn.cursor()
        
        if image_data and ',' in image_data:  # Check if it's a base64 image
            # Update with new image
            user = get_user_by_id(user_id)
            
            # Remove old image if it exists
            if user and os.path.exists(user['image_path']):
                os.remove(user['image_path'])
            
            # Save new image
            timestamp = int(time.time())
            filename = f"{name}_{timestamp}.jpg"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            # Convert base64 image to file
            image_data_clean = image_data.split(',')[1]
            image_binary = base64.b64decode(image_data_clean)
            with open(filepath, 'wb') as f:
                f.write(image_binary)
            
            cursor.execute(
                "UPDATE users SET name = ?, email = ?, image_path = ?, access_level = ? WHERE id = ?",
                (name, email, filepath, access_level, user_id)
            )
        else:
            # Update without changing image
            cursor.execute(
                "UPDATE users SET name = ?, email = ?, access_level = ? WHERE id = ?",
                (name, email, access_level, user_id)
            )
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error updating user: {e}")
        return False

# Function to delete user
def delete_user(user_id):
    try:
        user = get_user_by_id(user_id)
        if user:
            # Delete image file
            if os.path.exists(user['image_path']):
                os.remove(user['image_path'])
            
            # Delete from database
            conn = sqlite3.connect('facial_recognition.db')
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            conn.close()
            return True
        return False
    except Exception as e:
        print(f"Error deleting user: {e}")
        return False

# Function to log access attempts
def log_access(user_id, status):
    try:
        conn = sqlite3.connect('facial_recognition.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO access_logs (user_id, status) VALUES (?, ?)",
            (user_id, status)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error logging access: {e}")
        return False

# Function to get access logs
def get_access_logs():
    conn = sqlite3.connect('facial_recognition.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.status, a.timestamp, u.name, u.email
        FROM access_logs a
        LEFT JOIN users u ON a.user_id = u.id
        ORDER BY a.timestamp DESC
    """)
    logs = cursor.fetchall()
    conn.close()
    return logs

# Function to send email alert with image
def send_email_alert(image_data=None):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = RECEIVER_EMAIL
        msg['Subject'] = 'ALERT: Unauthorized Access Attempt'
        
        body = f"""
        <html>
        <body>
        <h2>Unauthorized Access Attempt</h2>
        <p>An unauthorized person attempted to access the system at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p>Please check the security cameras and access logs.</p>
        </body>
        </html>
        """
        msg.attach(MIMEText(body, 'html'))
        
        # Attach the image if provided
        if image_data and ',' in image_data:
            # Convert base64 to image
            image_data_clean = image_data.split(',')[1]
            image_binary = base64.b64decode(image_data_clean)
            
            # Create temporary file for the image
            timestamp = int(time.time())
            temp_filename = f"unauthorized_{timestamp}.jpg"
            temp_filepath = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)
            
            # Ensure directory exists
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])
                
            # Save the image temporarily
            with open(temp_filepath, 'wb') as f:
                f.write(image_binary)
            
            # Attach the image to the email
            with open(temp_filepath, 'rb') as f:
                img_data = f.read()
                image = MIMEImage(img_data)
                image.add_header('Content-Disposition', 'attachment', filename=temp_filename)
                msg.attach(image)
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        # Delete temporary file if it was created
        if image_data and os.path.exists(temp_filepath):
            os.remove(temp_filepath)
            
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

# Routes
@app.route('/')
def index():
    return render_template('index.html')

# Face detection stream
def gen_frames():
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    camera = cv2.VideoCapture(0)  # Try 0 first, if that doesn't work try 1
    
    if not camera.isOpened():
        camera = cv2.VideoCapture(0)  # Try alternate camera index
        
    while True:
        success, frame = camera.read()
        if not success:
            break
            
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.3, 5)
        
        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)
            
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/detect_face', methods=['POST'])
def detect_face():
    if request.method == 'POST':
        # Get the captured image
        image_data = request.form.get('image_data')
        
        if not image_data:
            flash('No image captured', 'error')
            return redirect(url_for('index'))
        
        # Process the image for face recognition
        try:
            # Convert base64 image to OpenCV format
            image_data_binary = base64.b64decode(image_data.split(',')[1])
            nparr = np.frombuffer(image_data_binary, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            # Load face cascade
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            
            # Convert to grayscale for face detection
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.3, 5)
            
            if len(faces) == 0:
                flash('No face detected in the image', 'error')
                return redirect(url_for('index'))
            
            # Extract face and compare with database
            face_found = False
            user_id = None
            user_name = None
            
            # Get all users from database
            users = get_all_users()
            
            for (x, y, w, h) in faces:
                face_img = gray[y:y+h, x:x+w]
                
                # Simple comparison (in real-world, use more advanced face recognition)
                for user in users:
                    stored_img_path = user['image_path']
                    if os.path.exists(stored_img_path):
                        stored_img = cv2.imread(stored_img_path, cv2.IMREAD_GRAYSCALE)
                        if stored_img is not None:  # Check if image loaded correctly
                            stored_img = cv2.resize(stored_img, (w, h))
                            
                            # Using a simple similarity measure
                            diff = cv2.absdiff(face_img, stored_img)
                            similarity = 100 - (np.sum(diff) / diff.size / 2.55)
                            
                            # Threshold for recognition (adjust as needed)
                            if similarity > 50:  # Arbitrary threshold
                                face_found = True
                                user_id = user['id']
                                user_name = user['name']
                                break
                
                if face_found:
                    break
            
            if face_found:
                # Log authorized access
                log_access(user_id, "Authorized")
                
                # Set user as authorized in session
                session['authorized_user_id'] = user_id
                session['authorized_user_name'] = user_name
                session['admin_logged_in'] = True  # Automatically log in to admin dashboard
                
                flash(f'Welcome, {user_name}! Access granted.', 'success')
                return redirect(url_for('admin_dashboard'))  # Redirect to admin dashboard on success
            else:
                # Log unauthorized access
                log_access(None, "Unauthorized")
                
                # Send email alert with the captured image
                send_email_alert(image_data)
                
                flash('Access denied: Face not recognized', 'error')
                return redirect(url_for('index'))
            
        except Exception as e:
            flash(f'Error processing image: {str(e)}', 'error')
            return redirect(url_for('index'))
    
    return redirect(url_for('index'))

# Admin Authentication
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        
        if password == app.config['ADMIN_PASSWORD']:
            session['admin_logged_in'] = True
            flash('Login successful', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid password', 'error')
    
    return render_template('admin_login.html')

@app.route('/admin_logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('authorized_user_id', None)
    session.pop('authorized_user_name', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))

# CRUD Operations
@app.route('/admin')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    users = get_all_users()
    logs = get_access_logs()
    return render_template('admin.html', users=users, logs=logs)

@app.route('/add_user', methods=['GET', 'POST'])
def add_user():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        access_level = request.form.get('access_level')
        image_data = request.form.get('image_data')
        
        if not all([name, email, access_level, image_data]):
            flash('All fields are required', 'error')
            return redirect(url_for('add_user'))
        
        success = save_face(name, email, image_data, access_level)
        
        if success:
            flash('User added successfully', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Error adding user', 'error')
    
    return render_template('add_user.html')

@app.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    user = get_user_by_id(user_id)
    
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        access_level = request.form.get('access_level')
        image_data = request.form.get('image_data')
        
        if not all([name, email, access_level]):
            flash('Name, email, and access level are required', 'error')
            return redirect(url_for('edit_user', user_id=user_id))
        
        success = update_user(user_id, name, email, access_level, image_data)
        
        if success:
            flash('User updated successfully', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Error updating user', 'error')
    
    return render_template('edit_user.html', user=user)

@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user_route(user_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    success = delete_user(user_id)
    
    if success:
        flash('User deleted successfully', 'success')
    else:
        flash('Error deleting user', 'error')
    
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(debug=True)