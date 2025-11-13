import logging

# Configure logging filter to suppress healthcheck endpoint logs
class HealthcheckLogFilter(logging.Filter):    
    def filter(self, record):
        message = record.getMessage()
        if "/health" in message or "/ready" in message:
            return False
        return True

# Apply the filter to uvicorn access logger
logger = logging.getLogger("uvicorn.access")
logger.addFilter(HealthcheckLogFilter())


