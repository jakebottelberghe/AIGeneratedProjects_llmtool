# Gemini CLI

A lightweight Python command-line client for chatting with Google Gemini.

## Requirements

- Python 3.10 or later
- A Gemini API key

## Setup (Windows PowerShell)

Create and activate a virtual environment, then install the project:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

Copy the example settings file and add your API key to `settings.toml` in the
directory where you run the CLI:

```powershell
Copy-Item settings.example.toml settings.toml
```

Edit `settings.toml` so it contains:

```toml
[gemini]
api_key = "your-api-key"
```

`settings.toml` is excluded from version control so the key is not committed.
You can choose a different TOML file with `--config`.

Alternatively, set your API key for the current PowerShell session:

```powershell
$env:GEMINI_API_KEY = "your-api-key"
```

You can also pass the key on the command line:

```powershell
gemini-cli --api-key "your-api-key" "Explain Python generators with a short example."
```

Command-line arguments may be saved in shell history or visible to other local
processes. Prefer `GEMINI_API_KEY` when possible.

## Usage

Send a one-shot prompt:

```powershell
gemini-cli "Explain Python generators with a short example."
```

Start an interactive conversation:

```powershell
gemini-cli
```

Choose a model or provide a system instruction:

```powershell
gemini-cli --model gemini-3.8-flash --system "Answer concisely." "What is recursion?"
```

Use `/exit` or `/quit` to end an interactive conversation; either command also
exits cleanly when passed as the initial CLI argument. The default model is
`gemini-3.8-flash`. The API key can be provided with `--api-key`, through
`GEMINI_API_KEY`, or in the `[gemini]` section of `settings.toml`. The CLI
option takes precedence, followed by the environment variable, then the
settings file. A terminal spinner is shown while waiting for Gemini responses.
API request and network errors are reported in the terminal with a nonzero exit
code. While Gemini is generating, response chunks stream into an eight-line
rolling terminal display, so long answers update in place rather than
scrolling the window. When generation finishes, the complete response is
printed below the preview so none of it is lost. User input is yellow, streamed
text is cyan, completion is green, and errors are red when the terminal
supports color.
