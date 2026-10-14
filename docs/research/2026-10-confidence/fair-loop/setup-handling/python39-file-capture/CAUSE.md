# Captured stdio metadata admission correction

This is a pre-inference infrastructure correction. The original failed `study/` preparation and adapter bytes are retained. No task model request occurred during diagnosis or qualification. The task interpreter, task sources, owner fixtures, evaluator, candidate and Opus core were unchanged by this correction.

Under the identical composed command-child sandbox, Python 3.9 worked with pipe stdout/stderr. With captured regular files, `sys.stdout` and `sys.stderr` became `None`: `os.fstat(1)` and `os.fstat(2)` failed with EPERM. A scratch-file witness retained these observations without requiring the broken streams. The executing interpreter PID equaled the Popen PID, so the proposed launcher-child race was not the cause. Direct `os.write` on the inherited descriptors worked, while ordinary `print` output was absent and unittest exited 1 without diagnostics.

The native mechanical adapter now appends a `file-read-metadata` allowance for only the exact per-command stdout and stderr custody files before calling the unchanged qualified bounded-process helper. It grants no file content reads, no custody writes, and no permission for the whole control tree. Output capture remains outside the actor checkout. Parent process cleanup and source/policy rules are unchanged.

The requalified actual CSV clone passed its immutable visible baseline through the five-tool MCP server and the same command-service sandbox: exit 0, stdout 91 bytes, stderr 98 bytes. All nine existing registered runtime-source reads were denied; outside reads/writes, policy writes and network access were denied; the source-tail command succeeded; source inventory was unchanged and the MCP process group was absent after cleanup. A separate executed-child probe against the exact metadata-allowed stdout/stderr files denied both O_RDONLY and O_WRONLY access and left their hashes unchanged. Root subsequently prepared `study-v2` and all four actual mounts passed this route, including both parser mounts.

Adapter before: `ec8b8132d4f2684d3e109af6f7cfe3a8524f8eac769e976bf1c8a6aab1591997`.
Adapter after: `99024867cec32e7acf5771f882337aa58db6f20b836ccee2ef8a9da99c228fbb`.

Receipts here include `queries.json`, `controlled-pipe-queries.json`, `controlled-file-fd-queries.json`, `controlled-stdio-queries.json`, `stdio-cause.json`, `exact-custody-content-denial.json`, `AMENDMENT-BEFORE.json`, `AMENDMENT-AFTER.json`, and `requalified/control/receipt.json`. Raw paths and process identifiers in private receipts must be redacted from public metadata. These CPU controls are transport evidence, not model repairs or task outcomes.
