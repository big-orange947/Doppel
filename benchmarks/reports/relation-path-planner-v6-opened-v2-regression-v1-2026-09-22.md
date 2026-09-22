# Relation-path Planner V6 opened V2 regression v1

Date: 2026-09-22. V2 was opened by the preceding V5 sealed run. This V6 result is
regression evidence only and is not eligible as unseen evidence.

## Identity and budget

- Source commit: `ea7628856a816ef021b1f38fb22e24f5c6215736`
- Planner: `doppel.reference-personal-memory-relation-path-planner-v6`
- Protocol: `v6_relation_atoms_host_compilation`
- Provider calls: 48 / 48
- Doppel cache hits/misses: 0 / 48
- Input/output/total tokens: 163,655 / 7,557 / 171,212
- Complete valid cases: 48 / 48
- Provider/planner errors: 0 / 0
- Report SHA-256: `ebd891283bc1d316501ef69eca05f1394ab50075d2bf90a0be61af3d4157af8f`

## Result versus V5

| Metric | V5 sealed | V6 regression | Delta |
|---|---:|---:|---:|
| Exact path | 0.750000 | 0.833333 | +0.083333 |
| Decision | 0.854167 | 0.854167 | 0 |
| Relation type | 0.604167 | 0.687500 | +0.083333 |
| Direction | 0.645833 | 0.708333 | +0.062500 |
| Two-hop exact | 0.312500 | 0.562500 | +0.250000 |
| Path recall | 0.781250 | 0.781250 | 0 |
| Forbidden hits | 1 | 0 | -1 |
| Wrong execute | 0 | 0 | 0 |

The opened regression gate still failed: exact path, decision, and reason remained below
their thresholds. V6 receives no execution authority.

## What the representation fixed

Declarative atoms plus host compilation recovered four V5 failures:

- the implicit repairer-to-location chain;
- shared purchase-venue outbound/inbound traversal;
- shared birthplace outbound/inbound traversal;
- double-inbound employee-to-care-recipient traversal, regardless of atom order.

The host also converted the previous wrong nearby repair type into safe abstention
because the model's atoms did not connect to the fixed anchor. This removed the
forbidden hit rather than executing a disconnected graph.

## Remaining bottleneck

Eight path cases still failed. Seven were ultimately abstentions: one relation
enumeration remained `nonrelation`, five implicit/inbound compositions remained model
`ambiguous`, and two model-authored exact atom graphs lacked an anchor connection and
were safely rejected by the host (one overlaps the preceding count categories). The
last failure emitted only the custody atom and omitted the location-to-person atom.

V6 therefore improved type/order/direction compilation but did not improve answerable
path recall or execute/abstain accuracy. The remaining failure happens before host
compilation: the model refuses or fails to emit a complete predicate inventory.

## Decision

Do not add host inference that invents missing atoms from surface words. The next opened
experiment uses two model passes over the same governed schema:

1. extract a V6 atom observation;
2. independently review that observation against the original question and definitions,
   repairing missing predicates, endpoint bindings, shared references, or an unjustified
   ambiguity;
3. validate the reviewed ontology and compile it with the unchanged V6 host algorithm.

The second pass remains non-authoritative and cannot execute a path. It doubles the
worst-case provider-call budget. If it cannot materially improve opened V2, the next
decision should be a stronger Planner model or accepting that implicit multi-hop recall
belongs outside the default path Planner.
