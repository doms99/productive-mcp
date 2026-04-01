#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Install Productive MCP from a GitHub repository using pip.

Usage:
  ./install.sh [--repo-url URL] [--ref REF] [--user]

Options:
  --repo-url URL   Git repository URL (default: $PRODUCTIVE_MCP_REPO_URL)
  --ref REF        Git ref: branch/tag/commit (default: $PRODUCTIVE_MCP_REF or main)
  --user           Install into the current user site-packages
  -h, --help       Show this help message

Environment:
  PRODUCTIVE_MCP_REPO_URL  Default Git repository URL
  PRODUCTIVE_MCP_REF       Default Git ref

Examples:
  ./install.sh --ref main
  ./install.sh --repo-url https://github.com/doms99/productive-mcp.git --ref main
  PRODUCTIVE_MCP_REPO_URL=https://github.com/doms99/productive-mcp.git ./install.sh
EOF
}

REPO_URL="${PRODUCTIVE_MCP_REPO_URL:-https://github.com/doms99/productive-mcp.git}"
REF="${PRODUCTIVE_MCP_REF:-main}"
PIP_USER_FLAG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-url)
      if [[ $# -lt 2 ]]; then
        echo "Error: --repo-url requires a value." >&2
        usage
        exit 1
      fi
      REPO_URL="$2"
      shift 2
      ;;
    --ref)
      if [[ $# -lt 2 ]]; then
        echo "Error: --ref requires a value." >&2
        usage
        exit 1
      fi
      REF="$2"
      shift 2
      ;;
    --user)
      PIP_USER_FLAG="--user"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown argument '$1'." >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$REPO_URL" ]]; then
  echo "Error: repository URL is required." >&2
  echo "Pass --repo-url or set PRODUCTIVE_MCP_REPO_URL." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required but not found." >&2
  exit 1
fi

echo "Installing productive-mcp from:"
echo "  repo: $REPO_URL"
echo "  ref:  $REF"

python3 -m pip install --upgrade $PIP_USER_FLAG "git+${REPO_URL}@${REF}"

echo
echo "Installed. Verify with:"
echo "  productive-mcp --help"
echo "  productive-mcp-server --help"
