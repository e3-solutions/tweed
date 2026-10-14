"""V2 executable-tool runtime: isolated scratch/home outside actor checkout.

Only the trusted command-service callback changes. MCP startup, authentication,
source/tool schemas and frozen adapters stay unchanged. Never alter process-wide
environment or global subprocess functions. Each stage gets a private scratch;
executed code can access its workspace, declared runtimes and that scratch only.
"""
from __future__ import annotations
from pathlib import Path
from types import FunctionType


def regular_directory(path):
    path = Path(path).absolute()
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError('Runtime directory may not contain symlink components')
    if path.exists() and not path.is_dir():
        raise ValueError('Runtime path must be a directory')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path.resolve()


def service_wrapper(module):
    original = module.service_commands
    if getattr(original, '_v2_isolated_runtime', False):
        return original
    original_env = module.safe_env

    def isolated_env(workspace, temporary):
        environment = original_env(workspace, temporary)
        # This is a fresh child environment, not the user's shell/application
        # HOME. No inherited environment or existing user directory is copied.
        environment['HOME'] = str(regular_directory(Path(temporary) / 'home'))
        return environment

    private_globals = {**original.__globals__, 'safe_env': isolated_env}
    isolated = FunctionType(original.__code__, private_globals, original.__name__, original.__defaults__, original.__closure__)
    isolated.__kwdefaults__ = original.__kwdefaults__

    def serve(control, workspace, temporary, readonly, deadline):
        control = regular_directory(control)
        workspace = Path(workspace).resolve()
        scratch = control / 'execution-scratch'
        if scratch.is_relative_to(workspace):
            raise ValueError('Executable scratch must be outside the actor checkout')
        scratch = regular_directory(scratch)
        regular_directory(scratch / 'home')
        # The unchanged callback builds the actual sandbox with this argument
        # and passes this same argument to the fresh safe child environment.
        return isolated(control, workspace, scratch, readonly, deadline)

    serve._v2_isolated_runtime = True
    return serve


def install(base, backend):
    for module in (base, backend.runner):
        module.service_commands = service_wrapper(module)
