#!/bin/zsh
cd "$(dirname "$0")"
source .venv-app/bin/activate
exec python app_main.py
