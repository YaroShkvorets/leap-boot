#!/usr/bin/env bash


echo "Booting up the chain ..."
sleep 3

python3 ./python/boot.py \
    --cleos=cleos \
    --dmlog-path=./run/dm.log \
    --actionlog-path=./run/expected.jsonl \
    --accounts-path=./boot/accounts.json \
    --genesis-path=./boot/genesis.json \
    --nodeos=nodeos \
    --keosd=keosd \
    --user-limit=15 \
    --producer-limit=3 \
    --producer-sync-delay=10 \
    --contracts-dir="./system-contracts-3.1" \
    -w -a -k

if [ $? -eq 0 ]; then
    echo "Logs successfully generated in ./run directory"
fi
