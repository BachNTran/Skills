# Test Plan Dimensions

For each test case in the plan, think through:

- **Inputs:** valid, invalid, boundary, empty, enormous, malformed, adversarial
- **States:** fresh, populated, corrupted, partial, missing
- **Sequences:** out of order, repeated, interrupted, skipped steps
- **Environments:** slow, unavailable, degraded, resource-constrained
- **Actors:** intended user, confused user, impatient user, concurrent user, adversarial actor
- **Failures:** each dependency unavailable, each write failing, each read returning garbage
- **Concurrency:** simultaneous identical operations, conflicting operations, race conditions
- **Recovery:** retry behavior, partial state cleanup, rollback correctness
- **Observability:** can a test assert this result without human eyes?
- **Time:** too early, too late, expired, wrong clock, unexpected ordering

## Test levels (pyramid — cover all three)

- **Unit (white-box):** every public function and every branch/edge path. The base and bulk of cases.
- **Integration:** every subsystem seam / contract boundary, real collaborators where feasible.
- **E2E:** full path proving success criteria; add golden-master + determinism for deterministic systems.

## Traceability & coverage

- Forward: every REQ-### → ≥1 test case.
- Reverse: every public function/branch → ≥1 unit test; every case names its REQ-###; orphan tests flagged.
- Maintain a matrix: REQ-ID ↔ test-case ID ↔ level ↔ test file path.
- Coverage gate: new/changed modules ≥90% line AND branch, enforced in CI (`pytest --cov --cov-branch --cov-fail-under=90`).
- Parameterize as a range/equivalence class (with boundaries), never duplicated rows.

For hardware / embedded projects, also cover:

- Endianness and byte order
- Cache coherency and DMA interaction
- Interrupt timing and ISR reentrancy
- Register access patterns and hazards
- Memory alignment and word size
- Power state transitions
- Real-time deadline behavior
- Hardware sanity tests (verify `DOMAIN_CONTEXT.md` claims on real hardware before implementation)
