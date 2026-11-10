#!/usr/bin/env bash
# DESC: Model-check the formal models in verification/ with TLC (needs Java; ~40s; not part of check)
# Usage: ./dev verify [--trace NAME | --sync]
#
#   (no args)      run every check, the recorded findings, and the mutants
#   --trace NAME   print one run's full TLC output
#   --sync         after a green run, record that the model describes the code as it is now
#
# Deliberately not a tier of `./dev check`: it needs a JVM and a minute, for code
# that rarely changes. The gate carries the cheap half instead — a tier-0 test
# that fails when the modelled code changed without this being re-run.
source "$(dirname "$0")/lib/dev.sh"
cd "$PROJECT_ROOT"
exec python3 verification/host/check.py "$@"
