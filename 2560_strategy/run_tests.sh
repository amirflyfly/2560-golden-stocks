#!/bin/bash
set -e

echo "🧪 Running tests..."

python -m pytest tests/ -v --tb=short

echo "✅ All tests passed!"
