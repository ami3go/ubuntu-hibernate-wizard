#!/usr/bin/env bash
set -euo pipefail

# Gate E validation helper for a disposable Ubuntu VM.
# This script is intentionally conservative.  It runs tests/build/preflight first
# and performs real apply only when UHW_GATE_E_REAL_APPLY=1 is exported.

ACK="I_UNDERSTAND_THIS_IS_A_DISPOSABLE_VM"
REPORT_DIR="${UHW_GATE_E_REPORT_DIR:-$PWD/dist/gate-e-reports}"
PYTHONPATH="${PYTHONPATH:-.}"
export PYTHONPATH
mkdir -p "$REPORT_DIR"

log() { printf '\n[Gate E] %s\n' "$*"; }

log "Running unit tests"
python3 -m pytest -q

log "Building Debian package"
make deb

log "Collecting unprivileged preflight report"
python3 -m ubuntu_hibernate_wizard.main --gate-e-preflight --gate-e-report-dir "$REPORT_DIR" || true

log "Running root dry-run helper validation"
sudo -E PYTHONPATH="$PYTHONPATH" python3 -m ubuntu_hibernate_wizard.main --gate-e-dry-run --gate-e-report-dir "$REPORT_DIR"

log "Running root validate-plan helper validation"
sudo -E PYTHONPATH="$PYTHONPATH" python3 -m ubuntu_hibernate_wizard.main --gate-e-validate-plan --gate-e-report-dir "$REPORT_DIR"

if [[ "${UHW_GATE_E_REAL_APPLY:-0}" == "1" ]]; then
  log "REAL APPLY ENABLED for this disposable VM"
  sudo -E PYTHONPATH="$PYTHONPATH" python3 -m ubuntu_hibernate_wizard.main \
    --gate-e-apply \
    --gate-e-ack "$ACK" \
    --gate-e-report-dir "$REPORT_DIR"
  log "Real apply completed. Reboot VM and perform manual hibernate/resume test."
else
  log "Real apply skipped. Export UHW_GATE_E_REAL_APPLY=1 only inside a disposable VM."
fi

log "Reports saved under $REPORT_DIR"
