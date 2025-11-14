# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code and necessary data
COPY atlantico_server/ ./atlantico_server
COPY server.py ./
COPY batch-config/ ./batch-config/

# Command to run the application
CMD ["python", "server.py"]
