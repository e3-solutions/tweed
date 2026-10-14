# runtime

`controller.py` is a lean controller that doesn't know which task it is running. It handles:

- **Input seal:** an immutable `inputs/SEAL.json` holds the task-field digest and the policy-doc inventory. `prepare` never overwrites it. Per-run outputs go to the separate `runs/<id>/PREFLIGHT.json`, and the seal is checked again after prepare (`check_seal`).
- **Serial provider admission:** one global `provider.lock` (an exclusive flock) is held from before Popen until cleanup, the receipt and settlement are done. Time spent waiting in the queue is recorded and is not charged to the provider timer. If an exception leaves an admission unsettled, it stays in `ADMISSION.json` and blocks every later dispatch until `settle_explicitly` is called.
- **Process handling:** each stage runs in its own process group, which is killed and reaped on timeout. Partial streams are kept. If a stage times out, no terminal is recorded or invented. The receipt records the observed assistant model and the `init.tools` list.
- **Sandbox command:** the profile allows the workspace and the `runtime_read_paths` support reads, then adds literal and subpath read denies for the full `forbidden_runtime_read_paths` list, unchanged. It also denies writes to policy paths. Visible commands run with the task's exact `interpreter`.
- **Continuation:** a continuation is admitted only if the grade is `observed` and either shows an artifact gap, or the stage hit a known settled deadline (Opus identity, the 5 tools, owned process group reaped, stable source). The one-continuation limit is enforced by a durable `O_EXCL` claim file. Feedback is limited to safe `failed_requirements` fields plus status fields.
- **Local module check:** `module_origin` imports the module and checks where it actually loaded from. Binding remains the grader's job.

Run the controls with `python3 runtime/tests/test_controls.py`.

Known gaps:
- **Control 4 skipped:** the sandbox deny control skips because this author tool sandbox does not allow a nested `sandbox_apply`. It must be run outside the tool sandbox before anyone relies on it.
- **No live provider wiring:** the controller is not yet connected to the qualified `runner.py`/MCP tool server. `claude_argv` builds the command line, but no live provider call has been made.
