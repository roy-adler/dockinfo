FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir flask docker

# Copy the service script
COPY main.py /app/main.py

# Expose port
EXPOSE 8080

# Run the service
CMD ["python", "/app/main.py"]

