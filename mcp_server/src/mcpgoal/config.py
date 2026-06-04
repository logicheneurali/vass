from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel, Field


class ToolACL(BaseModel):
    whitelist: List[str] = Field(default_factory=list)
    blacklist: List[str] = Field(default_factory=list)


class ServerConfig(BaseModel):
    tools: Dict[str, ToolACL]
    log_dir: str = "LOG"
    allowed_commands: List[str] = Field(default_factory=lambda: ["ping", "ipconfig", "whoami", "echo"])
    allowed_root: str = "../Allowed_root"


def load_config(path: Optional[Path] = None) -> ServerConfig:
    if path is None:
        path = Path(__file__).resolve().parent.parent.parent / "config" / "tools.yaml"
    if not path.exists():
        return ServerConfig(tools={})
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return ServerConfig.model_validate(raw)
