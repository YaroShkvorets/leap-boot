#!/usr/bin/env bash

echo "Decoding dm.log to dm.log.json ..."

cd decode

go run ./decode.go ../run/dm.log ../run/dm.log.json

cd ..