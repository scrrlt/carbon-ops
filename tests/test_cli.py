"""Tests for CLI functionality."""

from carbon_ops.cli import main


def test_cli_main_no_args(capsys):
    """Test CLI main with no arguments."""
    # This CLI requires input, so it should exit with error
    result = main([])
    assert result == 1  # Error exit code

    captured = capsys.readouterr()
    assert "No input provided" in captured.err


def test_cli_main_help(capsys):
    """Test CLI help output."""
    result = main(["--help"])
    # argparse exits with 0 for --help
    assert result == 0

    captured = capsys.readouterr()
    assert "usage:" in captured.out.lower()
    assert "verify" in captured.out.lower()


def test_cli_main_invalid_args(capsys):
    """Test CLI with invalid arguments."""
    result = main(["--version"])
    assert result == 1  # Error exit code
