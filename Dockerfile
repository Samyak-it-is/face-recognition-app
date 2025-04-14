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
