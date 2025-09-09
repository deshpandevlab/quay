import logging

try:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    SENTRY_SDK_AVAILABLE = True
except ImportError:
    sentry_sdk = None
    SENTRY_SDK_AVAILABLE = False

logger = logging.getLogger(__name__)


class FakeSentryClient(object):
    def captureException(self, *args, **kwargs):
        pass

    def user_context(self, *args, **kwargs):
        pass


class FakeSentry(object):
    def __init__(self):
        self.client = FakeSentryClient()


class Sentry(object):
    def __init__(self, app=None):
        self.app = app
        self.is_real_sentry = False
        if app is not None:
            self.state = self.init_app(app)
        else:
            self.state = None

    def init_app(self, app):
        sentry_type = app.config.get("EXCEPTION_LOG_TYPE", "FakeSentry")
        sentry_dsn = app.config.get("SENTRY_DSN")

        if sentry_type == "Sentry" and sentry_dsn and SENTRY_SDK_AVAILABLE:
            logger.info(f"Initializing Sentry with DSN: {sentry_dsn[:30]}...")
            
            # Configure integrations
            integrations = [FlaskIntegration()]
            
            # Check if OpenTelemetry is being used (minimal integrations in that case)
            if self._is_opentelemetry_enabled(app):
                logger.info("OpenTelemetry enabled - using minimal Sentry integrations")
                integrations = [
                    FlaskIntegration(),
                    LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)
                ]
            
            # Initialize Sentry SDK
            sentry_sdk.init(
                dsn=sentry_dsn,
                environment=app.config.get("SENTRY_ENVIRONMENT", "production"),
                integrations=integrations,
                traces_sample_rate=app.config.get("SENTRY_TRACES_SAMPLE_RATE", 0.1),
                profiles_sample_rate=app.config.get("SENTRY_PROFILES_SAMPLE_RATE", 0.1),
            )
            
            self.is_real_sentry = True
            logger.info("Sentry initialization completed successfully")
            sentry = self
        else:
            sentry = FakeSentry()

        # register extension with app
        app.extensions = getattr(app, "extensions", {})
        app.extensions["sentry"] = sentry
        return sentry

    def _is_opentelemetry_enabled(self, app):
        """Check if OpenTelemetry is enabled in the app config."""
        return app.config.get("OTEL_EXPORTER_OTLP_ENDPOINT") is not None

    def test_sentry_connection(self):
        """Test the Sentry connection by sending a test message."""
        if not self.is_real_sentry:
            logger.info("Using FakeSentry - connection test skipped")
            return False
        
        if not SENTRY_SDK_AVAILABLE:
            logger.error("Sentry SDK not available")
            return False
        
        try:
            sentry_sdk.capture_message("Manual Sentry connection test", level="info")
            logger.info("Sentry connection test message sent successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to send Sentry test message: {e}")
            return False

    def __getattr__(self, name):
        return getattr(self.state, name, None)
