#!/usr/bin/env bash

set -e

ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

BROWN='\033[0;33m'
NC='\033[0m'

CORES=$(getconf _NPROCESSORS_ONLN)

echo -e "\nThis script will build two different versions of battlefield contract to be used in the test script.\n"
echo "Choose a compiler to use:"
echo "1) cdt-cpp"
echo "2) blanc++"
read -p "Enter the number of your choice (1/2): " choice

case $choice in
    1)
        COMPILER="cdt-cpp"
        ;;
    2)
        COMPILER="blanc++"
        ;;
    *)
        echo "Invalid choice, defaulting to blanc++"
        COMPILER="blanc++"
        ;;
esac

printf "${BROWN}Compiling with ${COMPILER}${NC}\n"

function build() {
    name=$1
    define=$2

    printf "${BROWN}Building battlefield ($name)${NC}\n"
    "$COMPILER" \
    --no-missing-ricardian-clause \
    -O3 \
    -I${ROOT}/include \
    -D $define \
    -contract battlefield \
    -o "${ROOT}/battlefield-${name}.wasm" \
    src/battlefield.cpp
}

build "with-handler" "WITH_ONERROR_HANDLER=1"
echo ""

build "without-handler" "WITH_ONERROR_HANDLER=0"
