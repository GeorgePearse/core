# Upstream listeners

> When a project changes how it implements something my repo cares about, open a
> PR implementing the new approach in my repo.

An upstream listener is a standing connection between an upstream implementation
and a downstream concern. It watches code, decides whether a change matters to that
concern, adapts the implementation to the destination repository, runs its checks,
and opens a pull request automatically. The useful output is working code to review.

Registering an enabled listener authorizes that ongoing detection-to-PR workflow;
it should not ask again before each adaptation. Merging remains the repository
owner's decision. The CLI and service implement this workflow; see the README for setup and current bounds.

## What the user specifies

- **Upstream:** repository, tracked branch, immutable starting revision, and relevant
  files, symbols, tests, or documentation.
- **Concern:** what the destination cares about and why. This drives relevance even
  when a refactor moves the implementation outside its original directory.
- **Destination:** repository, base branch, implementing files, and related tests.
- **Adaptation contract:** behavior to adopt, local interfaces and invariants to keep,
  and validation commands to run.
- **Delivery:** automatically open a draft implementation PR; include provenance and
  validation evidence. The listener does not authorize merging or deployment.

An inspiration records where an idea came from; a listener can also be prospective:
"we care about how this project solves this problem, even if we have not borrowed
from it yet." A prospective relationship must not be recorded as proven past influence.

## Concrete example: DeepSeek Harness

The [listener manifest](../examples/deepseek-harness-listener.json) watches
[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)'s tool-result
pruning. Its upstream paths and baseline commit are real; the downstream repository,
paths, validation command, and desired constraints are illustrative. It is disabled
until a real destination is configured.

At the recorded [baseline implementation](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/packages/compaction/compaction-tool-result-pruner/src/index.ts),
the relevant concern is reducing oversized tool outputs while preserving useful
context. The accompanying [upstream tests](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/packages/compaction/compaction-tool-result-pruner/tests/tool-result-pruner.spec.ts)
provide evidence about behavior. The listener would track subsequent changes to
that implementation and its tests, then adapt relevant changes to the target's own
tool-result handling. This is a candidate watch scope, not a claim that one of the
user's existing repositories already depends on it.

For example, if upstream changes what context it retains from an oversized tool
result, Memetics should identify the behavioral difference and implement the same
approach through the local code's interfaces. A downstream repository in another
language should receive an idiomatic port of the behavior. The PR should explain
any deliberate difference from upstream.

## From upstream change to implementation PR

1. **Detect:** receive upstream push events when webhook access is available. For
   public projects where we cannot install a webhook, poll the tracked ref and
   reconcile missed events. Enqueue immediately on detection; actual delivery
   includes detection lag, implementation time, and validation time.
2. **Pin:** retain the immutable upstream before/after revisions, listener configuration,
   and destination base SHA. Inspect the actual changed files and configured destination implementation and tests.
   The adaptation agent looks up further code in both repositories on demand; it does not build a full call graph.
3. **Assess relevance:** compare changed behavior with the declared concern and local
   implementation. Paths and symbols guide assessment; rename-aware diffs preserve file moves.
   Record a reason for irrelevant changes or behavior already present locally.
4. **Implement:** start an isolated destination checkout, follow its repository rules,
   and adapt the upstream approach while preserving the configured local contracts.
   Port relevant regression cases and preserve required source/license attribution.
5. **Validate:** run the destination checks and compare the changed behavior with the
   pinned upstream implementation. Record exact commands, results, and limitations.
6. **Deliver:** automatically open or update a draft PR with the implementation, tests,
   upstream comparison, rationale, and validation evidence. No per-change approval
   is needed to create the PR. Surface blocked adaptations with a concrete cause;
   a notification or empty PR is not a completed adaptation.

An implementation with failed or unavailable checks can still be delivered as a
clearly blocked draft with its patch and failure evidence. It must not claim success.
Conflicting local requirements or an ambiguous upstream change should produce an
explicit unresolved decision rather than silently choosing incompatible behavior.

## What every adaptation PR contains

- Listener ID and the local concern it serves.
- Upstream repository and immutable before/after links, including the relevant diff.
- Destination base revision, implementation changes, and regression coverage.
- Explanation of how the local change follows upstream, including intentional deviations.
- Validation results, source attribution, and any unresolved compatibility issue.

The provenance should be inspectable directly from the PR and retained with its
listener run. Generated interpretations of an upstream change remain interpretations;
source diffs and tests are the supporting evidence.

## Repeated events and evolving branches

Persist the latest observed revision, each proposed revision and PR, and the latest
adopted revision separately. Seeing a commit or opening a PR does not mean its
implementation has been adopted. A merge records adoption; closing a PR records a
decline, so a retry does not reopen the same proposal. Later upstream changes are
assessed against the current destination and the retained decisions.

Deduplicate deliveries by listener, upstream revision, and destination repository.
Serialize updates for a listener and reuse its open PR when later commits extend
the same change. Preserve human edits; if the branch has changed unexpectedly,
reconcile before publishing. Recheck the destination base and rerun affected checks
when it moves. Track renamed paths, coalesce queued bursts into a comparison spanning the skipped revisions, and
flag force-pushes or removed branches for reconciliation rather than assuming a
linear history. Retries resume recorded work instead of spawning duplicate PRs.

## Execution model

Use a durable queue and an isolated worker checkout per adaptation. Listener-scoped
credentials allow upstream reads and destination branch/PR writes. Upstream code,
comments, and documentation are evidence, not instructions granting new authority.
Keep private source content within authorized destinations and run checks in the
worker's restricted environment. Configure bounded work, retries, and spend, and
allow listeners to be paused independently.

The first useful implementation is one configured listener completing the entire
loop: a relevant upstream change produces a downstream code-and-tests PR with
traceable evidence. Event ingestion alone is not that milestone.
