"""Retry logic with exponential backoff."""

import asyncio
from typing import Callable, Any, Type
from functools import wraps


async def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    exceptions: tuple = (Exception,)
) -> Any:
    """Retry function with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return await func()
        except exceptions as e:
            if attempt == max_retries - 1:
                raise
            
            delay = min(base_delay * (2 ** attempt), max_delay)
            await asyncio.sleep(delay)
    
    raise Exception("Max retries exceeded")


def with_retry(max_retries: int = 3, base_delay: float = 1.0):
    """Decorator for retry with exponential backoff."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_with_backoff(
                lambda: func(*args, **kwargs),
                max_retries=max_retries,
                base_delay=base_delay
            )
        return wrapper
    return decorator

