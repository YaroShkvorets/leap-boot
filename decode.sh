#!/usr/bin/env bash

nodeos_version=$(nodeos --version 2>/dev/null)
if [ $? -ne 0 ]; then
    echo "Error: Unable to get nodeos version. Exiting."
    exit 1
fi

echo "Decoding deep-mind-${nodeos_version}.dmlog to deep-mind-${nodeos_version}.dmlog.json ..."

cd decode

go run ./decode.go ../run/deep-mind-${nodeos_version}.dmlog ../run/deep-mind-${nodeos_version}.dmlog.json

cd ..