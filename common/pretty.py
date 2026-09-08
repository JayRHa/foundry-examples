"""Kleine Ausgabe-Helfer, damit die Beispiele lesbar bleiben.

Wichtig: Modellausgaben werden mit markup=False gedruckt. rich interpretiert
sonst eckige Klammern als Style-Tags - eine Antwort mit der Zitatmarke
"[handbuch.md#2]" erscheint dann ohne das Zitat, und man sucht den Fehler
im Prompt statt in der Konsole.
"""

from __future__ import annotations

import sys

try:
    from rich.console import Console
    from rich.rule import Rule

    _console = Console()

    def header(text: str) -> None:
        _console.print(Rule(f"[bold cyan]{text}"))

    def info(text: str) -> None:
        _console.print(text, style="dim", markup=False, highlight=False)

    def answer(text: str) -> None:
        _console.print(text, style="green", markup=False, highlight=False)

    def warn(text: str) -> None:
        _console.print(f"! {text}", style="yellow", markup=False, highlight=False)

except ImportError:  # rich ist optional
    def header(text: str) -> None:
        print(f"\n=== {text} ===")

    def info(text: str) -> None:
        print(text)

    def answer(text: str) -> None:
        print(text)

    def warn(text: str) -> None:
        print(f"! {text}", file=sys.stderr)


def stream_token(text: str) -> None:
    """Token-fuer-Token-Ausgabe ohne Zeilenumbruch."""
    print(text, end="", flush=True)
