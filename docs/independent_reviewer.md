# Independent Reviewer

`independent_reviewer` is the read-only stage immediately after Semantic
Executor. It verifies an exact `ExecutionCandidate` without changing its gate,
admitting policy, mutating state, or executing an action.

## Route

```text
SemanticInput
  -> ServerLLMProvider
  -> validated ExecutionCandidate
  -> LLMIndependentReviewer
  -> IndependentReview
```

The public `boris.execute` route performs all four steps in one Runtime call.
The experimental private `ChatGPTHostProvider` does not use this stage and
retains `not_independently_reviewed`.

## Independence claim

Core v2.31 defines:

- `IND2`: distinct method;
- `IND3`: distinct executor or substrate;
- `IND4`: external human or organizational verification.

Runtime declares only `IND2`. The Reviewer has a separate logical owner
(`O027.runtime-independent-reviewer`), a new LLM adapter instance, an
adversarial counterexample/gate-cross-check prompt, and a separate output
validator. It may still use the same configured model provider as Semantic
Executor, so `IND3` is not claimed. `IND4` requires an external verifier.
The receiving-substrate profile is
`boris-runtime/phase-4s-independent-review` and declares the corresponding
`independent_review_ind2` capability.

## Contract

The additive public object uses
`review_version: "boris-independent-review/1.0"` and contains:

- `decision`: `PASS`, `HOLD`, or `REJECTED`;
- `candidate_gate_assessment`: `SUPPORTED`, `INDETERMINATE`, or
  `UNSUPPORTED`;
- concise supported, refuted, unresolved, and distorted claims;
- a Core-aligned `IndependentReview` Evidence object;
- deterministic bindings;
- `state_mutation: false`.

Decision consistency is strict:

- `PASS` requires a supported gate and no material review defect;
- `HOLD` requires an indeterminate gate assessment and an unresolved review
  issue;
- `REJECTED` requires an unsupported gate plus a refuted claim or distortion.

Review decision and semantic gate are independent axes. A semantically correct
`C04/HOLD` may receive Review `PASS`; the candidate remains `C04/HOLD`.

## Exact bindings

Runtime, not the reviewer model, calculates SHA-256 bindings for:

- the complete `SemanticInput`;
- the validated semantic calculation projection;
- the full `ExecutionCandidate`;
- the exact Core reference;
- the active RuntimeAttestation.

Before the LLM call, Runtime also verifies phase, Core, selected norm set, and
attestation identity. Any mismatch fails closed. After the call, the output is
validated against a strict Runtime contract and, when the active package
provides it, Core's `IndependentReview` schema.

## Configuration

Reviewer configuration inherits the canonical semantic provider by default:

```bash
BOIS_LLM=openai
OPENAI_MODEL=gpt-5.6-terra
```

It can be selected independently:

```bash
BORIS_REVIEWER_LLM=openai
BORIS_REVIEWER_MODEL=gpt-5.6-terra
```

Each low-level call is bounded by
`BORIS_SERVER_LLM_TIMEOUT_SECONDS`. The MCP and reverse-proxy timeout must
cover compilation, calculation, and review. The default MCP timeout is 420
seconds.

## Explicit exclusions

Independent Reviewer does not:

- modify `ExecutionCandidate.gate`;
- close or create operator HOLD input;
- produce a `KernelDecision`;
- admit a `StateEvent`;
- write memory;
- call external tools;
- claim IND3 or IND4.
