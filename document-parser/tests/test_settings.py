"""Tests for Settings — environment variable parsing and defaults."""

from __future__ import annotations

from infra.settings import Settings


class TestSettingsDefaults:
    def test_default_values(self):
        s = Settings()
        assert s.app_version == "dev"
        assert s.conversion_engine == "local"
        assert s.deployment_mode == "self-hosted"
        assert s.docling_serve_url == "http://localhost:5001"
        assert s.docling_serve_api_key is None
        assert s.conversion_timeout == 900
        assert s.document_timeout == 120.0
        assert s.lock_timeout == 300
        assert s.max_page_count == 0
        assert s.max_file_size_mb == 50
        assert s.max_paste_image_size_mb == 10
        assert s.paste_allowed_image_types == ["image/png", "image/jpeg", "image/webp"]
        assert s.batch_page_size == 0
        assert s.opensearch_default_limit == 1000
        assert s.upload_dir == "./uploads"
        assert s.db_path == "./data/docling_studio.db"
        assert "http://localhost:3000" in s.cors_origins

    def test_frozen(self):
        """Settings should be immutable."""
        import pytest

        s = Settings()
        with pytest.raises(AttributeError):
            s.upload_dir = "/other"  # type: ignore[misc]


class TestSettingsValidation:
    def test_negative_document_timeout_rejected(self):
        import pytest

        with pytest.raises(ValueError, match="document_timeout must be > 0"):
            Settings(document_timeout=-1.0)

    def test_zero_document_timeout_rejected(self):
        import pytest

        with pytest.raises(ValueError, match="document_timeout must be > 0"):
            Settings(document_timeout=0)

    def test_negative_conversion_timeout_rejected(self):
        import pytest

        with pytest.raises(ValueError, match="conversion_timeout must be > 0"):
            Settings(conversion_timeout=-1)

    def test_zero_max_concurrent_rejected(self):
        import pytest

        with pytest.raises(ValueError, match="max_concurrent_analyses must be >= 1"):
            Settings(max_concurrent_analyses=0)

    def test_negative_max_page_count_rejected(self):
        import pytest

        with pytest.raises(ValueError, match="max_page_count must be >= 0"):
            Settings(max_page_count=-1)

    def test_negative_max_file_size_rejected(self):
        import pytest

        with pytest.raises(ValueError, match="max_file_size must be >= 0"):
            Settings(max_file_size=-1)

    def test_negative_max_file_size_mb_rejected(self):
        import pytest

        with pytest.raises(ValueError, match="max_file_size_mb must be >= 0"):
            Settings(max_file_size_mb=-1)

    def test_negative_max_paste_image_size_mb_rejected(self):
        import pytest

        with pytest.raises(ValueError, match="max_paste_image_size_mb must be >= 0"):
            Settings(max_paste_image_size_mb=-1)

    def test_empty_paste_allowed_image_types_rejected(self):
        import pytest

        with pytest.raises(ValueError, match="paste_allowed_image_types must not be empty"):
            Settings(paste_allowed_image_types=[])

    def test_zero_max_file_size_mb_accepted(self):
        s = Settings(max_file_size_mb=0)
        assert s.max_file_size_mb == 0

    def test_positive_max_file_size_mb_accepted(self):
        s = Settings(max_file_size_mb=100)
        assert s.max_file_size_mb == 100

    def test_negative_batch_page_size_rejected(self):
        import pytest

        with pytest.raises(ValueError, match="batch_page_size must be >= 0"):
            Settings(batch_page_size=-1)

    def test_zero_batch_page_size_accepted(self):
        s = Settings(batch_page_size=0)
        assert s.batch_page_size == 0

    def test_positive_batch_page_size_accepted(self):
        s = Settings(batch_page_size=10)
        assert s.batch_page_size == 10

    def test_zero_lock_timeout_rejected(self):
        import pytest

        with pytest.raises(ValueError, match="lock_timeout must be > 0"):
            Settings(lock_timeout=0)

    def test_zero_opensearch_default_limit_rejected(self):
        import pytest

        with pytest.raises(ValueError, match="opensearch_default_limit must be >= 1"):
            Settings(opensearch_default_limit=0)

    def test_invalid_table_mode_rejected(self):
        import pytest

        with pytest.raises(ValueError, match="default_table_mode must be"):
            Settings(default_table_mode="turbo")

    def test_cascade_document_ge_lock_rejected(self):
        import pytest

        with pytest.raises(ValueError, match=r"document_timeout.*< lock_timeout"):
            Settings(document_timeout=400.0, lock_timeout=300, conversion_timeout=900)

    def test_cascade_lock_ge_conversion_rejected(self):
        import pytest

        with pytest.raises(ValueError, match=r"lock_timeout.*< conversion_timeout"):
            Settings(document_timeout=100.0, lock_timeout=900, conversion_timeout=900)

    def test_cascade_valid_ordering_accepted(self):
        s = Settings(document_timeout=60.0, lock_timeout=300, conversion_timeout=900)
        assert s.document_timeout < s.lock_timeout < s.conversion_timeout

    def test_multiple_errors_reported(self):
        import pytest

        with pytest.raises(ValueError, match="document_timeout") as exc_info:
            Settings(document_timeout=-1, conversion_timeout=-1)
        assert "conversion_timeout" in str(exc_info.value)


class TestReasoningMaxIterations:
    """#317 — the RAG loop cap is a bounded bootstrap default."""

    def test_default_is_five(self):
        assert Settings().reasoning_max_iterations == 5

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("REASONING_MAX_ITERATIONS", "9")
        assert Settings.from_env().reasoning_max_iterations == 9

    def test_out_of_bounds_rejected(self):
        import pytest

        with pytest.raises(ValueError, match="reasoning_max_iterations"):
            Settings(reasoning_max_iterations=0)
        with pytest.raises(ValueError, match="reasoning_max_iterations"):
            Settings(reasoning_max_iterations=21)


class TestSettingsFromEnv:
    def test_reads_env_vars(self, monkeypatch):
        monkeypatch.setenv("APP_VERSION", "1.2.3")
        monkeypatch.setenv("CONVERSION_ENGINE", "remote")
        monkeypatch.setenv("DEPLOYMENT_MODE", "huggingface")
        monkeypatch.setenv("DOCLING_SERVE_URL", "http://serve:9000")
        monkeypatch.setenv("DOCLING_SERVE_API_KEY", "secret-key")
        monkeypatch.setenv("CONVERSION_TIMEOUT", "1200")
        monkeypatch.setenv("DOCUMENT_TIMEOUT", "60.0")
        monkeypatch.setenv("LOCK_TIMEOUT", "600")
        monkeypatch.setenv("MAX_PAGE_COUNT", "20")
        monkeypatch.setenv("MAX_FILE_SIZE_MB", "100")
        monkeypatch.setenv("BATCH_PAGE_SIZE", "15")
        monkeypatch.setenv("OPENSEARCH_DEFAULT_LIMIT", "500")
        monkeypatch.setenv("UPLOAD_DIR", "/data/uploads")
        monkeypatch.setenv("DB_PATH", "/data/test.db")
        monkeypatch.setenv("CORS_ORIGINS", "http://a.com, http://b.com")

        s = Settings.from_env()

        assert s.app_version == "1.2.3"
        assert s.conversion_engine == "remote"
        assert s.deployment_mode == "huggingface"
        assert s.docling_serve_url == "http://serve:9000"
        assert s.docling_serve_api_key == "secret-key"
        assert s.conversion_timeout == 1200
        assert s.lock_timeout == 600
        assert s.document_timeout == 60.0
        assert s.max_page_count == 20
        assert s.max_file_size_mb == 100
        assert s.batch_page_size == 15
        assert s.opensearch_default_limit == 500
        assert s.upload_dir == "/data/uploads"
        assert s.db_path == "/data/test.db"
        assert s.cors_origins == ["http://a.com", "http://b.com"]

    def test_defaults_when_env_empty(self, monkeypatch):
        """When no env vars set, from_env returns sensible defaults."""
        for key in (
            "APP_VERSION",
            "CONVERSION_ENGINE",
            "DEPLOYMENT_MODE",
            "DOCLING_SERVE_URL",
            "DOCLING_SERVE_API_KEY",
            "CONVERSION_TIMEOUT",
            "MAX_PAGE_COUNT",
            "UPLOAD_DIR",
            "DB_PATH",
            "CORS_ORIGINS",
        ):
            monkeypatch.delenv(key, raising=False)

        s = Settings.from_env()

        assert s.app_version == "dev"
        assert s.conversion_engine == "local"
        assert s.conversion_timeout == 900
        assert s.max_page_count == 0

    def test_cors_origins_split(self, monkeypatch):
        monkeypatch.setenv("CORS_ORIGINS", "http://a.com,http://b.com,http://c.com")
        s = Settings.from_env()
        assert len(s.cors_origins) == 3
        assert s.cors_origins[2] == "http://c.com"
