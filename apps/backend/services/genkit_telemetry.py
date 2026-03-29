# -*- coding: utf-8 -*-
import logging
import asyncio
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Mock Genkit objects for no-op execution
class MockGenkit:
    def define_flow(self, *args, **kwargs):
        def decorator(f):
            return f
        return decorator
    
    async def run(self, name: str, func: Callable, *args, **kwargs):
        """Mock ai.run for async execution without tracking."""
        if asyncio.iscoroutinefunction(func):
            # If the callable is a coroutine function, await it
            if callable(func):
                return await func(*args, **kwargs)
            return await func
        else:
            # Otherwise call it directly
            if callable(func):
                return func(*args, **kwargs)
            return func

ai = MockGenkit()

class MockZ:
    def object(self, *args, **kwargs):
        return self
    def string(self):
        return self
    def number(self):
        return self
    def optional(self):
        return self
    def any(self):
        return self

z = MockZ()

def track_l3_call(name: str):
    """
    Mocked track_l3_call that does nothing (no-op).
    Used to remove Genkit dependency while maintaining imports.
    """
    def decorator(f: Callable):
        return f
    return decorator
