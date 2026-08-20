# Extension ↔ Local Engine protocol compatibility policy

The compatibility boundary is `protocolMajor`.

- V1 extension and V1 Engine use `protocolMajor = 1`.
- A backward-compatible Engine change may add optional response fields, new capability flags, or new error detail while preserving existing required fields and semantics.
- The extension must ignore unknown optional fields and must not treat unknown Engine errors as retryable by default.
- A breaking change to authentication, endpoint meaning, required request fields, binary result validation, ProcessingSpec semantics, ticket idempotency, or security invariants requires a new `protocolMajor`.
- An extension must reject an Engine with an unsupported major rather than attempting best-effort processing.
- A controlled release manifest records the protocol major of every archived Engine artifact.
- Rollback artifacts must retain at least one Engine version compatible with the Store/unpacked extension being restored.

Protocol compatibility never overrides profile compatibility. Model/renderer/provider changes remain bound to the Engine profile fingerprint and WorkSignature rules established earlier.
