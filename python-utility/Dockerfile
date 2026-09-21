FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Create data directory for token storage
RUN mkdir -p /app/data && chmod 777 /app/data

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application. Every module the service imports must be listed here — a
# missing one only surfaces as an ImportError at container start.
COPY app.py tv_local.py weather_store.py .

# Expose port
EXPOSE 5000

# Run with gunicorn for production
# A launch can legitimately take a while: locating a display that moved to a
# new DHCP address, waiting for its network stack after the routine powered
# it on, then retrying the launch. That worst case runs to roughly a minute,
# so a 30s worker timeout would kill exactly the request discovery exists to
# rescue.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:app"]
