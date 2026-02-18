"""
Shared concurrency limit for async pipelines that do parallel fetches.

Import semaphore here so all pipelines use the same limit without redefining it.
Tune max_concurrent_requests to avoid overwhelming the API.
"""

import asyncio

max_concurrent_requests = 8
semaphore = asyncio.Semaphore(max_concurrent_requests)
