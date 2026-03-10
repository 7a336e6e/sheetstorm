#!/usr/bin/env bash
# SheetStorm MCP Bridge — automated setup script
# Usage: cd mcp-bridge && bash setup.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== SheetStorm MCP Bridge Setup ==="
echo ""

# 1. Detect Python
PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" &>/dev/null; then
        version=$("$candidate" --version 2>&1 | grep -oP '\d+\.\d+')
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [[ "$major" -ge 3 && "$minor" -ge 11 ]]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    echo "ERROR: Python 3.11+ is required but not found."
    echo "Install Python from https://python.org or via your package manager."
    exit 1
fi

echo "Using Python: $($PYTHON --version) at $(command -v $PYTHON)"

# 2. Create venv
if [[ ! -d .venv ]]; then
    echo "Creating virtual environment..."
    "$PYTHON" -m venv .venv
else
    echo "Virtual environment already exists."
fi

# 3. Install package + deps
echo "Installing sheetstorm-mcp-bridge and dependencies..."
.venv/bin/pip install --upgrade pip >/dev/null 2>&1
.venv/bin/pip install -e . 2>&1 | tail -5

# 4. Verify
echo ""
echo "Verifying installation..."
.venv/bin/python -c "
from sheetstorm_bridge.server import mcp
print(f'  Package: OK (server name: {mcp.name})')
" 2>&1

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Python path for Claude Desktop config:"
echo "  $(cd "$SCRIPT_DIR" && pwd)/.venv/bin/python"
echo ""

# 5. .env setup
if [[ ! -f .env ]]; then
    echo "No .env file found. Creating from .env.example..."
    cp .env.example .env
    echo "  Edit .env with your SheetStorm credentials before using."
else
    echo ".env file already exists."
fi

echo ""
echo "Next steps:"
echo "  1. Edit .env with your SheetStorm URL and credentials"
echo "  2. Test:    .venv/bin/python -m sheetstorm_bridge"
echo "  3. Add to Claude Desktop config (see README.md)"
