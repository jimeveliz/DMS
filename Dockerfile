FROM python:3.11-slim

# Ensure Python output is unbuffered and no .pyc files are written
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy only required application files to avoid copying a local 'fastapi/' dir
COPY main.py seed_mongo.py ./
COPY static ./static

# Expose the application port
EXPOSE 8000

# Run as a non-root user (best practice)
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Start the FastAPI app with Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

