FROM python:3.11-slim

# Installing system dependencies including gosu for user switching
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    gosu \
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

# Copy and setup entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Expose port for monitoring
EXPOSE 9090

# Use entrypoint to fix permissions before running as botuser
ENTRYPOINT ["docker-entrypoint.sh"]

# Run the bot (database tables are created automatically via SQLAlchemy)
CMD ["python", "run.py"]