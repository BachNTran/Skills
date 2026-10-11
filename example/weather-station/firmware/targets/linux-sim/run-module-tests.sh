#!/bin/sh
# linux-sim target: build the current module's tests natively and run them.
# Run in a module directory (modgate does: cwd = module). Compiles src/*.cpp, children's */src/*.cpp
# (subsystem integration tests) and test/*.cpp against every include/ and fakes/ dir of the firmware.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
FW="$(cd "$HERE/../.." && pwd)"
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT
INCS="$(find "$FW" -type d \( -name include -o -name fakes \) | sed 's/^/-I/')"
SRCS="$(ls src/*.cpp */src/*.cpp 2>/dev/null || true)"
TESTS="$(ls test/*.cpp 2>/dev/null || true)"
[ -n "$TESTS" ] || { echo "no tests in $(pwd)/test" >&2; exit 1; }
# shellcheck disable=SC2086
c++ -std=c++17 -Wall -Wextra -I"$HERE/gtest_shim" $INCS $SRCS $TESTS "$HERE/gtest_shim/gtest_main.cpp" -o "$OUT/tests"
"$OUT/tests"
