import asyncio
import shlex


async def execute(command: str, allowed_commands: list[str] | None = None, timeout: float = 30.0) -> str:
    try:
        if isinstance(timeout, str):
            timeout = float(timeout) if timeout.strip() else 30.0
    except ValueError:
        timeout = 30.0
    parts = shlex.split(command)
    if not parts:
        raise ValueError("Empty command")

    if allowed_commands:
        base = parts[0].lower()
        if not any(base == allowed or base.endswith(f"\\{allowed}") for allowed in allowed_commands):
            raise PermissionError(f"Command not allowed: {parts[0]}")

    try:
        proc = await asyncio.create_subprocess_exec(
            *parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = ""
        if stdout:
            output += stdout.decode("utf-8", errors="replace")
        if stderr:
            output += "\n[stderr]\n" + stderr.decode("utf-8", errors="replace")
        return output or f"Process exited with code {proc.returncode}"
    except asyncio.TimeoutError:
        proc.kill()
        raise TimeoutError(f"Command timed out after {timeout}s")
