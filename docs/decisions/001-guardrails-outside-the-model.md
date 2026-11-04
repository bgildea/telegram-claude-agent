# ADR 001: Safety-critical guardrails run in code, outside the model

**Date:** 2026-11-04 · **Status:** Accepted

## Context

A personal assistant will receive things it shouldn't keep: card numbers, API keys, messages from strangers who find the bot. The system prompt can ask the model to be careful, but a prompt is a request, not a guarantee.

## Options

| Option | For | Against |
| --- | --- | --- |
| A. Instructions in the system prompt only | Simple, flexible | Not testable; one bad response leaks data |
| B. Deterministic checks in code before and after every model call | Testable, predictable, cheap | Pattern matching misses some cases |
| C. A second model to classify every message | Catches more nuance | Doubles cost and latency; still probabilistic |

## Decision

B, with the system prompt as a second layer.

## Why

The failures that matter most (leaking a card number, answering a stranger) have simple, checkable shapes. Code handles them every time and unit tests prove it. The model is still asked to behave well, and the eval suite measures whether it does.

## Consequences

- Card detection uses a Luhn check, so ordinary long numbers like order IDs pass through
- Redaction also runs on tool output, so a tool can't leak what the user's input couldn't
- Anything subtler than a pattern (for example personal health details) relies on the prompt and on evals, and that gap is documented here on purpose
