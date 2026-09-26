# CSQ14 final integration — 2026-09-26

Sourcefreeze13687209eec7eaf440b9171f4a49f6110bcfdca5. Allimplementationlanes
landed anddrained;3readonlyholisticreviewers active. Existing PR2229stillce4c9de67.

| Lane | Landed merge | State |
| --- | --- | --- |
| MLseed | 6fa357a1b | Drained,237strictpasses |
| Archiveevidence | 6d5e34e35 | Drained,uncertainrefsretained |
| Dependency/classfixtures | dfcddfe7e | Reviewed74strictpasses |
| R1auth | 7fc46af2b | Drained,2cleanrounds |
| D1unitfixtures | dddf90871 | Drained,2cleanrounds |
| D3regressioncleanup | 30cbafa19 | Drained,2cleanrounds |
| D2ownership | 70af3a787 | Drained,2cleanrounds |
| R2runtime | 13687209e | Draining,2cleanrounds |

Detachedreviewers: ml_gate_recovery correctness; archive_checkpoint security;
ml_correctness_review coverage. Each sibling under
/Users/esperie/repos/kailash/build/.kailash-py-wt/csq14-holistic-<lens>.
Parentruns3exactCIselections onLinux in2separatevenvs andfullconfiguredhooks.
Push consolidated dev+promotion onlyaftergates; readexactheadchecks separately
fromalreadyapprovedmerge. Fivehistoricalstashes anduncertainrefsheld.
