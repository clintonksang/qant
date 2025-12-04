# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required for TA-Lib and other packages
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    wget \
    tar \
    autoconf \
    automake \
    libtool \
    && rm -rf /var/lib/apt/lists/*

# Install TA-Lib C library (required for the Python wrapper)
RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar -xvzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib && \
    ARCH=$(uname -m) && \
    if [ "$ARCH" = "aarch64" ]; then \
        BUILD_TYPE="aarch64-unknown-linux-gnu"; \
    elif [ "$ARCH" = "x86_64" ]; then \
        BUILD_TYPE="x86_64-unknown-linux-gnu"; \
    else \
        BUILD_TYPE="unknown-linux-gnu"; \
    fi && \
    ./configure --prefix=/usr --build=$BUILD_TYPE && \
    make && \
    make install && \
    cd .. && \
    rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

# Copy the requirements file into the container
COPY requirements.txt .

# Install Python dependencies
# Note: We might need to upgrade pip first
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Create necessary directories if they don't exist
RUN mkdir -p data assets templates static

# Expose port 5001 for the Flask app
EXPOSE 5001

# Define environment variable
ENV FLASK_APP=web_interface.py

# Run web_interface.py when the container launches
CMD ["python", "web_interface.py"]


