from pydantic import BaseModel
import yaml
from pathlib import Path
from typing import Optional
from functools import lru_cache

class LlmConfig(BaseModel):
    model: str

class AppConfig(BaseModel):
    llm: LlmConfig

@lru_cache(maxsize=1)
def load_config() -> AppConfig:
    path = Path(__file__).parent.parent / "config.yaml"
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return AppConfig(**data)
    except FileNotFoundError:
        raise RuntimeError(f"Config file not found: {path}")
    except Exception as e:
        raise RuntimeError(f"Failed to load config: {e}")
