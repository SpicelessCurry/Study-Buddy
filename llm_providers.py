"""LLM provider abstraction layer for Study Buddy RAG application.

Defines an abstract base class LLMProvider and concrete implementations for:
- OpenAI (OpenAIProvider)
- Google Gemini (GeminiProvider)
- Anthropic Claude (ClaudeProvider)
- Ollama (OllamaProvider)
- LlamaCpp (LlamaCppProvider)

Includes custom LLMError and a factory function get_provider().
"""

from __future__ import annotations

import logging
import os
import threading
from abc import ABC, abstractmethod
from collections.abc import Generator
from typing import Any

from config import ConfigManager

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Custom exception raised for all LLM provider errors."""

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        original_error: Exception | None = None,
    ) -> None:
        """Initialize LLMError with user-friendly message and optional context.

        Args:
            message: User-friendly error message.
            provider: Name of the provider that encountered the error.
            original_error: The underlying exception if available.
        """
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.original_error = original_error

    def __str__(self) -> str:
        if self.provider:
            return f"[{self.provider}] {self.message}"
        return self.message


class LLMProvider(ABC):
    """Abstract base class for all LLM providers."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> str:
        """Generate a complete text response from the LLM.

        Args:
            prompt: User message / prompt.
            system_prompt: Optional system prompt / instructions.
            max_tokens: Maximum tokens in response.

        Returns:
            Generated response string.

        Raises:
            LLMError: If generation fails.
        """
        pass

    @abstractmethod
    def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> Generator[str, None, None]:
        """Stream response chunks from the LLM.

        Args:
            prompt: User message / prompt.
            system_prompt: Optional system prompt / instructions.
            max_tokens: Maximum tokens in response.

        Yields:
            Chunks of response text.

        Raises:
            LLMError: If streaming fails.
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Return provider display name."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is configured and available for inference."""
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider using official openai library."""

    DEFAULT_MODEL = "gpt-4o"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        base_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key. Defaults to OPENAI_API_KEY env var.
            model: OpenAI model name (default: gpt-4o).
            base_url: Optional custom API base URL.
            **kwargs: Additional parameters passed to API calls.
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or ""
        self.model = model or self.DEFAULT_MODEL
        self.base_url = base_url
        self.extra_kwargs = kwargs

    def get_name(self) -> str:
        return "OpenAI"

    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            import openai  # noqa: F401

            return True
        except ImportError:
            return False

    def _get_client(self) -> Any:
        try:
            import openai
        except ImportError as e:
            raise LLMError(
                "The 'openai' library is not installed. Run 'pip install openai'.",
                provider=self.get_name(),
                original_error=e,
            )

        if not self.api_key:
            raise LLMError(
                "OpenAI API key is missing. Please configure it in Settings.",
                provider=self.get_name(),
            )

        kwargs: dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return openai.OpenAI(**kwargs)

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> str:
        client = self._get_client()

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                stream=False,
                **self.extra_kwargs,
            )
            choices = response.choices
            if choices and choices[0].message:
                return choices[0].message.content or ""
            return ""
        except LLMError:
            raise
        except Exception as e:
            logger.error(f"OpenAI generate error: {e}")
            raise LLMError(
                f"OpenAI error: {getattr(e, 'message', str(e))}",
                provider=self.get_name(),
                original_error=e,
            )

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> Generator[str, None, None]:
        client = self._get_client()

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            stream = client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                stream=True,
                **self.extra_kwargs,
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except LLMError:
            raise
        except Exception as e:
            logger.error(f"OpenAI generate_stream error: {e}")
            raise LLMError(
                f"OpenAI streaming error: {getattr(e, 'message', str(e))}",
                provider=self.get_name(),
                original_error=e,
            )


class GeminiProvider(LLMProvider):
    """Google Gemini LLM provider using Google Generative Language REST API and SDK."""

    DEFAULT_MODEL = "gemini-flash-lite-latest"
    FALLBACK_MODELS = [
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
        "gemini-flash-latest",
        "gemini-3.1-flash-lite",
        "gemini-3.8-flash",
    ]

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        **kwargs: Any,
    ) -> None:
        """Initialize Gemini provider.

        Args:
            api_key: Gemini API key. Defaults to GEMINI_API_KEY or GOOGLE_API_KEY.
            model: Gemini model name (default: gemini-flash-lite-latest).
            **kwargs: Additional parameters passed to API calls.
        """
        self.api_key = (
            api_key
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
            or ""
        )
        # Normalize model name: map deprecated or congested names to stable latest models
        chosen_model = model or self.DEFAULT_MODEL
        if chosen_model in ("gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"):
            chosen_model = self.DEFAULT_MODEL
        self.model = chosen_model
        self.extra_kwargs = kwargs

    def get_name(self) -> str:
        return "Gemini"

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def _get_models_to_try(self) -> list[str]:
        models = [self.model]
        for fb in self.FALLBACK_MODELS:
            if fb not in models:
                models.append(fb)
        return models

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> str:
        if not self.is_available():
            raise LLMError(
                "Gemini API key is missing. Please configure it in Settings.",
                provider=self.get_name(),
            )

        import requests

        models_to_try = self._get_models_to_try()
        last_error = None

        for model_name in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
            payload: dict[str, Any] = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": max_tokens},
            }
            if system_prompt:
                payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

            try:
                res = requests.post(url, json=payload, timeout=45)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "")
                    return ""
                elif res.status_code in (404, 429, 503):
                    err_msg = res.json().get("error", {}).get("message", res.text)
                    logger.warning(f"Gemini model '{model_name}' returned {res.status_code}: {err_msg}. Trying fallback...")
                    last_error = f"Model {model_name}: {err_msg}"
                    continue
                else:
                    err_msg = res.json().get("error", {}).get("message", res.text)
                    raise LLMError(f"Gemini error ({res.status_code}): {err_msg}", provider=self.get_name())
            except requests.RequestException as e:
                logger.warning(f"Gemini request timeout/error with model '{model_name}': {e}. Trying fallback...")
                last_error = str(e)
                continue

        # If all REST attempts failed, try SDK as final fallback if installed
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key, transport="rest")
            model = genai.GenerativeModel(self.DEFAULT_MODEL)
            response = model.generate_content(prompt)
            return response.text or ""
        except Exception:
            pass

        raise LLMError(
            f"All Gemini models failed. Last error: {last_error}",
            provider=self.get_name(),
        )

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> Generator[str, None, None]:
        if not self.api_key:
            raise LLMError(
                "Gemini API key is missing. Please configure it in Settings.",
                provider=self.get_name(),
            )

        import requests
        import json

        models_to_try = self._get_models_to_try()
        last_error = None
        streamed_any = False

        for model_name in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:streamGenerateContent?alt=sse&key={self.api_key}"
            payload: dict[str, Any] = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": max_tokens},
            }
            if system_prompt:
                payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

            try:
                res = requests.post(url, json=payload, stream=True, timeout=30)
                if res.status_code == 200:
                    for line in res.iter_lines():
                        if not line:
                            continue
                        decoded = line.decode("utf-8")
                        if decoded.startswith("data: "):
                            try:
                                chunk_json = json.loads(decoded[6:])
                                candidates = chunk_json.get("candidates", [])
                                if candidates:
                                    parts = candidates[0].get("content", {}).get("parts", [])
                                    if parts:
                                        text_chunk = parts[0].get("text", "")
                                        if text_chunk:
                                            streamed_any = True
                                            yield text_chunk
                            except Exception:
                                continue
                    if streamed_any:
                        return
                elif res.status_code in (404, 429, 503):
                    err_msg = res.json().get("error", {}).get("message", res.text)
                    logger.warning(f"Gemini streaming model '{model_name}' returned {res.status_code}: {err_msg}. Trying fallback...")
                    last_error = f"Model {model_name}: {err_msg}"
                    continue
                else:
                    err_msg = res.json().get("error", {}).get("message", res.text)
                    raise LLMError(f"Gemini streaming error ({res.status_code}): {err_msg}", provider=self.get_name())
            except requests.RequestException as e:
                if streamed_any:
                    return
                logger.warning(f"Gemini streaming request error with model '{model_name}': {e}. Trying fallback...")
                last_error = str(e)
                continue

        if not streamed_any:
            raise LLMError(
                f"Gemini streaming failed for all models. Last error: {last_error}",
                provider=self.get_name(),
            )


class ClaudeProvider(LLMProvider):
    """Anthropic Claude LLM provider using official anthropic SDK."""

    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        base_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize Claude provider.

        Args:
            api_key: Anthropic API key. Defaults to ANTHROPIC_API_KEY env var.
            model: Claude model name (default: claude-sonnet-4-20250514).
            base_url: Optional custom API base URL.
            **kwargs: Additional parameters passed to API calls.
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY") or ""
        self.model = model or self.DEFAULT_MODEL
        self.base_url = base_url
        self.extra_kwargs = kwargs

    def get_name(self) -> str:
        return "Claude"

    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            import anthropic  # noqa: F401

            return True
        except ImportError:
            return False

    def _get_client(self) -> Any:
        try:
            import anthropic
        except ImportError as e:
            raise LLMError(
                "The 'anthropic' library is not installed. Run 'pip install anthropic'.",
                provider=self.get_name(),
                original_error=e,
            )

        if not self.api_key:
            raise LLMError(
                "Anthropic API key is missing. Please configure it in Settings.",
                provider=self.get_name(),
            )

        kwargs: dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return anthropic.Anthropic(**kwargs)

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> str:
        client = self._get_client()

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            **self.extra_kwargs,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        try:
            response = client.messages.create(**kwargs)
            parts = [block.text for block in response.content if hasattr(block, "text")]
            return "".join(parts)
        except LLMError:
            raise
        except Exception as e:
            logger.error(f"Claude generate error: {e}")
            raise LLMError(
                f"Claude error: {getattr(e, 'message', str(e))}",
                provider=self.get_name(),
                original_error=e,
            )

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> Generator[str, None, None]:
        client = self._get_client()

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            **self.extra_kwargs,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        try:
            with client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    yield text
        except LLMError:
            raise
        except Exception as e:
            logger.error(f"Claude generate_stream error: {e}")
            raise LLMError(
                f"Claude streaming error: {getattr(e, 'message', str(e))}",
                provider=self.get_name(),
                original_error=e,
            )


class OllamaProvider(LLMProvider):
    """Local Ollama LLM provider using ollama library."""

    DEFAULT_MODEL = "llama3"
    DEFAULT_BASE_URL = "http://localhost:11434"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        **kwargs: Any,
    ) -> None:
        """Initialize Ollama provider.

        Args:
            model: Ollama model name (default: llama3).
            base_url: Ollama daemon URL (default: http://localhost:11434).
            **kwargs: Additional parameters passed to API calls.
        """
        self.model = model or self.DEFAULT_MODEL
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.extra_kwargs = kwargs

    def get_name(self) -> str:
        return "Ollama"

    def is_available(self) -> bool:
        try:
            import ollama

            client = ollama.Client(host=self.base_url)
            client.list()
            return True
        except Exception:
            return False

    def _get_client(self) -> Any:
        try:
            import ollama
        except ImportError as e:
            raise LLMError(
                "The 'ollama' library is not installed. Run 'pip install ollama'.",
                provider=self.get_name(),
                original_error=e,
            )

        return ollama.Client(host=self.base_url)

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> str:
        client = self._get_client()

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        options: dict[str, Any] = {}
        if max_tokens:
            options["num_predict"] = max_tokens
        options.update(self.extra_kwargs.get("options", {}))

        try:
            response = client.chat(
                model=self.model,
                messages=messages,
                options=options or None,
            )
            msg = response.get("message", {})
            return msg.get("content", "")
        except LLMError:
            raise
        except Exception as e:
            logger.error(f"Ollama generate error: {e}")
            raise LLMError(
                f"Ollama error: {getattr(e, 'message', str(e))}. Ensure Ollama is running at {self.base_url}.",
                provider=self.get_name(),
                original_error=e,
            )

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> Generator[str, None, None]:
        client = self._get_client()

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        options: dict[str, Any] = {}
        if max_tokens:
            options["num_predict"] = max_tokens
        options.update(self.extra_kwargs.get("options", {}))

        try:
            stream = client.chat(
                model=self.model,
                messages=messages,
                stream=True,
                options=options or None,
            )
            for chunk in stream:
                content = chunk.get("message", {}).get("content", "")
                if content:
                    yield content
        except LLMError:
            raise
        except Exception as e:
            logger.error(f"Ollama generate_stream error: {e}")
            raise LLMError(
                f"Ollama streaming error: {getattr(e, 'message', str(e))}. Ensure Ollama is running at {self.base_url}.",
                provider=self.get_name(),
                original_error=e,
            )


class LlamaCppProvider(LLMProvider):
    """Llama.cpp provider supporting both local GGUF model files and llama-server HTTP endpoints."""

    def __init__(
        self,
        model_path: str | None = None,
        n_ctx: int = 4096,
        **kwargs: Any,
    ) -> None:
        """Initialize LlamaCpp provider.

        Args:
            model_path: Absolute path to local .gguf file OR URL of running llama-server (e.g. http://localhost:8080).
            n_ctx: Context window size (default: 4096).
            **kwargs: Additional parameters passed to Llama initialization.
        """
        clean_path = (model_path or "").strip().strip('"').strip("'")
        self.model_path = clean_path
        self.n_ctx = n_ctx
        self.extra_kwargs = kwargs
        self._llm: Any = None
        self._lock = threading.RLock()

    def get_name(self) -> str:
        return "LlamaCpp"

    def _is_http_endpoint(self) -> bool:
        if not self.model_path:
            return False
        return self.model_path.startswith("http://") or self.model_path.startswith("https://")

    def _get_resolved_file_path(self) -> str:
        if not self.model_path or self._is_http_endpoint():
            return ""
        return os.path.abspath(os.path.expanduser(os.path.expandvars(self.model_path)))

    def is_available(self) -> bool:
        if not self.model_path:
            return False
        if self._is_http_endpoint():
            return True
        resolved = self._get_resolved_file_path()
        if not os.path.isfile(resolved):
            return False
        try:
            import llama_cpp  # noqa: F401
            return True
        except ImportError:
            return False

    def _load_model(self) -> Any:
        with self._lock:
            if self._llm is not None:
                return self._llm

            if not self.model_path:
                raise LLMError(
                    "Model path is not specified for LlamaCpp. Please enter your .gguf file path or server URL in Settings.",
                    provider=self.get_name(),
                )

            resolved = self._get_resolved_file_path()
            if not os.path.isfile(resolved):
                raise LLMError(
                    f"GGUF model file not found at: '{resolved}'. Please verify the path in Settings.",
                    provider=self.get_name(),
                )

            try:
                from llama_cpp import Llama
            except ImportError as e:
                raise LLMError(
                    "The 'llama-cpp-python' library is not installed. Run:\n"
                    "pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu",
                    provider=self.get_name(),
                    original_error=e,
                )

            try:
                self._llm = Llama(
                    model_path=resolved,
                    n_ctx=self.n_ctx,
                    verbose=False,
                    **self.extra_kwargs,
                )
                return self._llm
            except Exception as e:
                logger.error(f"Failed to load GGUF model from {resolved}: {e}")
                raise LLMError(
                    f"Failed to load GGUF model: {getattr(e, 'message', str(e))}",
                    provider=self.get_name(),
                    original_error=e,
                )

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> str:
        if not self.model_path:
            raise LLMError(
                "LlamaCpp model path or server URL is not configured. Please open Settings.",
                provider=self.get_name(),
            )

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # If HTTP llama-server endpoint
        if self._is_http_endpoint():
            import requests
            base_url = self.model_path.rstrip("/")
            endpoint = f"{base_url}/v1/chat/completions"
            payload = {
                "messages": messages,
                "max_tokens": max_tokens,
                "stream": False,
            }
            try:
                res = requests.post(endpoint, json=payload, timeout=60)
                if res.status_code == 200:
                    data = res.json()
                    choices = data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "") or ""
                    return ""
                else:
                    raise LLMError(f"llama-server error ({res.status_code}): {res.text}", provider=self.get_name())
            except requests.RequestException as e:
                raise LLMError(f"Cannot connect to llama-server at {base_url}: {e}", provider=self.get_name(), original_error=e)

        # Local GGUF file via llama-cpp-python
        llm = self._load_model()
        try:
            response = llm.create_chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                stream=False,
            )
            choices = response.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "") or ""
            return ""
        except LLMError:
            raise
        except Exception as e:
            logger.error(f"LlamaCpp generate error: {e}")
            raise LLMError(
                f"LlamaCpp error: {getattr(e, 'message', str(e))}",
                provider=self.get_name(),
                original_error=e,
            )

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
    ) -> Generator[str, None, None]:
        if not self.model_path:
            raise LLMError(
                "LlamaCpp model path or server URL is not configured. Please open Settings.",
                provider=self.get_name(),
            )

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # If HTTP llama-server endpoint
        if self._is_http_endpoint():
            import requests
            import json
            base_url = self.model_path.rstrip("/")
            endpoint = f"{base_url}/v1/chat/completions"
            payload = {
                "messages": messages,
                "max_tokens": max_tokens,
                "stream": True,
            }
            try:
                res = requests.post(endpoint, json=payload, stream=True, timeout=60)
                if res.status_code == 200:
                    for line in res.iter_lines():
                        if not line:
                            continue
                        decoded = line.decode("utf-8")
                        if decoded.startswith("data: "):
                            raw_data = decoded[6:].strip()
                            if raw_data == "[DONE]":
                                break
                            try:
                                chunk_json = json.loads(raw_data)
                                choices = chunk_json.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content")
                                    if content:
                                        yield content
                            except Exception:
                                continue
                    return
                else:
                    raise LLMError(f"llama-server streaming error ({res.status_code}): {res.text}", provider=self.get_name())
            except requests.RequestException as e:
                raise LLMError(f"Cannot connect to llama-server at {base_url}: {e}", provider=self.get_name(), original_error=e)

        # Local GGUF file via llama-cpp-python
        llm = self._load_model()
        try:
            stream = llm.create_chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                stream=True,
            )
            for chunk in stream:
                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        yield content
        except LLMError:
            raise
        except Exception as e:
            logger.error(f"LlamaCpp generate_stream error: {e}")
            raise LLMError(
                f"LlamaCpp streaming error: {getattr(e, 'message', str(e))}",
                provider=self.get_name(),
                original_error=e,
            )


def get_provider(
    provider_name: str,
    config: dict[str, Any] | ConfigManager | None = None,
) -> LLMProvider:
    """Factory function to instantiate an LLM provider based on name and config.

    Args:
        provider_name: Name of the provider ('openai', 'gemini', 'claude',
            'ollama', 'llamacpp').
        config: Configuration dictionary (or ConfigManager instance) containing
            keys such as api_key, model, base_url, model_path.

    Returns:
        Configured LLMProvider instance.

    Raises:
        LLMError: If the provider name is unknown or unsupported.
    """
    if not provider_name or not isinstance(provider_name, str):
        raise LLMError("A valid provider_name string must be specified.")

    norm_name = (
        provider_name.strip()
        .lower()
        .replace("_", "")
        .replace("-", "")
        .replace(".", "")
    )

    # Extract dict configuration
    cfg: dict[str, Any] = {}
    if config is not None:
        if isinstance(config, dict):
            cfg = dict(config)
        elif isinstance(config, ConfigManager) or hasattr(config, "get_all_settings"):
            cfg = config.get_all_settings()
        elif hasattr(config, "to_dict"):
            cfg = config.to_dict()

    # If config was empty or missing keys, fall back to ConfigManager if available
    if not cfg:
        try:
            cm = ConfigManager()
            if norm_name in ("openai", "gemini", "claude"):
                key = cm.get_api_key(norm_name)
                if key:
                    cfg["api_key"] = key
            elif norm_name == "ollama":
                cfg.update(cm.get_ollama_settings())
            elif norm_name in ("llamacpp", "llama"):
                cfg.update(cm.get_llamacpp_settings())
        except Exception as e:
            logger.debug(f"Could not load fallback config from ConfigManager: {e}")

    if norm_name == "openai":
        api_key = cfg.get("api_key")
        model = cfg.get("model") or OpenAIProvider.DEFAULT_MODEL
        base_url = cfg.get("base_url")
        return OpenAIProvider(api_key=api_key, model=model, base_url=base_url)

    elif norm_name in ("gemini", "google", "googlegemini"):
        api_key = cfg.get("api_key")
        model = cfg.get("model") or GeminiProvider.DEFAULT_MODEL
        return GeminiProvider(api_key=api_key, model=model)

    elif norm_name in ("claude", "anthropic"):
        api_key = cfg.get("api_key")
        model = cfg.get("model") or ClaudeProvider.DEFAULT_MODEL
        base_url = cfg.get("base_url")
        return ClaudeProvider(api_key=api_key, model=model, base_url=base_url)

    elif norm_name == "ollama":
        model = cfg.get("model") or OllamaProvider.DEFAULT_MODEL
        base_url = cfg.get("base_url") or OllamaProvider.DEFAULT_BASE_URL
        return OllamaProvider(model=model, base_url=base_url)

    elif norm_name in ("llamacpp", "llama", "gguf"):
        model_path = cfg.get("model_path") or cfg.get("llama_model_path") or cfg.get("llamacpp_model_path")
        n_ctx = cfg.get("n_ctx", 4096)
        return LlamaCppProvider(model_path=model_path, n_ctx=n_ctx)

    else:
        raise LLMError(
            f"Unsupported LLM provider: '{provider_name}'. "
            "Supported providers: openai, gemini, claude, ollama, llamacpp."
        )
