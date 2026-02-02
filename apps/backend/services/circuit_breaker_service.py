"""
Circuit Breaker Service for TomeHub
====================================
Implements circuit breaker pattern for external API calls (Gemini embeddings).

Prevents cascading failures:
- Fail fast when API is unavailable
- Automatic recovery after timeout
- Metrics and logging for observability

Author: TomeHub Team
Date: 2026-02-02
"""

import time
import logging
from typing import Optional, Callable, Any
from enum import Enum
from datetime import datetime, timedelta
import threading

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"          # Normal operation
    OPEN = "open"              # Too many failures, rejecting calls
    HALF_OPEN = "half_open"    # Testing if service recovered


class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior"""
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 300,  # seconds
        expected_exception: Exception = Exception,
        name_suffix: str = ""
    ):
        self.name = f"{name}{name_suffix}"
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception


class CircuitBreaker:
    """
    Circuit Breaker Pattern Implementation
    
    States:
    - CLOSED: Normal operation, all calls pass through
    - OPEN: Too many failures, calls rejected immediately
    - HALF_OPEN: Testing if service recovered, allow one test call
    
    Behavior:
    - Track consecutive failures
    - When failures exceed threshold: transition to OPEN
    - After timeout: transition to HALF_OPEN
    - Success in HALF_OPEN: transition to CLOSED
    - Failure in HALF_OPEN: transition to OPEN
    """
    
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.last_state_change = datetime.now()
        self.lock = threading.RLock()
        
        logger.info(f"✓ Circuit breaker initialized: {config.name}")
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Raises:
            CircuitBreakerOpenException: If circuit is open
            CircuitBreakerHalfOpenException: If testing in half-open state
            Original exception from func: If call fails
        """
        with self.lock:
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    # Transition to HALF_OPEN to test recovery
                    self._transition_to_half_open()
                else:
                    # Still in OPEN state, fail fast
                    time_remaining = self._time_until_reset()
                    raise CircuitBreakerOpenException(
                        f"Circuit {self.config.name} is OPEN. "
                        f"Recovery in {time_remaining}s. Service unavailable."
                    )
        
        # Call the function
        try:
            result = func(*args, **kwargs)
            
            # Success!
            with self.lock:
                if self.state == CircuitState.HALF_OPEN:
                    # Successfully recovered
                    self._transition_to_closed()
                    logger.info(f"✓ {self.config.name} recovered (HALF_OPEN → CLOSED)")
                elif self.state == CircuitState.CLOSED:
                    # Normal success, reset failure count
                    self.failure_count = 0
            
            return result
            
        except Exception as e:
            with self.lock:
                self._record_failure()
                
                if self.state == CircuitState.HALF_OPEN:
                    # Recovery failed, go back to OPEN
                    self._transition_to_open()
                    logger.warning(
                        f"⚠️ {self.config.name} recovery failed. "
                        f"Transitioning HALF_OPEN → OPEN. Error: {type(e).__name__}"
                    )
                elif self.state == CircuitState.CLOSED:
                    if self.failure_count >= self.config.failure_threshold:
                        # Exceeded failure threshold
                        self._transition_to_open()
                        logger.warning(
                            f"⚠️ {self.config.name} circuit breaker OPEN. "
                            f"Failures: {self.failure_count}/{self.config.failure_threshold}"
                        )
            
            raise
    
    def _record_failure(self):
        """Record a failure and update counters"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery"""
        if not self.last_failure_time:
            return False
        
        time_since_failure = (datetime.now() - self.last_failure_time).total_seconds()
        return time_since_failure >= self.config.recovery_timeout
    
    def _time_until_reset(self) -> int:
        """Get seconds until recovery can be attempted"""
        if not self.last_failure_time:
            return self.config.recovery_timeout
        
        elapsed = (datetime.now() - self.last_failure_time).total_seconds()
        remaining = self.config.recovery_timeout - elapsed
        return max(0, int(remaining))
    
    def _transition_to_open(self):
        """Transition circuit to OPEN state"""
        self.state = CircuitState.OPEN
        self.last_state_change = datetime.now()
        logger.warning(f"🔴 {self.config.name} circuit breaker OPEN")
    
    def _transition_to_half_open(self):
        """Transition circuit to HALF_OPEN state (testing recovery)"""
        self.state = CircuitState.HALF_OPEN
        self.failure_count = 0
        self.last_state_change = datetime.now()
        logger.info(f"🟡 {self.config.name} circuit breaker HALF_OPEN (testing recovery)")
    
    def _transition_to_closed(self):
        """Transition circuit to CLOSED state (normal operation)"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_state_change = datetime.now()
        logger.info(f"🟢 {self.config.name} circuit breaker CLOSED (normal operation)")
    
    def get_status(self) -> dict:
        """Get current circuit breaker status"""
        with self.lock:
            return {
                "name": self.config.name,
                "state": self.state.value,
                "failure_count": self.failure_count,
                "failure_threshold": self.config.failure_threshold,
                "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
                "last_state_change": self.last_state_change.isoformat(),
                "time_until_reset_seconds": self._time_until_reset() if self.state == CircuitState.OPEN else 0
            }


class CircuitBreakerOpenException(Exception):
    """Raised when circuit breaker is open and call was rejected"""
    pass


class CircuitBreakerHalfOpenException(Exception):
    """Raised when testing recovery in half-open state"""
    pass


class RetryConfig:
    """Configuration for retry logic with exponential backoff"""
    
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,  # seconds
        max_delay: float = 32.0,     # seconds
        backoff_factor: float = 2.0,
        jitter: bool = True
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay for attempt number (0-indexed)"""
        import random
        
        delay = min(
            self.initial_delay * (self.backoff_factor ** attempt),
            self.max_delay
        )
        
        if self.jitter:
            # Add random jitter to prevent thundering herd
            delay = delay * (0.5 + random.random())
        
        return delay


def retry_with_backoff(
    func: Callable,
    config: RetryConfig,
    *args,
    **kwargs
) -> Any:
    """
    Execute function with retry logic and exponential backoff.
    
    Args:
        func: Function to call
        config: RetryConfig with retry parameters
        *args, **kwargs: Arguments to pass to function
    
    Returns:
        Result from func
    
    Raises:
        Last exception if all retries exhausted
    """
    last_exception = None
    
    for attempt in range(config.max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            
            if attempt < config.max_retries:
                delay = config.get_delay(attempt)
                logger.warning(
                    f"⚠️ Retry {attempt + 1}/{config.max_retries} "
                    f"(delay: {delay:.1f}s). Error: {type(e).__name__}: {str(e)[:100]}"
                )
                time.sleep(delay)
            else:
                logger.error(
                    f"❌ All {config.max_retries + 1} retries exhausted. "
                    f"Final error: {type(e).__name__}: {str(e)[:100]}"
                )
    
    raise last_exception


# Global circuit breaker for embedding API
_embedding_circuit_breaker: Optional[CircuitBreaker] = None


def get_embedding_circuit_breaker() -> CircuitBreaker:
    """Get or create global embedding circuit breaker"""
    global _embedding_circuit_breaker
    
    if _embedding_circuit_breaker is None:
        config = CircuitBreakerConfig(
            name="embedding_api",
            failure_threshold=5,
            recovery_timeout=300,  # 5 minutes
        )
        _embedding_circuit_breaker = CircuitBreaker(config)
    
    return _embedding_circuit_breaker
