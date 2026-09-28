"""Motor del agente: investiga al prospecto y genera propuesta + correo."""

from __future__ import annotations

import json
import sys

import anthropic

from .prompts import (
    PROPOSAL_SYSTEM,
    RESEARCH_SYSTEM,
    proposal_prompt,
    research_prompt,
)
from .schema import PROPOSAL_SCHEMA

MODEL = "claude-opus-5"
BETAS = ["server-side-fallback-2026-07-01"]
WEB_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 12},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 12},
]
MAX_RESTARTS = 5


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _text(message) -> str:
    return "".join(b.text for b in message.content if b.type == "text")


def _check_refusal(message, fase: str) -> None:
    if message.stop_reason == "refusal":
        detalle = getattr(message, "stop_details", None)
        raise RuntimeError(f"El modelo se negó en la fase de {fase}: {detalle}")


def investigar(client: anthropic.Anthropic, target: str, contexto: str | None) -> str:
    """Fase 1: investigación web del prospecto (sitio, redes, reseñas, competencia)."""
    messages = [{"role": "user", "content": research_prompt(target, contexto)}]
    for _ in range(MAX_RESTARTS + 1):
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=64000,
            betas=BETAS,
            fallbacks="default",
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            system=RESEARCH_SYSTEM,
            tools=WEB_TOOLS,
            messages=messages,
        ) as stream:
            for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "server_tool_use":
                        _log(f"  🔎 {block.name}…")
            message = stream.get_final_message()

        _check_refusal(message, "investigación")
        if message.stop_reason != "pause_turn":
            return _text(message)
        # Las herramientas web llegaron a su límite de iteraciones: continuar el turno.
        messages.append({"role": "assistant", "content": message.content})
    raise RuntimeError("La investigación no terminó tras varios reintentos.")


def proponer(client: anthropic.Anthropic, research: str, empresa_yaml: str, target: str) -> dict:
    """Fase 2: propuesta a medida + correo + secuencia de seguimiento (JSON estructurado)."""
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=64000,
        betas=BETAS,
        fallbacks="default",
        thinking={"type": "adaptive"},
        output_config={
            "effort": "high",
            "format": {"type": "json_schema", "schema": PROPOSAL_SCHEMA},
        },
        system=PROPOSAL_SYSTEM,
        messages=[{
            "role": "user",
            "content": proposal_prompt(research, empresa_yaml, target),
        }],
    ) as stream:
        message = stream.get_final_message()

    _check_refusal(message, "propuesta")
    if message.stop_reason == "max_tokens":
        raise RuntimeError("La propuesta se cortó por longitud (max_tokens).")
    return json.loads(_text(message))
