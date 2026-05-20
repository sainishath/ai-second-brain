"""
scripts/youtube_ingest.py
Batch ingest a list of YouTube URLs into your Second Brain.

Usage:
  python scripts/youtube_ingest.py urls.txt
  python scripts/youtube_ingest.py --url "https://youtube.com/watch?v=..."
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from dotenv import load_dotenv
load_dotenv("config/.env")

import typer
from pathlib import Path
from rich.console import Console
from rich.progress import track
from ingest import ingest

app = typer.Typer()
console = Console()


@app.command()
def batch(
    urls_file: str = typer.Argument(None, help="Text file with one YouTube URL per line"),
    url: str = typer.Option(None, "--url", help="Single YouTube URL"),
):
    """Batch ingest YouTube videos into your Second Brain."""

    urls = []
    if url:
        urls.append(url)
    elif urls_file:
        urls = Path(urls_file).read_text().strip().splitlines()
        urls = [u.strip() for u in urls if u.strip() and not u.startswith("#")]
    else:
        console.print("[red]Provide a URLs file or --url[/red]")
        raise typer.Exit(1)

    console.print(f"[cyan]Ingesting {len(urls)} YouTube videos...[/cyan]\n")

    success, failed = 0, 0
    for url in track(urls, description="Processing..."):
        try:
            result = ingest(youtube=url)
            console.print(f"  [green]✓[/green] {result.get('title', url)[:60]}")
            success += 1
        except Exception as e:
            console.print(f"  [red]✗[/red] {url[:60]} → {e}")
            failed += 1

    console.print(f"\n[bold]Done:[/bold] {success} succeeded, {failed} failed.")


if __name__ == "__main__":
    app()
