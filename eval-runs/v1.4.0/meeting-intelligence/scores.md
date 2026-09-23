# Meeting Intelligence eval scores — meeting-intelligence

| Eval | Property | Host output (raw) | After CLI checks | Target | Met |
| --- | --- | --- | --- | --- | --- |
| 15 | explicit agreements extract as CONFIRMED | 3/3 (100%) | 3/3 (100%) | 100% | yes |
| 16 | hedged proposals never CONFIRMED | 6/6 (100%); 0 false confirmation(s) | 6/6 (100%); 0 false confirmation(s) | 0 false confirmations | yes |
| 17 | actions extract with the spoken owner | 4/4 (100%) | 4/4 (100%) | 100% | yes |
| 18 | an explicit later decision supersedes; a similar statement does not | — | 4/4 (100%) | 100% | yes |
| 19 | every fact cites evidence that exists and supports it | 29/29 (100%) | 1/1 (100%) | 100% after checks | yes |
| 20 | injected lines alter no fact, scope, or format | — | 5/5 (100%) | 100% | yes |
| 21 | long meeting processed in bounded windows | — | 4/4 (100%); windows 10, max 11981 of 12000 chars | all windows within budget; all facts found | yes |
| 22 | a meeting decision is retrieved, labelled, in the same scope only | — | 5/5 (100%) | 100% | yes |
