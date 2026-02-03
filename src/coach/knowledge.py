"""
Knowledge Base Loader

Loads coaching knowledge documents for RAG (Retrieval-Augmented Generation)
to provide context-aware recommendations based on Core Theory principles.
"""

import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

# Path to knowledge base
KNOWLEDGE_DIR = Path(__file__).parent.parent.parent / "knowledge"


@dataclass
class KnowledgeDocument:
    """A loaded knowledge document"""
    title: str
    category: str
    content: str
    path: Path
    
    @property
    def word_count(self) -> int:
        return len(self.content.split())


def load_document(path: Path) -> Optional[KnowledgeDocument]:
    """Load a single markdown document"""
    if not path.exists() or not path.suffix == '.md':
        return None
    
    content = path.read_text(encoding='utf-8')
    
    # Extract title from first line (assumes # Title format)
    lines = content.strip().split('\n')
    title = lines[0].lstrip('#').strip() if lines else path.stem
    
    # Get category from parent folder
    category = path.parent.name
    
    return KnowledgeDocument(
        title=title,
        category=category,
        content=content,
        path=path
    )


def load_all_documents() -> list[KnowledgeDocument]:
    """Load all knowledge documents from the knowledge base"""
    documents = []
    
    if not KNOWLEDGE_DIR.exists():
        return documents
    
    for md_file in KNOWLEDGE_DIR.rglob("*.md"):
        doc = load_document(md_file)
        if doc:
            documents.append(doc)
    
    return documents


def load_by_category(category: str) -> list[KnowledgeDocument]:
    """Load all documents from a specific category"""
    category_path = KNOWLEDGE_DIR / category
    documents = []
    
    if not category_path.exists():
        return documents
    
    for md_file in category_path.glob("*.md"):
        doc = load_document(md_file)
        if doc:
            documents.append(doc)
    
    return documents


def load_for_intent(intent_value: str) -> list[KnowledgeDocument]:
    """
    Load relevant knowledge documents based on coaching intent.
    
    Maps intents to relevant knowledge categories.
    """
    intent_to_categories = {
        "laning": ["fundamentals", "core_theory.md"],
        "macro": ["macro", "core_theory.md"],
        "teamfighting": ["fundamentals", "macro"],
        "dying_less": ["fundamentals", "mental"],
        "climbing": ["fundamentals", "macro", "mental", "core_theory.md"],
        "champion_specific": ["fundamentals"],
        "mental": ["mental"],
        "general": ["fundamentals", "macro", "mental", "core_theory.md"],
    }
    
    categories = intent_to_categories.get(intent_value, ["fundamentals"])
    documents = []
    
    # Load category folders
    for cat in categories:
        if cat.endswith('.md'):
            # Direct file reference
            doc = load_document(KNOWLEDGE_DIR / cat)
            if doc:
                documents.append(doc)
        else:
            # Category folder
            docs = load_by_category(cat)
            documents.extend(docs)
    
    return documents


def get_knowledge_context(intent_value: str, max_words: int = 2000) -> str:
    """
    Get formatted knowledge context for AI prompt injection.
    
    Args:
        intent_value: The coaching intent (e.g., "laning", "macro")
        max_words: Maximum words to include (to manage token limits)
    
    Returns:
        Formatted markdown string with relevant knowledge
    """
    documents = load_for_intent(intent_value)
    
    if not documents:
        return ""
    
    context_parts = []
    total_words = 0
    
    for doc in documents:
        if total_words + doc.word_count > max_words:
            # Truncate if we're approaching the limit
            remaining = max_words - total_words
            if remaining > 100:  # Only include if we have room for meaningful content
                words = doc.content.split()[:remaining]
                context_parts.append(f"## {doc.title} (from {doc.category})\n\n" + ' '.join(words) + "...\n")
            break
        
        context_parts.append(f"## {doc.title} (from {doc.category})\n\n{doc.content}\n")
        total_words += doc.word_count
    
    return "\n---\n\n".join(context_parts)


def list_available_knowledge() -> dict[str, list[str]]:
    """List all available knowledge by category"""
    result = {}
    
    if not KNOWLEDGE_DIR.exists():
        return result
    
    # Root level files
    root_files = [f.name for f in KNOWLEDGE_DIR.glob("*.md")]
    if root_files:
        result["root"] = root_files
    
    # Category folders
    for category_dir in KNOWLEDGE_DIR.iterdir():
        if category_dir.is_dir():
            files = [f.name for f in category_dir.glob("*.md")]
            if files:
                result[category_dir.name] = files
    
    return result


# ==================== CLI for testing ====================

if __name__ == "__main__":
    from rich.console import Console
    from rich.table import Table
    from rich.markdown import Markdown
    
    console = Console()
    
    # List available knowledge
    console.print("\n[bold cyan]📚 Available Knowledge Base[/bold cyan]\n")
    
    available = list_available_knowledge()
    
    table = Table(title="Knowledge Documents")
    table.add_column("Category", style="cyan")
    table.add_column("Documents", style="green")
    
    for category, docs in available.items():
        table.add_row(category, ", ".join(docs))
    
    console.print(table)
    
    # Test loading for an intent
    console.print("\n[bold yellow]Testing intent-based loading (laning):[/bold yellow]\n")
    
    context = get_knowledge_context("laning", max_words=500)
    console.print(Markdown(context[:2000] + "..." if len(context) > 2000 else context))
