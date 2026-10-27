"""A small command-line chat client for Google's Gemini models."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import itertools
import os
import shutil
import sys
import textwrap
from collections.abc import Sequence
from pathlib import Path
from threading import Event, Thread
from typing import IO, Iterator

import httpx
from google import genai
from google.genai import types

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


DEFAULT_MODEL = "gemini-3.8-flash"
EXIT_COMMANDS = {"/exit", "/quit"}
COLOR_USER = "33"
COLOR_PARTIAL = "36"
COLOR_RESULT = "32"
COLOR_ERROR = "31"
MAX_RESPONSE_LINES = 8


def write_colored(
    text: str,
    color: str,
    stream: IO[str] | None = None,
    end: str = "",
) -> None:
    if stream is None:
        stream = sys.stdout
    if stream.isatty():
        stream.write(f"\033[{color}m{text}\033[0m")
    else:
        stream.write(text)
    stream.write(end)
    stream.flush()


def read_user_input() -> str:
    if not sys.stdout.isatty():
        return input("You: ")

    sys.stdout.write(f"\033[{COLOR_USER}mYou: ")
    sys.stdout.flush()
    try:
        return input()
    finally:
        sys.stdout.write("\033[0m")
        sys.stdout.flush()


@contextmanager
def thinking_indicator() -> Iterator[None]:
    if not sys.stderr.isatty():
        yield
        return

    stop = Event()

    def animate() -> None:
        for frame in itertools.cycle("|/-\\"):
            if stop.wait(0.1):
                break
            sys.stderr.write(f"\rThinking {frame}")
            sys.stderr.flush()

    spinner = Thread(target=animate)
    spinner.start()
    try:
        yield
    finally:
        stop.set()
        spinner.join()
        sys.stderr.write("\r" + " " * 12 + "\r")
        sys.stderr.flush()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ask Gemini a question or start an interactive conversation."
    )
    parser.add_argument(
        "prompt",
        nargs="*",
        help="Prompt to send once. Omit it to start an interactive chat.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Gemini model to use (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--system",
        help="Optional system instruction for the conversation.",
    )
    parser.add_argument(
        "--api-key",
        help="Gemini API key (overrides the environment variable and settings file).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("settings.toml"),
        help="TOML settings file to read when no API key is provided elsewhere "
        "(default: settings.toml).",
    )
    return parser.parse_args(argv)


def load_api_key(config_path: Path) -> str | None:
    try:
        with config_path.open("rb") as settings_file:
            settings = tomllib.load(settings_file)
    except FileNotFoundError:
        return None
    except (OSError, tomllib.TOMLDecodeError) as error:
        message = f"Could not read settings file '{config_path}': {error}"
        raise ValueError(message) from error

    gemini_settings = settings.get("gemini", {})
    if not isinstance(gemini_settings, dict):
        raise ValueError(
            "The [gemini] section in the settings file must be a table."
        )

    api_key = gemini_settings.get("api_key")
    if api_key is not None and not isinstance(api_key, str):
        raise ValueError("The 'api_key' setting in [gemini] must be a string.")
    return api_key or None


def create_chat(
    model: str,
    system_instruction: str | None,
    api_key: str | None = None,
    config_path: Path = Path("settings.toml"),
) -> tuple[genai.Client, genai.chats.Chat]:
    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        api_key = load_api_key(config_path)
    if not api_key:
        raise ValueError(
            "No API key provided. Use --api-key, set GEMINI_API_KEY, "
            f"or add api_key to [gemini] in '{config_path}'."
        )

    client = genai.Client(api_key=api_key)
    config = (
        types.GenerateContentConfig(system_instruction=system_instruction)
        if system_instruction
        else None
    )
    return client, client.chats.create(model=model, config=config)


def wrap_response(text: str, width: int) -> list[str]:
    wrapper = textwrap.TextWrapper(
        width=max(1, width - 1),
        break_long_words=True,
        break_on_hyphens=False,
        replace_whitespace=False,
        drop_whitespace=False,
    )
    lines: list[str] = []
    for paragraph in text.split("\n"):
        lines.extend(wrapper.wrap(paragraph) or [""])
    return lines[-MAX_RESPONSE_LINES:]


def redraw_response(
    text: str,
    previous_line_count: int,
    final_line_color: str | None = None,
) -> int:
    stream = sys.stdout
    width = shutil.get_terminal_size((80, 24)).columns
    lines = wrap_response(text, width)

    if previous_line_count:
        stream.write(f"\033[{previous_line_count}A")

    row_count = max(previous_line_count, len(lines))
    for index in range(row_count):
        stream.write("\r\033[2K")
        if index < len(lines):
            color = (
                final_line_color
                if final_line_color is not None and index == len(lines) - 1
                else COLOR_PARTIAL
            )
            stream.write(f"\033[{color}m{lines[index]}\033[0m")
        stream.write("\n")

    stream.flush()
    return len(lines)


def print_result(text: str) -> None:
    write_colored(text or "[No text response]", COLOR_RESULT, end="\n")


def print_complete_response(text: str) -> None:
    write_colored("Complete response:", COLOR_RESULT, end="\n")
    write_colored(text or "[No text response]", COLOR_RESULT, end="\n")


def stream_response(chat, message: str) -> str:
    chunks = iter(chat.send_message_stream(message))
    response_started = False
    response_completed = False
    response_parts: list[str] = []
    terminal_output = sys.stdout.isatty()
    displayed_line_count = 0

    try:
        with thinking_indicator():
            for chunk in chunks:
                text = chunk.text or ""
                if not text:
                    continue
                response_started = True
                response_parts.append(text)
                response_text = f"Gemini: {''.join(response_parts)}"
                if terminal_output:
                    displayed_line_count = redraw_response(
                        response_text, displayed_line_count
                    )
                else:
                    write_colored("Gemini: ", COLOR_PARTIAL)
                    write_colored(text, COLOR_PARTIAL)
                break

        for chunk in chunks:
            text = chunk.text or ""
            if text:
                response_parts.append(text)
                response_text = f"Gemini: {''.join(response_parts)}"
                if terminal_output:
                    displayed_line_count = redraw_response(
                        response_text, displayed_line_count
                    )
                else:
                    write_colored(text, COLOR_PARTIAL)
        response_completed = True
    finally:
        if response_started:
            if terminal_output:
                marker = "[complete]" if response_completed else "[incomplete]"
                marker_text = f"Gemini: {''.join(response_parts)}\n{marker}"
                redraw_response(
                    marker_text,
                    displayed_line_count,
                    COLOR_RESULT if response_completed else COLOR_ERROR,
                )
            else:
                marker = " [complete]" if response_completed else " [incomplete]"
                write_colored(
                    marker,
                    COLOR_RESULT if response_completed else COLOR_ERROR,
                    end="\n",
                )

    if not response_started:
        print_result("")
    elif response_completed:
        print_complete_response("".join(response_parts))

    return "".join(response_parts)


def run_chat(chat, prompt: str | None) -> int:
    if prompt is not None:
        if prompt.strip().lower() in EXIT_COMMANDS:
            return 0
        write_colored(f"You: {prompt}", COLOR_USER, end="\n")
        stream_response(chat, prompt)
        return 0

    print("Gemini chat started. Enter /exit or press Ctrl+C to quit.")
    try:
        while True:
            try:
                message = read_user_input().strip()
            except EOFError:
                print()
                return 0

            if not message:
                continue
            if message.lower() in EXIT_COMMANDS:
                return 0

            stream_response(chat, message)
    except KeyboardInterrupt:
        print()
        return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    prompt = " ".join(args.prompt) if args.prompt else None

    if prompt is not None and prompt.strip().lower() in EXIT_COMMANDS:
        return 0

    client = None
    try:
        client, chat = create_chat(
            args.model, args.system, args.api_key, args.config
        )
        return run_chat(chat, prompt)
    except ValueError as error:
        write_colored(f"Error: {error}", COLOR_ERROR, sys.stderr, end="\n")
        return 2
    except genai.errors.APIError as error:
        write_colored(
            f"Gemini API request failed ({error.code} {error.status}): "
            f"{error.message or error}",
            COLOR_ERROR,
            sys.stderr,
            end="\n",
        )
        return 1
    except httpx.HTTPError as error:
        write_colored(
            f"Network error while contacting Gemini: {error}",
            COLOR_ERROR,
            sys.stderr,
            end="\n",
        )
        return 1
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
