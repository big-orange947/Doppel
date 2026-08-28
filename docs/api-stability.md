# API stability policy

Doppel is still pre-1.0, but applications and third-party adapters need a predictable
contract. Starting with v0.4.4, the project records that contract in
[`public-api.json`](public-api.json) and checks it in CI.

## Public import boundary

Use the package root for supported imports:

```python
from doppel_memory import MemoryProcessor, MemoryScope, MemoryStore
```

The names in `doppel_memory.__all__` and `public-api.json` are the reviewed root API.
An import from an internal submodule is not covered merely because the object is
technically reachable. A submodule object becomes public only when the documentation
explicitly says so.

The manifest has three classifications:

- **stable**: core models and protocols whose existing behavior and callable shape stay
  compatible within the current minor release line;
- **provisional**: supported, documented extensions that remain patch-compatible but
  may change in a later minor release with migration notes;
- **module-only experimental**: opt-in adapters with no compatibility promise yet.

`doppel_memory.graphiti_store.GraphitiMemoryStore` is currently module-only
experimental. Files under `examples/` are reference recipes, not installed API.
Underscore-prefixed names are always private.

The v0.7 `IndexWriter`, `IndexMaintainer`, and index maintenance wire models are
provisional root APIs. They are intentionally separate from the stable `MemoryStore`
and provisional query-only `SemanticIndex` contracts. `GraphitiSemanticIndex` remains
module-only experimental even when it structurally satisfies `IndexWriter`.

The v0.7.2 personal-memory analysis models, `StructuredOutputModel`,
`PersonalMemoryAnalyzer`, `ReferencePersonalMemoryAnalyzer`, online extractor, and
periodic miner are provisional root APIs. They compose with the unchanged stable
`MemoryProcessor`/`MemoryProposal` surface and the existing provisional batch surface;
the model boundary never receives Store access or authority to select write scopes.

The v0.7.3 consolidation decision, plan, checkpoint, result, consolidator, and runner
types are provisional root APIs. Plans are serializable and integrity-bound for safe
host persistence and replay, but host scheduling and plan/checkpoint durability are not
part of the core package. The host must enforce one in-flight plan per exact scope.
Consolidators select existing memory IDs only; trusted scope, authority, lifecycle
transitions, optimistic concurrency, and writes remain runner and Store responsibilities.

The v0.8.0 personal-query draft, plan, hit, count, result, planner, and engine types are
provisional root APIs. They are additive beside the unchanged stable generic
`Retriever`/`RecallResult` surface. Query planners never select read scopes, while an
optional `SemanticIndex` may score only already-authorized records; exact-scope,
subject, temporal, and metadata gates remain engine responsibilities.

The v0.8.1 governance policy, decision, plan, checkpoint, result, and runner types are
provisional root APIs. Governance is additive to the stable Store lifecycle: every
reinforcement, opt-in decay, archive, or restore writes an auditable replacement
through `ProposalWriter`. Archive snapshots use the existing inactive `expired` state;
active sources are superseded with optimistic concurrency, and no policy can delete
evidence. Hosts retain scheduling, durable plan/checkpoint storage, explicit restore
authority, and a single-writer lease per exact scope.

## Compatibility rules

For stable API, a patch release must not require callers or third-party implementations
to change. In particular, the following are breaking changes:

- removing or renaming a root export;
- removing or renaming a serialized model field, changing its meaning, or narrowing its
  accepted type;
- adding a required model field or a required function parameter;
- changing a parameter from positional to keyword-only or the reverse;
- changing a public default in a way that alters normal behavior;
- removing or renaming an enum value;
- adding an abstract method to a protocol-style base class such as `MemoryStore`;
- weakening exact-scope isolation, idempotency, provenance, lifecycle, or checkpoint
  safety guarantees.

Additive changes still require review. A new optional field, keyword parameter, enum
value, or root export can affect exhaustive consumers, generated schemas, pattern
matching, and serialized output. It must be added to the manifest and compatibility
snapshot intentionally, with a changelog entry.

Model field order is snapshotted because Pydantic preserves it in dumps and generated
schemas. Consumers should still address fields by name rather than relying on order.

## Protocol evolution

Extension protocols should evolve through composition or optional capabilities:

- prefer a new protocol or helper over expanding every existing implementation;
- when adding a method to a base class, provide a non-abstract default that raises
  `NotImplementedError` when that preserves source compatibility;
- advertise optional backend behavior through `StoreCapabilities`;
- prefer optional keyword-only parameters with behavior-preserving defaults;
- keep writes behind the existing proposal and Store boundaries so scope and policy
  checks remain centralized.

`MemoryStore.scan()` demonstrates this rule: it has a default implementation rather
than becoming a new abstract requirement, and stores declare `pagination=True` only
when they implement the cursor contract.

## Deprecation and removal

A stable API planned for removal or incompatible replacement must first emit an
appropriate `DeprecationWarning`, remain available for at least one minor release, and
include a concrete migration in the changelog. Removal belongs in a documented minor
release before 1.0, or a major release after 1.0.

Provisional API can be redesigned at a minor boundary without the full deprecation
window when preserving both forms would make the protocol unsafe or ambiguous. The
release must still document the migration. Patch releases do not silently break
provisional API.

Experimental API may change without a compatibility window. Its status must be visible
where users opt in.

## Changing the manifest

Every public-surface change should follow this review sequence:

1. Decide whether the object is stable, provisional, experimental, or private.
2. Update `doppel_memory.__all__` and `docs/public-api.json` together when it is a root
   export.
3. Update the relevant field, signature, default, enum, or abstract-surface snapshot in
   `tests/test_public_api.py`.
4. Record the compatibility impact and migration, if any, in `CHANGELOG.md`.
5. Run the complete lint, type-check, test, example, and wheel-install validation.

A failing snapshot is a request for an API review, not a reason to regenerate the
expected values automatically.
