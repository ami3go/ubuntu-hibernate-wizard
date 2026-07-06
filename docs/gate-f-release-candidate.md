# Gate F release-candidate evidence check

Gate F is the release-candidate gate after Gate E.  It does **not** modify the system and it does **not** replace the disposable-VM Gate E test.  Gate F only checks that the evidence from Gate E is complete and internally consistent before a package is treated as a release candidate.

## Required evidence

Gate F requires two files:

1. A Gate E real-apply report from a disposable Ubuntu VM.
   - It must be produced by `--gate-e-apply`.
   - Its status must be `manual_hibernate_pending`.
   - The helper apply step must have succeeded.
2. A manual hibernate/resume record made after rebooting the same VM.
   - The VM must be rebooted after apply.
   - Hibernation must be attempted.
   - Resume must succeed.
   - Post-resume verification must pass.

## Create the manual record

After Gate E real apply, reboot the disposable VM, test hibernation/resume, then create the manual record:

```bash
ubuntu-hibernate-wizard \
  --gate-f-record-manual \
  --gate-e-report /var/log/ubuntu-hibernate-wizard/gate-e/gate-e-apply-YYYYMMDDTHHMMSSZ.json \
  --output ./gate-f-manual-record.json \
  --operator "release-vm-operator" \
  --manual-status passed \
  --reboot-performed \
  --hibernate-attempted \
  --resumed-successfully \
  --post-resume-verify-passed \
  --notes "Disposable VM hibernated and resumed successfully."
```

If the VM did not resume correctly, use `--manual-status failed` and do not pass the success flags.  The later Gate F check will remain blocked.

## Run Gate F check

```bash
ubuntu-hibernate-wizard \
  --gate-f-check \
  --gate-e-report ./gate-e-apply.json \
  --manual-record ./gate-f-manual-record.json \
  --output ./gate-f-manifest.json
```

A successful manifest has:

```json
{
  "status": "release_candidate_ready"
}
```

## Safety boundary

Gate F does not mean that every machine can hibernate.  It means the release candidate has passed the defined disposable-VM evidence checks.  Public release still needs package install/removal smoke tests and manual review of release notes.
