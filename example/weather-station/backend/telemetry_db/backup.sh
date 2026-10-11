#!/bin/sh
# Online backup of the readings database: backup.sh <db-file> <backup-dir>
set -eu
mkdir -p "$2"
sqlite3 "$1" ".backup '$2/readings-$(date +%Y%m%d).db'"
