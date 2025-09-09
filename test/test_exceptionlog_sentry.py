import pytest
from unittest.mock import MagicMock, patch


class TestExceptionLogSentry:
    def test_sentry_connection_test_with_real_sentry(self):
        """Test that test_sentry_connection returns True when Sentry is properly configured."""
        mock_app = MagicMock()
        mock_app.config.get.side_effect = lambda key, default=None: {
            "EXCEPTION_LOG_TYPE": "Sentry",
            "SENTRY_DSN": "https://test@sentry.io/123",
            "SENTRY_ENVIRONMENT": "test",
            "OTEL_EXPORTER_OTLP_ENDPOINT": None,  # Explicitly set to None to disable OpenTelemetry
        }.get(key, default)

        # Patch sentry_sdk before importing the module
        with patch("util.saas.exceptionlog.sentry_sdk") as mock_sentry_sdk, \
             patch("util.saas.exceptionlog.SENTRY_SDK_AVAILABLE", True):
            
            mock_sentry_sdk.init.return_value = None
            mock_sentry_sdk.capture_message.return_value = None
            
            # Import after patching
            from util.saas.exceptionlog import Sentry

            sentry = Sentry(mock_app)

            # Test the connection
            result = sentry.test_sentry_connection()

            mock_sentry_sdk.capture_message.assert_called_once_with(
                "Manual Sentry connection test", level="info"
            )

            assert result is True

    def test_sentry_connection_test_with_fake_sentry(self):
        """Test that test_sentry_connection returns False when using FakeSentry."""
        from util.saas.exceptionlog import Sentry
        
        mock_app = MagicMock()
        mock_app.config.get.side_effect = lambda key, default=None: {
            "EXCEPTION_LOG_TYPE": "FakeSentry",
        }.get(key, default)

        sentry = Sentry(mock_app)
        result = sentry.test_sentry_connection()

        assert result is False

    def test_sentry_connection_test_no_dsn(self):
        """Test that test_sentry_connection returns False when no DSN is configured."""
        from util.saas.exceptionlog import Sentry
        
        mock_app = MagicMock()
        mock_app.config.get.side_effect = lambda key, default=None: {
            "EXCEPTION_LOG_TYPE": "Sentry",
            "SENTRY_DSN": None,
        }.get(key, default)

        sentry = Sentry(mock_app)
        result = sentry.test_sentry_connection()

        assert result is False