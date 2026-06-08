#!/usr/bin/env bash
# misc/spinner.sh — Simple CLI spinner for long-running steps
# Usage: source misc/spinner.sh; spin "Installing…" & PID=$!; sleep 5; kill $PID; wait $PID 2>/dev/null

spin() {
    local msg="${1:-Working…}"
    local delay=0.12
    local spinstr='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    local i=0
    while true; do
        c="${spinstr:$((i % ${#spinstr})):1}"
        printf "\r  %s  %s " "$c" "$msg"
        sleep "$delay"
        (( i++ ))
    done
}

spin "$@"
