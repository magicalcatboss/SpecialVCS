#!/bin/bash
# One-Click Setup Script for SpatialVCS (macOS .command)

# Get directory of this script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# Go to project root (assuming script is in root)
cd "$DIR"

echo "======================================"
echo "🚀 SpatialVCS One-Click Setup"
echo "======================================"

# 1. Check/Install mkcert
if ! command -v mkcert &> /dev/null; then
    echo "📦 Installing mkcert (requires Homebrew)..."
    if command -v brew &> /dev/null; then
        brew install mkcert nss
    else
        echo "❌ Homebrew not found. Please install Homebrew first: https://brew.sh/"
        exit 1
    fi
else
    echo "✅ mkcert found."
fi

# 2. Setup Certificates
echo "🔐 Generating SSL Certificates..."
chmod +x scripts/setup_ssl.sh
./scripts/setup_ssl.sh

# 3. Setup Python Backend
echo "🐍 Setting up Python Environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "   Created virtual environment."
fi
source .venv/bin/activate
echo "   Installing Backend Dependencies..."
pip install -r requirements.txt

# 4. Setup Frontend
echo "⚛️ Setting up Frontend..."
cd frontend
if [ ! -d "node_modules" ]; then
    echo "   Installing Node Modules (may take a while)..."
    npm install
else
    echo "✅ Node Modules already installed."
fi
cd ..

echo ""
echo "======================================"
echo "✅ SETUP COMPLETE!"
echo "You can now run 'start_app.command' to launch the system."
echo "======================================"
read -p "Press Enter to exit..."
