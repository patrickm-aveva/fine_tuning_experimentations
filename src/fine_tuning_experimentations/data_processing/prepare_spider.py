"""Convert raw Spider data into backend-neutral canonical JSONL records."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any