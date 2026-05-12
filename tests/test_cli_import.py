def test_cli_imports_with_sqlalchemy_14() -> None:
    from bitamin_finance.cli import build_parser

    parser = build_parser()
    command_names = parser._subparsers._actions[1].choices.keys()
    assert "init-db" in command_names
    assert "export-exposure" in command_names
