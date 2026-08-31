"""Tests for the main entry point and CLI."""

import pytest
import sys


class TestMainEntryPoint:
    """Test that the main module can be imported and basic functions work."""

    def test_import_main(self):
        """Main module should be importable."""
        import app.main
        assert hasattr(app.main, "main")

    def test_setup_logging(self):
        """setup_logging should not crash."""
        from app.main import setup_logging
        setup_logging("INFO")

    def test_config_status_output(self):
        """Config status should be printable."""
        from app.dashboard.terminal import print_config_status
        # Should not raise
        print_config_status()

    def test_settings_singleton(self):
        """Settings singleton should be accessible and stable."""
        from app.config.settings import settings
        from app.config.settings import settings as settings2
        assert settings is settings2

    def test_database_init(self):
        """Database initialization should not crash."""
        from app.database.models import init_db
        init_db()  # Should be idempotent

    def test_agent_json_loads(self):
        """agents.json should be loadable."""
        import json
        from pathlib import Path
        agents_file = Path(__file__).resolve().parent.parent / "agents.json"
        assert agents_file.exists()
        with open(agents_file) as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) > 0
        for agent in data:
            assert "name" in agent
            assert "category" in agent

    def test_env_example_exists(self):
        """.env.example should exist."""
        from pathlib import Path
        env_file = Path(__file__).resolve().parent.parent / ".env.example"
        assert env_file.exists()

    def test_gitignore_exists(self):
        """.gitignore should exist and contain .env."""
        from pathlib import Path
        gi = Path(__file__).resolve().parent.parent / ".gitignore"
        assert gi.exists()
        content = gi.read_text()
        assert ".env" in content
