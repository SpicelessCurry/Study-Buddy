"""Configuration manager for Study Buddy RAG application.

Manages application settings, provider credentials, and model paths with
thread-safe access and persistence to ~/.studybuddy/config.json.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Base path for Study Buddy data
STUDYBUDDY_DIR = Path.home() / ".studybuddy"
CONFIG_FILE_PATH = STUDYBUDDY_DIR / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "active_provider": "openai",
    "api_keys": {
        "openai": "",
        "gemini": "",
        "claude": "",
        "ollama": "",
        "llamacpp": "",
    },
    "ollama": {
        "base_url": "http://localhost:11434",
        "model": "llama3",
    },
    "llamacpp": {
        "model_path": "",
    },
    "rag": {
        "embedding_model": "all-MiniLM-L6-v2",
        "chunk_size": 1000,
        "chunk_overlap": 200,
        "top_k": 4,
    },
}


class ConfigManager:
    """Thread-safe configuration manager for Study Buddy settings."""

    def __init__(self, config_path: Path | str | None = None) -> None:
        """Initialize ConfigManager with path to config JSON file.

        Args:
            config_path: Optional custom path to config file. Defaults to
                ~/.studybuddy/config.json.
        """
        self.config_path = Path(config_path) if config_path else CONFIG_FILE_PATH
        self._lock = threading.RLock()
        self._config: dict[str, Any] = {}
        self.load_config()

    def _ensure_dir(self) -> None:
        """Ensure that the parent directory for the config file exists."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create directory {self.config_path.parent}: {e}")
            raise

    def load_config(self) -> dict[str, Any]:
        """Load configuration from disk.

        If the file does not exist or contains invalid JSON, defaults are used
        and written back to disk.

        Returns:
            The loaded configuration dictionary.
        """
        with self._lock:
            self._ensure_dir()
            if not self.config_path.exists():
                logger.info(f"Config file not found at {self.config_path}. Initializing defaults.")
                self._config = json.loads(json.dumps(DEFAULT_CONFIG))
                self.save_config()
                return self._config

            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError("Configuration file root must be a JSON object")

                # Merge with defaults to ensure all keys exist
                merged = json.loads(json.dumps(DEFAULT_CONFIG))
                self._deep_merge(merged, data)
                self._config = merged
            except Exception as e:
                logger.warning(
                    f"Error reading {self.config_path}: {e}. Falling back to default config."
                )
                self._config = json.loads(json.dumps(DEFAULT_CONFIG))
                self.save_config()

            return self._config

    def _deep_merge(self, base: dict[str, Any], update: dict[str, Any]) -> None:
        """Recursively merge update dictionary into base dictionary."""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def save_config(self, config_data: dict[str, Any] | None = None) -> None:
        """Save configuration dictionary to disk.

        Args:
            config_data: Optional configuration dictionary to save. If None,
                current in-memory config is saved.
        """
        with self._lock:
            self._ensure_dir()
            if config_data is not None:
                self._config = json.loads(json.dumps(config_data))

            temp_path = self.config_path.with_suffix(".tmp")
            try:
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(self._config, f, indent=2, ensure_ascii=False)
                # Atomically replace config file
                temp_path.replace(self.config_path)
            except Exception as e:
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except OSError:
                        pass
                logger.error(f"Failed to save configuration to {self.config_path}: {e}")
                raise

    def get_api_key(self, provider: str) -> str | None:
        """Get API key for a given provider.

        Args:
            provider: Provider name (e.g., 'openai', 'gemini', 'claude',
                'ollama', 'llamacpp').

        Returns:
            The API key string or None if not set.
        """
        with self._lock:
            provider_key = provider.lower().strip()
            api_keys = self._config.get("api_keys", {})
            key = api_keys.get(provider_key)
            if key and isinstance(key, str) and key.strip():
                return key.strip()

            # Check environment variables as fallback
            env_var_map = {
                "openai": "OPENAI_API_KEY",
                "gemini": "GEMINI_API_KEY",
                "claude": "ANTHROPIC_API_KEY",
            }
            env_var = env_var_map.get(provider_key)
            if env_var and os.getenv(env_var):
                return os.getenv(env_var)

            return None

    def set_api_key(self, provider: str, key: str) -> None:
        """Set API key for a given provider.

        Args:
            provider: Provider name.
            key: The API key value.
        """
        with self._lock:
            provider_key = provider.lower().strip()
            if "api_keys" not in self._config:
                self._config["api_keys"] = {}
            self._config["api_keys"][provider_key] = key.strip()
            self.save_config()

    def get_active_provider(self) -> str | None:
        """Get the name of the currently active provider.

        Returns:
            Active provider name string or None.
        """
        with self._lock:
            return self._config.get("active_provider")

    def set_active_provider(self, name: str) -> None:
        """Set the active provider.

        Args:
            name: Provider name to activate.
        """
        with self._lock:
            self._config["active_provider"] = name.lower().strip()
            self.save_config()

    def get_ollama_settings(self) -> dict[str, str]:
        """Get Ollama settings (base_url and model)."""
        with self._lock:
            ollama = self._config.get("ollama", {})
            return {
                "base_url": ollama.get("base_url", "http://localhost:11434"),
                "model": ollama.get("model", ""),
            }

    def set_ollama_settings(self, base_url: str | None = None, model: str | None = None) -> None:
        """Set Ollama configuration settings."""
        with self._lock:
            if "ollama" not in self._config:
                self._config["ollama"] = {}
            if base_url is not None:
                self._config["ollama"]["base_url"] = base_url.strip()
            if model is not None:
                self._config["ollama"]["model"] = model.strip()
            self.save_config()

    def get_llamacpp_settings(self) -> dict[str, str]:
        """Get LlamaCpp settings (model_path)."""
        with self._lock:
            llamacpp = self._config.get("llamacpp", {})
            return {
                "model_path": llamacpp.get("model_path", ""),
            }

    def set_llamacpp_settings(self, model_path: str) -> None:
        """Set LlamaCpp model path."""
        with self._lock:
            if "llamacpp" not in self._config:
                self._config["llamacpp"] = {}
            self._config["llamacpp"]["model_path"] = model_path.strip()
            self.save_config()

    def is_provider_configured(self, provider: str) -> bool:
        """Check if a specific provider is configured.

        Args:
            provider: Provider name to check.

        Returns:
            True if provider has necessary credentials/paths configured.
        """
        with self._lock:
            p = provider.lower().strip()
            if p in ("openai", "gemini", "claude"):
                key = self.get_api_key(p)
                return bool(key and key.strip())
            elif p == "ollama":
                ollama = self._config.get("ollama", {})
                # Ollama is configured if a base_url is present (default localhost) and model is defined
                # or base_url is specified
                return bool(ollama.get("base_url") and ollama.get("model"))
            elif p == "llamacpp":
                llamacpp = self._config.get("llamacpp", {})
                model_path = llamacpp.get("model_path", "")
                return bool(model_path and model_path.strip())
            return False

    def is_configured(self) -> bool:
        """Check if at least one provider is set up.

        Returns:
            True if at least one provider has valid configuration.
        """
        with self._lock:
            supported_providers = ["openai", "gemini", "claude", "ollama", "llamacpp"]
            for provider in supported_providers:
                if self.is_provider_configured(provider):
                    return True
            return False

    def get_all_settings(self) -> dict[str, Any]:
        """Get a copy of all current settings.

        Returns:
            A deep copy of the configuration dictionary.
        """
        with self._lock:
            return json.loads(json.dumps(self._config))

    def update_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Update settings with the provided dictionary and persist changes.

        Args:
            settings: Dictionary of configuration updates.

        Returns:
            The updated configuration dictionary.
        """
        with self._lock:
            self._deep_merge(self._config, settings)
            self.save_config()
            return self.get_all_settings()


# Global default instance
config = ConfigManager()
