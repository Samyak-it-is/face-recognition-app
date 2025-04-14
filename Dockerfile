<<<<<<< HEAD
# Use official Python slim image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libgl1 \
    libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy rest of the app
COPY . .

# Expose port (optional for documentation)
EXPOSE 10000

# Start the app with gunicorn
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000"]
=======
# Use the official Python image from the Docker Hub
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install the required dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Expose the port the app will run on
EXPOSE 5000

# Set the environment variable to prevent Python from writing pyc files to disk
ENV PYTHONDONTWRITEBYTECODE 1

# Set the environment variable for the Flask app
ENV FLASK_APP=app.py

# Set the Flask app to run in production mode
ENV FLASK_ENV=production

# Run the Flask application
CMD ["flask", "run", "--host=0.0.0.0"]
>>>>>>> 638d250f61c8c28e33b49f5ffaefcd9cd7d1a2d9
