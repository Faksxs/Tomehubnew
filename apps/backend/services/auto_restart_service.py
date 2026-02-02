
import asyncio
import logging
import os
import signal
import time
from .memory_monitor_service import MemoryMonitor

logger = logging.getLogger("tomehub_api")

class AutoRestartManager:
    """
    Background task that monitors memory and triggers graceful shutdown
    if thresholds are exceeded.
    """
    def __init__(self):
        from config import settings
        self.is_running = False
        self.check_interval = 10 # seconds
        self.critical_threshold = settings.MEMORY_CRITICAL_THRESHOLD
        self.warning_threshold = settings.MEMORY_WARNING_THRESHOLD
        self._last_alert = 0
        self._consecutive_criticals = 0

    async def monitor(self):
        """Main monitoring loop started by lifespan."""
        self.is_running = True
        logger.info(f"Memory Monitor started (Interval: {self.check_interval}s, Threshold: {self.critical_threshold}%)")
        
        while self.is_running:
            try:
                status = MemoryMonitor.check_memory_health(self.critical_threshold)
                stats = MemoryMonitor.get_memory_stats()
                
                if status == "CRITICAL":
                    self._consecutive_criticals += 1
                    logger.error(f"⚠️ HIGH MEMORY ALERT ({self._consecutive_criticals}/3): {stats['system_percent']}% used (RSS: {stats['rss_mb']}MB)")
                    
                    # If sustained critical usage, trigger restart logic
                    if self._consecutive_criticals >= 3:
                        # Task A2 extension: Only shutdown in production
                        from config import settings
                        if settings.ENVIRONMENT == "production":
                            logger.critical("🚨 MEMORY CRITICAL: Initiating Graceful Shutdown to prevent OOM Kill...")
                            os.kill(os.getpid(), signal.SIGTERM)
                        else:
                            logger.warning("🚨 MEMORY CRITICAL: Shutdown skipped (Development Mode)")
                        
                elif status == "WARNING":
                    self._consecutive_criticals = 0
                    if time.time() - self._last_alert > 60: # Alert max once per minute
                        logger.warning(f"⚠️ Memory Warning: {stats['system_percent']}% used (RSS: {stats['rss_mb']}MB)")
                        self._last_alert = time.time()
                else:
                    self._consecutive_criticals = 0
                    
                await asyncio.sleep(self.check_interval)
                
            except asyncio.CancelledError:
                logger.info("Memory Monitor stopped.")
                break
            except Exception as e:
                logger.error(f"Error in memory monitor: {e}")
                await asyncio.sleep(self.check_interval)

    async def get_status(self):
        status = MemoryMonitor.check_memory_health(self.critical_threshold)
        stats = MemoryMonitor.get_memory_stats()
        return {
            "monitoring_active": self.is_running,
            "current_usage": stats['system_percent'],
            "threshold": self.critical_threshold,
            "status": status,
            "consecutive_criticals": self._consecutive_criticals
        }

# Global instance
auto_restart_manager = AutoRestartManager()
