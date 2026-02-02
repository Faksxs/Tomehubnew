
import psutil
import os
import logging

logger = logging.getLogger("tomehub_api")

class MemoryMonitor:
    """
    Monitors system memory usage to prevent OOM kills.
    Implements Task A2: Memory monitoring + alerting.
    """
    
    @staticmethod
    def get_memory_stats():
        """Returns current memory usage statistics."""
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        
        system_mem = psutil.virtual_memory()
        
        return {
            "rss_mb": round(mem_info.rss / 1024 / 1024, 2), # Resident Set Size
            "vms_mb": round(mem_info.vms / 1024 / 1024, 2), # Virtual Memory Size
            "system_percent": system_mem.percent,
            "system_available_mb": round(system_mem.available / 1024 / 1024, 2)
        }
        
    @staticmethod
    def check_memory_health(threshold_percent=85.0):
        """
        Checks if memory usage is critical.
        Returns: 'HEALTHY', 'WARNING', or 'CRITICAL'
        """
        stats = MemoryMonitor.get_memory_stats()
        usage = stats['system_percent']
        
        if usage >= threshold_percent:
            return "CRITICAL"
        elif usage >= (threshold_percent - 10): # e.g. 75%
            return "WARNING"
        return "HEALTHY"

    @staticmethod
    def get_status_emoji(status):
        if status == "CRITICAL": return "🔴"
        if status == "WARNING": return "🟡"
        return "🟢"
