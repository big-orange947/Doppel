# Evidence-rich blind V1 — authoring V1 incomplete result

Date: 2026-09-28

Status: preserved authoring-contract failure; retrieval was never opened

Implementation commit: `dfd660263d4b987e95a7fe03b44d4201cc4a8828`

Host-manifest fingerprint:
`fa7da45c5822168e8bc30fcd4c26eb585375e3969018f682c7c5e18cf7515965`

## Execution

- logical batches: 48;
- completed batches: 4;
- provider calls: 5;
- calls with usage: 5;
- input tokens: 29,822;
- output tokens: 23,429;
- total tokens: 53,251;
- reasoning tokens: 0;
- invalid cache entries: 0;
- retrieval calls and quality metrics: 0.

The fifth raw response was cached successfully but failed host projection for
`owner-blind-03:01`. Two distinct host entity slots received the same display name
`云澜科技`: `entity-current-employer` and `entity-one-hop-target`. The raw cached
envelope is preserved in ignored runtime data with SHA-256
`e8aed918a783716e4019341f4518686b6b9af929e1e6e8e108a9893bb3bbe7e9`.

The first two completed owners also exposed a separate contract gap. Their designated
cross-owner shared-name slots were authored as `启明服务中心` and `启明中心`, so the
frozen compiler would reject the corpus even if all remaining calls succeeded.

## Decision

No cache entry or report was overwritten, no invalid surface was repaired in place,
and no V7/V8 retrieval output was opened. Authoring V1 stops here.

Authoring contract V2 keeps the same host-owned topology and evidence policy but:

- gives the shared-name slot one exact host-required display name;
- requires every other entity display name to be unique within an owner request;
- uses a new runner identity, nonce namespace, cache directory, progress file, and
  manifest fingerprint.

This change addresses a demonstrated authoring/projection contradiction before the
first retrieval run. It is not selected from, and cannot be influenced by, V7/V8
quality results because those results still do not exist.
