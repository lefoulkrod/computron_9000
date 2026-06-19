"""Channels — entry points that receive user input and run agent turns.

Each subpackage (``telegram``, future ones) hosts one channel implementation.
A channel constructs an ``Agent``, builds a ``Conversation``, and drives the
turn loop via ``sdk.TurnExecutor``.
"""
