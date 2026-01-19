FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Create data directory for token storage
RUN mkdir -p /app/data && chmod 777 /app/data

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app.py .

# Expose port
EXPOSE 5000

# Run with gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "30", "app:app"]
