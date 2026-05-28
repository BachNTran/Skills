# Coding Standards

## Purpose

This file defines the coding standards for this project.
The agent applies these during the REFACTOR step of every TDD cycle.
All code must pass these standards before a slice is considered complete.

## Project Language and Standard

- Language: TODO
- Base standard: TODO (e.g., MISRA-C 2012, CERT-C, project-specific)
- Standard version: TODO

## Naming Conventions

| Element | Convention | Example |
|---|---|---|
| TODO | TODO | TODO |

## Structure Rules

- TODO

## Function Rules

- Maximum function length: TODO lines
- Single responsibility: TODO (define what this means for this project)
- TODO

## Error Handling

- TODO

## Memory Rules

- TODO (e.g., no dynamic allocation, stack budget per module)

## Comment Rules

- TODO (when required, when forbidden)

## Forbidden Patterns

| Pattern | Why avoided | Use instead |
|---|---|---|
| TODO | TODO | TODO |

## Module Rules

- Every module must have a single stated responsibility
- Every module must have a minimal public interface
- Every module's tests must be runnable independently
- Test doubles must never be inline — always in shared files

## Linter / Static Analysis

- Tool: TODO
- Config file: TODO
- Command: TODO
- Must pass: before every slice closes

## Test Standards

- Tests co-located with code (per project convention)
- One authoritative double per external dependency
- No inline mocks in test files
- Integration tests at the module boundary level
- Test command must be exact and repeatable
