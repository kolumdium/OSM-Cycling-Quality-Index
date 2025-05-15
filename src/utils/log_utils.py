import sys

import pretty_errors
from loguru import logger
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.theme import Theme

# Configure prettyerror for better error formatting
pretty_errors.configure(
    display_locals=True,
    # display_trace=True,
    separator_character="─",
    display_link=True,
)

# Create a Rich console for fancy output
console = Console(
    theme=Theme(
        {
            "logging.level.success": "green",
            "logging.level.trace": "bright_black",
        }
    ),
    file=sys.stdout,  # Output to stdout
)

# Add console handler with rich formatting
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    colorize=True,
    backtrace=True,
    diagnose=True,
    level="INFO",
)

# # Add file handler with plain formatting (no color codes)
# logger.add(
#     "logs/{time:YYYY-MM-DD}.log",
#     format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
#     colorize=False,
#     rotation="10 MB",  # Rotate when file reaches 10MB
#     retention="30 days",  # Keep logs for 30 days
#     compression="zip",  # Compress rotated logs
#     backtrace=True,
#     diagnose=True,
#     level="DEBUG"  # More detailed logging to file
# )

# Try to use richuru if available for better integration
try:
    from richuru import install

    install(rich_console=console)
    logger.info(
        "Using richuru for enhanced logging with rich",
        alt="[bold green]Using richuru for enhanced logging with rich[/]",
    )
except ImportError:
    logger.info("richuru not available, using standard loguru formatting")


def create_progress(description="Processing", total=100):
    """Create a Rich progress bar"""
    progress = Progress(
        TextColumn("[bold green]{task.description}"),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        "•",
        TimeElapsedColumn(),
        console=console,
    )
    task_id = progress.add_task(description, total=total)
    return progress, task_id


def log_file_start(file_path, sensor_type):
    """Log the start of processing a new file with high visibility"""
    console.rule(f"[bold green]Starting to process {sensor_type} file[/bold green]")
    console.print(f"[bold cyan]File:[/bold cyan] {file_path}", highlight=False)
    console.rule()


def log_import_summary(total_files, total_rows, duration):
    """Log a summary of the import process with highlighted metrics"""
    console.rule("[bold green]Import Summary[/bold green]")
    console.print(
        f"[bold cyan]Files processed:[/bold cyan] [yellow]{total_files}[/yellow]"
    )
    console.print(f"[bold cyan]Total rows:[/bold cyan] [yellow]{total_rows:,}[/yellow]")
    console.print(
        f"[bold cyan]Duration:[/bold cyan] [yellow]{duration:.2f}[/yellow] seconds"
    )
    console.rule()


def setup_logging(log_level="INFO", log_file=None):
    """Set up logging with specified level and optional file"""
    # This is a no-op since we've already set up logging above
    # But we keep it for compatibility with existing code
    return logger
