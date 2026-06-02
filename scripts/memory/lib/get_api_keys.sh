#!/usr/bin/env bash
# Sourced helper — exports QDRANT_API_KEY from ~/.ai-memory/docker/.env.
# Silent fallback: missing/empty .env yields QDRANT_API_KEY="", exit 0.
export QDRANT_API_KEY="$(grep QDRANT_API_KEY ~/.ai-memory/docker/.env | cut -d= -f2)"
