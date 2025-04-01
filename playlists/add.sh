#!/bin/bash

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <filename> <text>"
    exit 1
fi

FILENAME="$1"
TEXT="$2"

for dir in *; do
    if [ -d "$dir" ]; then
        echo "$TEXT" >> "$dir/$FILENAME"
    fi
done

echo "Text added to all directories."
