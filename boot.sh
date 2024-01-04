#!/usr/bin/env bash

mkdir ./run 2> /dev/null

nodeos_version=$(nodeos --version 2>/dev/null)
if [ $? -ne 0 ]; then
    echo "Error: Unable to get nodeos version. Exiting."
    exit 1
fi

echo "Booting up the chain and saving deep-mind logs to deep-mind-${nodeos_version}.dmlog ..."
sleep 3

python3 ./python/boot.py \
    --cleos=cleos \
    --dmlog-path=./run/deep-mind-${nodeos_version}.dmlog \
    --actionlog-path=./run/deep-mind-${nodeos_version}.expected.jsonl \
    --accounts-path=./boot/accounts.json \
    --genesis-path=./boot/genesis.json \
    --nodeos=nodeos \
    --keosd=keosd \
    --user-limit=15 \
    --producer-limit=1 \
    --producer-sync-delay=5 \
    --contracts-dir=./system-contracts-3.1 \
    -w -a -k

if [ $? -eq 0 ]; then
    echo "Logs successfully generated in ./run directory"
fi
