import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def load_config(config_path: str = "config.yaml") -> dict:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config nicht gefunden: {config_path}")

    with open(path) as f:
        cfg = yaml.safe_load(f)

    # API Key aus Umgebungsvariable übernehmen wenn nicht in config
    if not cfg.get("anthropic_api_key"):
        cfg["anthropic_api_key"] = os.environ.get("ANTHROPIC_API_KEY", "")

    return cfg
