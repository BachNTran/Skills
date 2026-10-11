# humidity_sensor · changelog

### 2026-09-21-a71b · v1 · humidity_sensor.md · AI
- Created humidity_sensor (code): overview, brief, req, ICD, test plan, bindings. Awaiting approval.

### 2026-09-27-73e3 · v1 · all · Example Dev
- APPROVED humidity_sensor.bind.yaml v1 sha256:8493172f5462 by Example Dev.
- APPROVED humidity_sensor.brief.md v1 sha256:b913dfaaeb8d by Example Dev.
- APPROVED humidity_sensor.icd.md v1 sha256:35a707b40986 by Example Dev.
- APPROVED humidity_sensor.req.md v1 sha256:ef921c21c80d by Example Dev.
- APPROVED humidity_sensor.tests.md v1 sha256:762bd0c53f92 by Example Dev.
- APPROVED humidity_sensor.md v1 sha256:6405574368c7 by Example Dev.
- APPROVED all gates and code: module sha256:22e91123103f by Example Dev.

### 2026-09-27-5e2d · v2 · humidity_sensor.icd.md · AI
- Added Timing: read() blocks ≤ 10 ms; call from the 60 s task only. Why: the tick budget is 5 ms (firmware ICD) and the blocking time was undocumented. Code unchanged. Awaiting approval.
