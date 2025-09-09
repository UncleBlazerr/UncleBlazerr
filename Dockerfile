FROM python:3.10-alpine

WORKDIR /app

COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy all necessary directories
COPY ./scripts /app/scripts
COPY ./components /app/components
COPY ./almosthomers /app/almosthomers
COPY ./assets /app/assets

# Ensure data directory exists
RUN mkdir -p /app/data

# Set working directory to scripts
WORKDIR /app/scripts

EXPOSE 5000

CMD ["python3", "almosthomers.py"]
