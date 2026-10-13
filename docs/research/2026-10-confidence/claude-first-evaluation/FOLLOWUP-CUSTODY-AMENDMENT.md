# Prospective maintenance input custody amendment

Recorded October 13, 2026, after completion and inspection of the main comparison, before any maintenance follow-up model call.

The original `followup.py seal` preparation failed because a first-stage test created a symlink inside `main/execution-scratch`. That temporary execution subtree is not candidate source or an input to the maintenance worker. The original preparation, controller, declaration, control results and first-stage artifacts remain preserved. No follow-up input seal or model call existed at the time of the failure.

The new `followup_v2.py` wrapper excludes only descendants of the exact first-stage `main/execution-scratch` directory from trial artifact inventories. That directory and all its ancestors must still be regular directories. Candidate source, patches, requests, receipts, streams, tool records and grader artifacts remain bound. Symlinks elsewhere are rejected. The wrapper validates all 48 raw receipts against the normalized closure, requires all eight original PR40 sources, and checks the completed strict analysis and its cached CPU rechecks without invoking a grader again.

The eight assigned identities, input source bytes, original and novel requirements, qualified oracle and control bytes, Opus model, medium effort, 120-second limit, one-dollar guard, one-attempt policy and reporting strata are unchanged. Incorrect initial implementations remain included. This amendment changes artifact custody only; it does not select cases using outcomes or amend success metrics. The original qualified oracle and control trees are copied byte for byte.

The new declaration freezes the wrapper and its tests, this amendment, the completed analysis and CPU rechecks, and the original support files before any maintenance call. A separate reviewer checks this boundary and synthetic controls before launch. The resulting follow-up is reported separately from the original main comparison, including initial correctness strata and any unknown outcomes.
