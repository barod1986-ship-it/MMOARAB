# REV21 local production-execution probe

This directory is **diagnostic only** and is not V1 release evidence.

`rev21-local-qualification-readiness.json` records the live probe result from the constrained build/audit environment used to prepare REV21. It is expected to remain `passed=false`: the environment is not a protected `mte-production-qualification` runner, does not expose `MTE_QUALIFICATION_INPUT_ROOT`, and does not use the canonical production toolchain versions.

A real production run must create its readiness result on the protected runner through `.github/workflows/production-execution-readiness.yml` and the qualification workflow's own live preflight. This file must never be promoted as qualification, smoke, signing, or release-ready evidence.

## REV24 fail-closed release-gate probes

`rev24-private-v1-gate.txt` and `rev24-public-v1-gate.txt` are local diagnostic gate outputs after repository provisioning tooling was added. They remain blocked at **19** and **28** items respectively. They are not production evidence and are retained only to prove that bootstrap/provisioning code does not auto-satisfy release gates.
