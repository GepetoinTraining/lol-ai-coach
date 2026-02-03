"""
Knowledge Base Loader

Loads coaching knowledge documents for RAG (Retrieval-Augmented Generation)
to provide context-aware recommendations based on Core Theory principles.
"""

from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from ..logging_config import get_logger

logger = get_logger(__name__)

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
    """
    Load a single markdown document with error handling.

    Args:
        path: Path to the markdown file

    Returns:
        KnowledgeDocument if successful, None otherwise
    """
    if not path.exists():
        logger.debug(f"Knowledge file not found: {path}")
        return None

    if path.suffix != '.md':
        logger.debug(f"Skipping non-markdown file: {path}")
        return None

    try:
        content = path.read_text(encoding='utf-8')
    except PermissionError as e:
        logger.warning(f"Permission denied reading knowledge file: {path} - {e}")
        return None
    except UnicodeDecodeError as e:
        logger.warning(f"Encoding error reading knowledge file: {path} - {e}")
        # Try with fallback encoding
        try:
            content = path.read_text(encoding='latin-1')
            logger.info(f"Successfully read {path} with latin-1 fallback encoding")
        except Exception:
            return None
    except OSError as e:
        logger.warning(f"OS error reading knowledge file: {path} - {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error reading knowledge file: {path} - {e}")
        return None

    # Validate content
    if not content.strip():
        logger.debug(f"Empty knowledge file: {path}")
        return None

    # Extract title from first line (assumes # Title format)
    lines = content.strip().split('\n')
    title = path.stem  # Default to filename

    if lines and lines[0].startswith('#'):
        title = lines[0].lstrip('#').strip()
        if not title:
            title = path.stem

    # Get category from parent folder
    category = path.parent.name if path.parent != KNOWLEDGE_DIR else "root"

    logger.debug(f"Loaded knowledge document: {title} ({category})")

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
        logger.warning(f"Knowledge directory not found: {KNOWLEDGE_DIR}")
        return documents

    try:
        for md_file in KNOWLEDGE_DIR.rglob("*.md"):
            doc = load_document(md_file)
            if doc:
                documents.append(doc)
    except PermissionError as e:
        logger.error(f"Permission denied accessing knowledge directory: {e}")
    except Exception as e:
        logger.error(f"Error scanning knowledge directory: {e}")

    logger.info(f"Loaded {len(documents)} knowledge documents")
    return documents


def load_by_category(category: str) -> list[KnowledgeDocument]:
    """Load all documents from a specific category"""
    category_path = KNOWLEDGE_DIR / category
    documents = []

    if not category_path.exists():
        logger.debug(f"Category not found: {category}")
        return documents

    if not category_path.is_dir():
        logger.debug(f"Category path is not a directory: {category_path}")
        return documents

    try:
        for md_file in category_path.glob("*.md"):
            doc = load_document(md_file)
            if doc:
                documents.append(doc)
    except PermissionError as e:
        logger.warning(f"Permission denied accessing category {category}: {e}")
    except Exception as e:
        logger.warning(f"Error loading category {category}: {e}")

    return documents


def load_for_intent(intent_value: str) -> list[KnowledgeDocument]:
    """
    Load relevant knowledge documents based on coaching intent.

    Maps intents to relevant knowledge categories.

    Args:
        intent_value: The coaching intent value

    Returns:
        List of relevant KnowledgeDocuments
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
    seen_paths = set()  # Avoid duplicates

    logger.debug(f"Loading knowledge for intent '{intent_value}': {categories}")

    # Load category folders
    for cat in categories:
        try:
            if cat.endswith('.md'):
                # Direct file reference
                doc = load_document(KNOWLEDGE_DIR / cat)
                if doc and doc.path not in seen_paths:
                    documents.append(doc)
                    seen_paths.add(doc.path)
            else:
                # Category folder
                for doc in load_by_category(cat):
                    if doc.path not in seen_paths:
                        documents.append(doc)
                        seen_paths.add(doc.path)
        except Exception as e:
            logger.warning(f"Error loading knowledge for category '{cat}': {e}")
            continue

    logger.info(f"Loaded {len(documents)} documents for intent '{intent_value}'")
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
    try:
        documents = load_for_intent(intent_value)
    except Exception as e:
        logger.error(f"Failed to load knowledge for intent '{intent_value}': {e}")
        return ""  # Graceful degradation - coaching works without knowledge

    if not documents:
        logger.debug(f"No knowledge documents found for intent: {intent_value}")
        return ""

    context_parts = []
    total_words = 0

    for doc in documents:
        if total_words + doc.word_count > max_words:
            # Truncate if we're approaching the limit
            remaining = max_words - total_words
            if remaining > 100:  # Only include if we have room for meaningful content
                words = doc.content.split()[:remaining]
                context_parts.append(
                    f"## {doc.title} (from {doc.category})\n\n" +
                    ' '.join(words) + "...\n"
                )
            break

        context_parts.append(f"## {doc.title} (from {doc.category})\n\n{doc.content}\n")
        total_words += doc.word_count

    result = "\n---\n\n".join(context_parts)
    logger.debug(f"Generated knowledge context: {total_words} words from {len(context_parts)} docs")

    return result


def list_available_knowledge() -> dict[str, list[str]]:
    """List all available knowledge by category"""
    result = {}

    if not KNOWLEDGE_DIR.exists():
        logger.warning(f"Knowledge directory not found: {KNOWLEDGE_DIR}")
        return result

    try:
        # Root level files
        root_files = [f.name for f in KNOWLEDGE_DIR.glob("*.md")]
        if root_files:
            result["root"] = root_files

        # Category folders
        for category_dir in KNOWLEDGE_DIR.iterdir():
            if category_dir.is_dir():
                try:
                    files = [f.name for f in category_dir.glob("*.md")]
                    if files:
                        result[category_dir.name] = files
                except PermissionError:
                    logger.warning(f"Permission denied reading category: {category_dir.name}")
    except Exception as e:
        logger.error(f"Error listing knowledge: {e}")

    return result


# ==================== CLI for testing ====================

if __name__ == "__main__":
    from rich.console import Console
    from rich.table import Table
    from rich.markdown import Markdown

    # Initialize logging for CLI test
    from ..logging_config import setup_logging
    setup_logging(level="DEBUG")

    console = Console()

    # List available knowledge
    console.print("\n[bold cyan]Available Knowledge Base[/bold cyan]\n")

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
