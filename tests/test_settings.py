"""Tests for the configuration settings module."""

import os

import pytest


class TestLLMConfig:
    def test_default_provider(self):
        from app.config.settings import LLMConfig
        config = LLMConfig()
        assert config.provider in ("openai", "anthropic", "gemini", "groq", "")

    def test_unconfigured_api_key(self):
        from app.config.settings import LLMConfig
        config = LLMConfig(api_key="")
        assert config.is_configured is False

    def test_configured_api_key(self):
        from app.config.settings import LLMConfig
        config = LLMConfig(api_key="sk-test123")
        assert config.is_configured is True


class TestSearchConfig:
    def test_default_provider(self):
        from app.config.settings import SearchConfig
        config = SearchConfig()
        assert config.provider in ("tavily", "serpapi", "google_cse", "bing", "")

    def test_unconfigured(self):
        from app.config.settings import SearchConfig
        config = SearchConfig(api_key="")
        assert config.is_configured is False


class TestCampaignConfig:
    def test_default_lead_target(self):
        from app.config.settings import CampaignConfig
        config = CampaignConfig()
        assert config.daily_lead_target >= 0

    def test_dry_run_default(self):
        from app.config.settings import CampaignConfig
        config = CampaignConfig()
        # Should be set from env or default
        assert isinstance(config.dry_run, bool)

    def test_score_threshold(self):
        from app.config.settings import CampaignConfig
        config = CampaignConfig()
        assert 0 <= config.lead_score_threshold <= 100


class TestSettingsPrintStatus:
    def test_print_status_contains_sections(self):
        from app.config.settings import Settings
        s = Settings()
        status = s.print_status()
        assert "Configuration Status" in status
        assert "LLM API" in status
        assert "Search API" in status
        assert "Google Maps API" in status
        assert "Google Sheets API" in status
        assert "Email API" in status
        assert "WhatsApp API" in status

    def test_status_shows_ok_or_not_configured(self):
        from app.config.settings import Settings
        s = Settings()
        status = s.print_status()
        assert "OK" in status or "NOT CONFIGURED" in status


class TestProjectPaths:
    def test_data_dir_exists(self):
        from app.config.settings import DATA_DIR
        assert DATA_DIR.exists()

    def test_log_dir_exists(self):
        from app.config.settings import LOG_DIR
        assert LOG_DIR.exists()
