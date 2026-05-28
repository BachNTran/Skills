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

For hardware / embedded projects, also cover:

- Endianness and byte order
- Cache coherency and DMA interaction
- Interrupt timing and ISR reentrancy
- Register access patterns and hazards
- Memory alignment and word size
- Power state transitions
- Real-time deadline behavior
- Hardware sanity tests (verify `DOMAIN_CONTEXT.md` claims on real hardware before implementation)
