import logging
import signal
import socket
import sys
import time
from datetime import datetime, timedelta
from functools import wraps
from random import randint
from threading import Event

import sentry_sdk
from apscheduler.schedulers.background import BackgroundScheduler
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.stdlib import StdlibIntegration

import features
from app import app
from data.database import UseThenDisconnect
from util.log import logfile_path

logger = logging.getLogger(__name__)


def with_exponential_backoff(backoff_multiplier=10, max_backoff=3600, max_retries=10):
    def inner(func):
        """
        Decorator to retry the operation with exponential backoff if it raised an exception.

        Waits 2^attempts * `backoff_multiplier`, up to `max_backoff`, up to `max_retries` number of time,
        then re-raise the exception.
        """

        def wrapper(*args, **kwargs):
            attempts = 0
            backoff = 0

            while True:
                next_backoff = 2**attempts * backoff_multiplier
                backoff = min(next_backoff, max_backoff)
                attempts += 1

                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if max_retries is not None and attempts == max_retries:
                        raise e

                logger.exception("Operation raised exception, retrying in %d seconds", backoff)
                time.sleep(backoff)

        return wrapper

    return inner


class Worker(object):
    """
    Base class for workers which perform some work periodically.
    """

    def __init__(self):
        self._sched = BackgroundScheduler()
        self._operations = []
        self._stop = Event()
        self._terminated = Event()

        worker_name = "%s:worker-%s" % (socket.gethostname(), self.__class__.__name__)

        if app.config.get("EXCEPTION_LOG_TYPE", "FakeSentry") == "Sentry":
            sentry_dsn = app.config.get("SENTRY_DSN", "")
            if sentry_dsn:
                try:
                    integrations = []

                    # Always include logging integration
                    integrations.append(
                        LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)
                    )

                    # Only add Flask and SQLAlchemy integrations if OpenTelemetry is not enabled
                    if not getattr(features, "OTEL_TRACING", False):
                        integrations.extend(
                            [
                                FlaskIntegration(transaction_style="endpoint"),
                                SqlalchemyIntegration(),
                                StdlibIntegration(),
                            ]
                        )
                    else:
                        logger.info(
                            "OpenTelemetry enabled - using minimal Sentry integrations for worker"
                        )

                    sentry_sdk.init(
                        dsn=sentry_dsn,
                        environment=app.config.get("SENTRY_ENVIRONMENT", "production"),
                        traces_sample_rate=app.config.get("SENTRY_TRACES_SAMPLE_RATE", 0.1),
                        profiles_sample_rate=app.config.get("SENTRY_PROFILES_SAMPLE_RATE", 0.1),
                        integrations=integrations,
                        default_integrations=False,
                        auto_session_tracking=True,
                        # Fix connection pool issues
                        transport=sentry_sdk.transport.make_transport(
                            {
                                "pool_connections": 10,  # Instead of 1
                                "pool_maxsize": 20,  # Max connections per pool
                                "max_retries": 3,  # Retry failed sends
                            }
                        ),
                    )
                    sentry_sdk.set_tag("worker", worker_name)
                except Exception as e:
                    logger.warning("Failed to initialize Sentry: %s", str(e))

    def is_healthy(self):
        return not self._stop.is_set()

    def is_terminated(self):
        return self._terminated.is_set()

    def ungracefully_terminated(self):
        """
        Method called when the worker has been terminated in an ungraceful fashion.
        """
        pass

    def add_operation(self, operation_func, operation_sec):
        @wraps(operation_func)
        def _operation_func():
            try:
                with UseThenDisconnect(app.config):
                    return operation_func()
            except Exception:
                logger.exception("Operation raised exception")
                # Sentry SDK automatically captures exceptions when configured
                sentry_sdk.capture_exception()

        self._operations.append((_operation_func, operation_sec))

    def _setup_and_wait_for_shutdown(self):
        signal.signal(signal.SIGTERM, self.terminate)
        signal.signal(signal.SIGINT, self.terminate)

        while not self._stop.wait(1):
            pass

    def start(self):
        logging.config.fileConfig(logfile_path(debug=False), disable_existing_loggers=False)

        if not app.config.get("SETUP_COMPLETE", False):
            logger.info("Product setup is not yet complete; skipping worker startup")
            self._setup_and_wait_for_shutdown()
            return

        if app.config.get("REGISTRY_STATE", "normal") == "readonly":
            logger.info("Product is in read-only mode; skipping worker startup")
            self._setup_and_wait_for_shutdown()
            return

        logger.debug("Scheduling worker.")

        self._sched.start()
        for operation_func, operation_sec in self._operations:
            start_date = datetime.now() + timedelta(seconds=0.001)
            if app.config.get("STAGGER_WORKERS"):
                start_date += timedelta(seconds=randint(1, operation_sec))
            logger.debug("First run scheduled for %s", start_date)
            self._sched.add_job(
                operation_func,
                "interval",
                seconds=operation_sec,
                start_date=start_date,
                max_instances=1,
            )

        self._setup_and_wait_for_shutdown()

        logger.debug("Waiting for running tasks to complete.")
        self._sched.shutdown()
        logger.debug("Finished.")

        self._terminated.set()

    def terminate(self, signal_num=None, stack_frame=None, graceful=False):
        if self._terminated.is_set():
            sys.exit(1)

        else:
            logger.debug("Shutting down worker.")
            self._stop.set()

            if not graceful:
                self.ungracefully_terminated()

    def join(self):
        self.terminate(graceful=True)
