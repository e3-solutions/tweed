"""V2-only direct-child reaping before original-group escalation.

On macOS, killpg(SIGKILL) can return EPERM when the group contains only an
unreaped zombie direct child. Reap that child before escalation. Still send
SIGKILL to its original group to stop surviving SIGTERM-ignoring descendants.
Do not suppress permission failures or claim detached-descendant containment.
The first registered process helper and its receipts remain unchanged.
"""
import os
import signal
import time


def cleanup_group(process):
    if getattr(process, '_hybrid_group_cleanup_complete', False):
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    else:
        time.sleep(.05)
    # poll uses waitpid on our direct child. A zombie cannot execute/write;
    # reaping it does not imply that other group members have stopped.
    process.poll()
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if process.poll() is None:
        process.wait(timeout=2)
    process._hybrid_group_cleanup_complete = True


def install(process_module):
    """Replace only this imported V2 controller's cleanup implementation."""
    process_module.cleanup_group = cleanup_group
