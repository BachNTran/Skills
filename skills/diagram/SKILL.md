---
name: diagram
description: Hand-author clean Mermaid diagrams — system architecture, component/data-flow, sequence, call/dependency graph, or deployment — for whatever project you are in, using real names at subsystem altitude. Reads code, docs, and the project glossary; asks the developer when scope or altitude is ambiguous. Use when asked to draw, visualize, or diagram a system, module, or flow, or when writing architecture or design docs.
---

# /diagram — hand-authored Mermaid diagrams

Draw clean, intentional architecture and visualization diagrams in Mermaid for the current
project. **Curated by hand** from reading the code and docs — never dumped from a tool. Aim for
diagrams a reader digests at a glance.

## When to use
- The developer asks to **draw / visualize / diagram** a system, module, data flow, sequence,
  call graph, or deployment.
- You are writing or updating **architecture/design docs** and a diagram would carry the mental
  model better than prose.

## When NOT to use
- Non-Mermaid asset/image generation.
- Exhaustive machine-generated graphs — this skill **curates**, it does not dump tool output.

## Method
1. **Understand before drawing.** Read the relevant code **and** docs. Adopt the project's own
   vocabulary: look for a glossary (`GLOSSARY.md`, `docs/`, `README`), then fall back to the real
   identifiers in the code. Use names that already exist in the repo.
2. **Clarify with the developer when ambiguous** — don't guess on: which modules are in scope, the
   altitude, which archetype, where the boundaries are. One or two sharp questions beat a wrong
   diagram.
3. **Pick the archetype(s)** from the catalog. Often two complementary views (e.g. architecture +
   one sequence) beat a single overloaded diagram.
4. **Draft at subsystem altitude.** One box per meaningful module, **real names**, ~12 nodes max;
   if it would sprawl, split into several focused diagrams.
5. **Validate it renders.** Run `mmdc` (mermaid-cli) if available; otherwise check the syntax
   deliberately. A diagram that doesn't render is worse than none.
6. **Pair every diagram with short prose** — 1–3 sentences on what it shows and the one insight to
   take away.
7. **Place it (output mode C).** Ask whether to (a) write into the project's docs — detect where
   docs live (`docs/`, a subsystem `*_diagrams.md`, existing Mermaid usage) and respect that
   location's conventions (frontmatter, file naming) — or (b) hand it back standalone. **Never
   silently overwrite**: update a diagrams section or propose a new file.

## Two hard rules
- **Real names over abstractions.** Use module / file / class / contract names that actually exist.
  - Good: `auth_service.py --> token_store --> redis`
  - Bad: `Service --> Store --> Cache`
- **Subsystem altitude; split before you sprawl.** Default to module/subsystem level; go to
  function/line level only when explicitly asked. Several small diagrams beat one giant one.

## Archetype catalog (copy and adapt)

### 1. System architecture — nested containment
```mermaid
flowchart TB
  subgraph host[Host]
    subgraph svc[api_service]
      router[router.py] --> handler[handlers/]
    end
    db[(postgres)]
  end
  handler --> db
```

### 2. Component / data-flow — protocol-labeled edges
```mermaid
flowchart LR
  ingest[ingest.py] -- "kafka: events" --> proc[processor.py]
  proc -- "grpc:50051" --> store[store.py]
  proc -- "writes" --> db[(timeseries_db)]
```

### 3. Sequence — one runtime interaction
```mermaid
sequenceDiagram
  autonumber
  participant C as client
  participant A as api_service
  participant D as db
  C->>A: POST /order
  A->>D: insert order
  D-->>A: ok
  A-->>C: 201 created
```

### 4. Call / dependency graph — curated, module level
```mermaid
flowchart LR
  cli[cli.py] --> core[core/engine.py]
  core --> risk[risk.py]
  core --> exec[execution.py]
  risk --> contracts[contracts/]
  exec --> contracts
```

### 5. Deployment / topology — processes, ports, hosts
```mermaid
flowchart LR
  lb[load_balancer :443] --> app
  subgraph node[host : vm]
    app["app :8080"]
    worker[worker]
  end
  app -- ":5432" --> db[(db)]
  worker -. "reads" .-> db
```

## Output contract
Every run yields: the **diagram(s)**, **render-validated**, each with **short prose**, **placed by
the project's convention** (or standalone on request), and **never a silent overwrite**.
