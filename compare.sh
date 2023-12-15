#!/usr/bin/env bash

echo "Comparing expected.jsonl and dm.log.json ..."
sleep 1

python3 ./python/compare.py ./run/expected.jsonl ./run/dm.log.json

