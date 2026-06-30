"""LLM model port."""

from __future__ import annotations

from typing import Protocol, TypeVar

T = TypeVar("T")


class StructuredInvoker(Protocol[T]):
    def invoke(self, messages):
        ...


class ChatModel(Protocol):
    def with_structured_output(self, schema: type[T]) -> StructuredInvoker[T]:
        ...
