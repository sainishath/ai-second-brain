"""
brain.py — Main CLI for AI Second Brain
Usage:
  python src/brain.py ingest --url "https://..."
  python src/brain.py chat "What do I know about RAG?"
  python src/brain.py search "transformer attention"
  python src/brain.py stats
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", ".env"))

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from typing import Optional

from ingest import ingest as _ingest
from retriever import HybridRetriever
from generator import get_generator

app = typer.Typer(help="🧠 AI Second Brain — Anti-Gravity Edition")
console = Console()


@app.command()
def ingest(
    url: Optional[str] = typer.Option(None, "--url", "-u", help="URL to scrape"),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Path to PDF, TXT, DOCX, or MD"),
    youtube: Optional[str] = typer.Option(None, "--youtube", "-y", help="YouTube URL"),
    text: Optional[str] = typer.Option(None, "--text", "-t", help="Raw text to save"),
    title: str = typer.Option("", "--title", help="Optional title"),
    folder: Optional[str] = typer.Option(None, "--folder", help="Ingest all files in a folder"),
):
    """📥 Add content to your Second Brain."""
    with console.status("[bold green]Ingesting..."):
        result = _ingest(
            url=url, file=file, youtube=youtube,
            text=text, title=title, folder=folder
        )

    if "batch" in result:
        console.print(f"[green]✅ Batch ingested {result['batch']} files.[/green]")
    else:
        console.print(Panel(
            f"[green]✅ Saved[/green]\n"
            f"Title: [bold]{result.get('title', 'N/A')}[/bold]\n"
            f"Type: {result.get('source_type', 'N/A')}\n"
            f"Chunks: {result.get('chunks', 'N/A')}\n"
            f"ID: {result.get('doc_id', 'N/A')}",
            title="Ingested",
        ))


@app.command()
def chat(
    question: str = typer.Argument(..., help="Question to ask your Second Brain"),
    n: int = typer.Option(8, "--results", "-n", help="Number of chunks to retrieve"),
):
    """💬 Chat with your Second Brain."""
    retriever = HybridRetriever()
    generator = get_generator()

    with console.status("[bold cyan]Searching your knowledge base..."):
        hits = retriever.retrieve(question, n=n)

    if not hits:
        console.print("[yellow]⚠️  No relevant content found. Try ingesting more content first.[/yellow]")
        return

    context = retriever.format_context(hits)

    console.print(f"\n[dim]Found {len(hits)} relevant chunks from your knowledge base.[/dim]\n")

    # Stream the response
    console.print("[bold]🧠 Second Brain:[/bold]\n")
    full_response = ""
    for token in generator.stream(question, context):
        print(token, end="", flush=True)
        full_response += token
    print("\n")

    # Show sources
    sources_seen = set()
    table = Table(title="Sources Used", show_header=True)
    table.add_column("Title", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Source", style="dim")

    for hit in hits:
        meta = hit["metadata"]
        key = meta.get("doc_id", "")
        if key not in sources_seen:
            sources_seen.add(key)
            table.add_row(
                meta.get("title", "Unknown")[:50],
                meta.get("source_type", ""),
                meta.get("source", "")[:60],
            )

    console.print(table)


@app.command()
def search(
    query: str = typer.Argument(..., help="Semantic search query"),
    n: int = typer.Option(5, "--results", "-n"),
):
    """🔍 Semantic search across your knowledge base."""
    retriever = HybridRetriever()

    with console.status("[bold cyan]Searching..."):
        hits = retriever.retrieve(query, n=n)

    if not hits:
        console.print("[yellow]No results found.[/yellow]")
        return

    for i, hit in enumerate(hits, 1):
        meta = hit["metadata"]
        console.print(Panel(
            f"[dim]{hit['content'][:300]}...[/dim]",
            title=f"[{i}] {meta.get('title', 'Unknown')} ({meta.get('source_type', '')})",
            subtitle=f"Score: {hit.get('rrf_score', 0):.4f}",
        ))


@app.command()
def stats():
    """📊 Show knowledge base statistics."""
    retriever = HybridRetriever()
    data = retriever.stats()

    table = Table(title="🧠 Second Brain Stats")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="bold")

    for key, val in data.items():
        table.add_row(key.replace("_", " ").title(), str(val))

    console.print(table)


if __name__ == "__main__":
    app()
