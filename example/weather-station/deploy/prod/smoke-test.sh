#!/bin/sh
# Smoke test a deployment: smoke-test.sh <base-url>
set -eu
curl -fsS "$1/healthz" >/dev/null
curl -fsS "$1/v1/latest?station=0" >/dev/null
echo "smoke ok"
