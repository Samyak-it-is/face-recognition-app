# Use the official Python image from the Docker Hub
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory inside the container
WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy the entire project into the container
COPY . .

# Expose the port gunicorn will listen on
EXPOSE 10000

# Command to run the app using gunicorn
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000"]
