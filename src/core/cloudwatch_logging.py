"""
CloudWatch logging via watchtower.

Adds a CloudWatch Logs handler that sends only pipeline-relevant logs
(story/book/image generation milestones and errors) to keep costs minimal.

Requires:
  - pip install watchtower
  - IAM permissions for CloudWatch Logs (EC2 instance role or env credentials)

Environment variables:
  CLOUDWATCH_ENABLED    - Set to "true" to enable (default: disabled)
  CLOUDWATCH_LOG_GROUP  - CloudWatch log group name (default: /app/ai-book-creation)
  CLOUDWATCH_LOG_STREAM - Stream name (default: auto-generated from hostname + pid)
"""

import logging
import os

logger = logging.getLogger(__name__)


class PipelineLogFilter(logging.Filter):
    """Only pass through logs from pipeline modules or ERROR+ from anywhere."""

    PIPELINE_MODULES = (
        "src.tasks.",
        "src.core.story_generator",
        "src.core.image_generator",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        # Always send ERROR and above from any module
        if record.levelno >= logging.ERROR:
            return True

        # Send INFO+ from pipeline modules only
        if record.levelno >= logging.INFO:
            return any(record.name.startswith(m) for m in self.PIPELINE_MODULES)

        return False


def setup_cloudwatch_logging() -> bool:
    """
    Attach a CloudWatch handler to the root logger.

    Returns True if CloudWatch logging was enabled, False otherwise.
    Fails silently if watchtower is not installed or credentials are missing.
    """
    if os.getenv("CLOUDWATCH_ENABLED", "").lower() != "true":
        return False

    try:
        import watchtower
    except ImportError:
        logger.warning("CLOUDWATCH_ENABLED=true but watchtower is not installed. pip install watchtower")
        return False

    log_group = os.getenv("CLOUDWATCH_LOG_GROUP", "/app/ai-book-creation")

    try:
        handler = watchtower.CloudWatchLogHandler(
            log_group_name=log_group,
            log_stream_name=os.getenv("CLOUDWATCH_LOG_STREAM"),
            send_interval=10,
            max_batch_count=100,
        )
        handler.setLevel(logging.INFO)
        handler.addFilter(PipelineLogFilter())
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )

        logging.getLogger().addHandler(handler)
        logger.info("CloudWatch logging enabled: group=%s", log_group)
        return True

    except Exception as e:
        logger.warning("Failed to initialize CloudWatch logging: %s", e)
        return False


def flush_cloudwatch_logging() -> None:
    """Flush and close any CloudWatch handlers. Call on app shutdown."""
    try:
        import watchtower
    except ImportError:
        return

    for handler in logging.getLogger().handlers:
        if isinstance(handler, watchtower.CloudWatchLogHandler):
            handler.flush()
            handler.close()
