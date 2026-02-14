#!/bin/bash
# Helper script to generate SSL certificates for SpatialVCS

# Check if mkcert is installed
if ! command -v mkcert &> /dev/null
then
    echo "❌ mkcert is not installed."
    echo "-> Please install it first:"
    echo "   macOS: brew install mkcert nss"
    echo "   Windows: choco install mkcert"
    exit 1
fi

echo "🔐 Generating SSL Certificates..."

# Install Root CA
mkcert -install

# Detect Local IP (works on macOS/Linux)
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "100.104.16.42")
# Fallback for Linux if ipconfig not found (not robust but okay for helper)
if [ "$LOCAL_IP" == "" ]; then
    LOCAL_IP="127.0.0.1"
fi

echo "Detected Local IP: $LOCAL_IP"
echo "Generating key.pem and cert.pem..."

# Generate Certs
mkcert -key-file key.pem -cert-file cert.pem localhost 127.0.0.1 ::1 $LOCAL_IP 100.104.16.42

echo ""
echo "✅ Certificates Generated:"
echo "   - key.pem"
echo "   - cert.pem"
echo ""
echo "🚀 Now you can run the backend and frontend!"
