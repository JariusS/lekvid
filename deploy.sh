#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "   Deploying Antigravity Liquidity Sweep Bot via Docker"
echo "=========================================================="

if [ ! -f ".env" ]; then
    echo "⚠️ .env file not found! Copying from .env.example..."
    cp .env.example .env
    echo "❗ Please configure .env before starting container."
fi

mkdir -p data

echo "🔨 Building Docker image..."
docker compose build

echo "🚀 Starting container..."
docker compose up -d

echo "📊 Checking container status..."
docker compose ps

echo "📋 Following logs (Ctrl+C to exit)..."
docker compose logs -f
