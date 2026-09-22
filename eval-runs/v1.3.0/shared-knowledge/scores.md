# Shared knowledge evals (18, 19)

Produced by `python3 scripts/eval-shared-knowledge.py`. Deterministic and offline: three simulated
installations share one bare-repository source. What is measured is what each agent is given
by `knowledge read --brief`, not how a model phrases its answer.

| Eval | Property | Result | Target | Met |
| --- | --- | --- | --- | --- |
| 18 | before approval, the proposer sees it labelled `local, unshared` | yes | yes | yes |
| 18 | before approval, the other two do not see it | 2/2 | 2/2 | yes |
| 18 | after approval + sync, the same CONFIRMED shared top answer | 3/3 (100%) | 100% | yes |
| 19 | superseded decision never presented as current | 18/18 clean (100%) | 100% | yes |
| 19 | engineer B, who held the old decision locally, is told on sync | yes | yes | yes |

Top answer each installation was given after approval:

| Installation | Label | Status | Statement | Approval |
| --- | --- | --- | --- | --- |
| `a` | shared:acme | CONFIRMED | Payment retries use Kafka. | approved by Rita Reviewer via PR #31 |
| `b` | shared:acme | CONFIRMED | Payment retries use Kafka. | approved by Rita Reviewer via PR #31 |
| `c` | shared:acme | CONFIRMED | Payment retries use Kafka. | approved by Rita Reviewer via PR #31 |
