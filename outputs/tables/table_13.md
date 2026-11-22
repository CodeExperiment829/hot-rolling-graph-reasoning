Task graph generation ablation results with the same candidate set.

| Strategy | Cases solved with a budget of 30 | Cases solved with a budget of 60 | Cases solved with a budget of 120 | Cases solved with a budget of 165 | Invalid complete combinations at a budget of 60 |
| --- | --- | --- | --- | --- | --- |
| Checking only complete plans | 9 | 23 | 34 | 72 | 5,418 |
| Without input screening | 15 | 28 | 43 | 72 | 2,612 |
| Without incremental resource pruning | 72 | 72 | 72 | 72 | 1,104 |
| Proposed method | 72 | 72 | 72 | 72 | 0 |

Solved counts use 72 known feasible cases. Invalid combinations cover all 120 cases. Median search time per case in table order (ms): 0.0861, 0.0777, 0.0770, 0.0222.
