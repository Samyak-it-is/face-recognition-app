# Use a lightweight Python image
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Expose the port
EXPOSE 10000

# Run with gunicorn
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000"]
