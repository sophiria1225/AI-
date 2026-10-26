# P125 figure: all eight conditions

The upper panel shows whole-job logical input plus output tokens, including all roles, summaries, failures and recovery. Every predefined task and policy is present, with its audited official outcome. Hatched bars denote known subtotals with incomplete usage. An x marked "Not measured" is missing data, not zero cost. Contract stops retain the independent evaluation result and are explicitly marked.

The lower panel shows dispatched API requests and separately labels partial hits. A hit is not a net saved request: ordinary complete cache reuse and later full reads can offset it. Neither API counts nor control bytes are model tokens. The all-condition and common-success totals, original adoption criteria and audit-error count are retained in figure_data.json.

This is one known-task development comparison with a single common checkpoint. It does not establish statistical non-inferiority, general quality preservation, superiority over rolling-separate checkpoints, or technical novelty. No result was selected or omitted according to outcome. The renderer only reads closed public audit and server artifacts plus their hash-bound material bundle. It makes no model, API, tokenizer or evaluator calls.
