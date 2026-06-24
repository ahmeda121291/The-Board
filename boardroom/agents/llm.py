"""Thin Anthropic wrapper.

Two non-negotiables:
  1. It returns TEXT only. Callers keep all numbers authoritative; nothing the
     LLM says can overwrite a computed field.
  2. It degrades gracefully. With no ANTHROPIC_API_KEY (or the SDK absent), the
     loop still runs — agents fall back to deterministic templated prose — so
     the system is testable end-to-end in dry-run without spending tokens.
"""

from __future__ import annotations

from boardroom.config import get_settings


class LLM:
    def __init__(self, model: str | None = None) -> None:
        self._settings = get_settings()
        self.model = model or self._settings.llm_model
        self._client = None

    @property
    def available(self) -> bool:
        return self._settings.anthropic_api_key is not None

    def _ensure_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self._settings.require_anthropic())
        return self._client

    def ping(self) -> tuple[bool, str]:
        """Live check: actually call the model once and return (ok, detail).

        Unlike ``complete``, this does NOT swallow the error — so ``doctor`` can
        show exactly why the LLM layer is falling back to templated prose.
        """
        if not self.available:
            return False, "no ANTHROPIC_API_KEY"
        try:
            client = self._ensure_client()
            client.messages.create(
                model=self.model,
                max_tokens=5,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True, f"model {self.model} OK"
        except Exception as e:
            return False, f"{type(e).__name__}: {str(e)[:180]}"

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 600,
        temperature: float = 0.3,
    ) -> str:
        """Return the model's text, or "" if the LLM is unavailable.

        Callers MUST treat "" as "use the deterministic fallback" — never as an
        error. The system is designed to run without the brain attached.
        """
        if not self.available:
            return ""
        try:
            client = self._ensure_client()
            resp = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            parts = [block.text for block in resp.content if getattr(block, "type", "") == "text"]
            return "\n".join(parts).strip()
        except Exception:
            # Never let a brain hiccup take down the deterministic spine.
            return ""
