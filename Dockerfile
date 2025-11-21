FROM python:3.11-slim

# Installing system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copying and installing dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copying the application
COPY . /app

# Creating a user and directories
RUN useradd -m -u 1000 botuser \
    && mkdir -p /app/logs /app/data \
    && chown -R botuser:botuser /app

USER botuser

# Expose port for monitoring
EXPOSE 9090

# Run the bot (database tables are created automatically via SQLAlchemy)
CMD ["python", "run.py"]