#!/usr/bin/env bash

nodeos_version=$(nodeos --version 2>/dev/null)
if [ $? -ne 0 ]; then
    echo "Error: Unable to get nodeos version. Exiting."
    exit 1
fi

echo "Validating deep-mind-${nodeos_version}.dmlog.json against deep-mind-${nodeos_version}.expected.jsonl ..."
sleep 1

python3 ./python/compare.py ./run/deep-mind-${nodeos_version}.expected.jsonl ./run/deep-mind-${nodeos_version}.dmlog.json

