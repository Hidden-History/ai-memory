#!/usr/bin/env python3
"""PLACEHOLDER - Stop hook removed in TECH-DEBT-012 Phase 5.

This file exists only to prevent errors in sessions that started before
the hook was removed from settings.json. New sessions will not call this.

The real session_stop.py is archived at: archived/session_stop.py
Reason: Duplicated PreCompact functionality. User prefers manual /save-memory.
"""
import sys
sys.exit(0)
