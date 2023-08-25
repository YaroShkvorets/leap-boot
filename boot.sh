#!/usr/bin/env bash

python3 boot.py --cleos=cleos --nodeos=nodeos --keosd=keosd --user-limit=10 --producer-limit=3 --producer-sync-delay=10 --contracts-dir="./system-contracts-3.1" -w -a -k