import logging


# Configure logging filter to suppress healthcheck endpoint logs
class HealthcheckLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "/health" in message or "/ready" in message:
            return False
        return True


# Apply the filter to uvicorn access logger
uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.addFilter(HealthcheckLogFilter())

# Create application logger (separate from uvicorn's access logger)
# uvicorn.access uses a special formatter that expects HTTP request args,
# so we use a standard logger for application messages
logger = logging.getLogger("shoot")
logger.setLevel(logging.INFO)

# Add handler if not already configured (avoid duplicate logs)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(handler)
