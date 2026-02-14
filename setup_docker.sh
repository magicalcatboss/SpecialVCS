#!/bin/bash

echo "🐳 Setting up SpatialVCS Docker Environment..."

# 1. Check for .env
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "Creating .env from example..."
        cp .env.example .env
        echo "⚠️  PLEASE EDIT .env AND ADD YOUR GEMINI_API_KEY!"
        open .env
    else
        echo "❌ .env.example not found!"
        exit 1
    fi
fi

# 2. Check for SSL Certs
if [ ! -f key.pem ] || [ ! -f cert.pem ]; then
    echo "🔐 Generating Self-Signed SSL Certificates..."
    openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/C=US/ST=State/L=City/O=SpatialVCS/CN=localhost"
    echo "✅ Certificates generated."
else
    echo "✅ SSL Certificates found."
fi

# 3. Build and Run
echo "🚀 Building and Starting Docker Containers..."
docker-compose up --build
