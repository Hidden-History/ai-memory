#!/bin/bash
# AI Memory Module - Comprehensive Health Check
# Purpose: Validate all memory system components in one command
# Usage: ./scripts/memory/health_check.sh
# Exit codes: 0 = healthy, 1 = needs attention
# Author: AI Memory Module Team
# Last validated: 2026-01-13

# Strict mode: exit on error, undefined vars, pipe failures
set -euo pipefail

# Exit code constants (per bash best practices)
readonly EXIT_HEALTHY=0
readonly EXIT_NEEDS_ATTENTION=1

# Cleanup trap - ensure we always report status
cleanup() {
    local exit_code=$?
    if [ $exit_code -ne 0 ] && [ $exit_code -ne $EXIT_NEEDS_ATTENTION ]; then
        echo ""
        echo -e "${RED}Health check terminated unexpectedly (exit code: $exit_code)${NC}"
        echo "Check script errors above for details."
    fi
}
trap cleanup EXIT

echo "=== AI Memory Module Health Check ==="
echo ""

# Colors for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly NC='\033[0m' # No Color

ERRORS=0
WARNINGS=0

# Check 1: Docker running
echo -n "Docker daemon... "
if docker ps > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${RED}✗ Not running${NC}"
    echo "  → Run: sudo systemctl start docker (Linux) or open Docker Desktop (macOS)"
    echo "  → See: docs/RECOVERY.md#qdrant-unavailable"
    ((ERRORS++))
fi

# Check 2: Qdrant container
echo -n "Qdrant container... "
if docker compose -f ~/.ai-memory/docker/docker-compose.yml ps qdrant 2>/dev/null | grep -q "running"; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${RED}✗ Not running${NC}"
    echo "  → Run: docker compose -f ~/.ai-memory/docker/docker-compose.yml up -d qdrant"
    echo "  → See: docs/RECOVERY.md#qdrant-unavailable"
    ((ERRORS++))
fi

# Check 3: Qdrant health endpoint
echo -n "Qdrant health... "
if curl -sf http://localhost:26350/healthz > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Healthy${NC}"
else
    echo -e "${RED}✗ Unhealthy${NC}"
    echo "  → See: docs/RECOVERY.md#qdrant-unavailable"
    ((ERRORS++))
fi

# Check 4: Qdrant collections
echo -n "Qdrant collections... "
COLLECTIONS=$(curl -sf http://localhost:26350/collections 2>/dev/null | grep -o '"name":"[^"]*"' | wc -l)
if [ "$COLLECTIONS" -ge 2 ]; then
    echo -e "${GREEN}✓ Found $COLLECTIONS collections${NC}"
else
    echo -e "${YELLOW}⚠ Only $COLLECTIONS collections (expected 2+)${NC}"
    echo "  → May need initialization"
    ((WARNINGS++))
fi

# Check 5: Embedding service container
echo -n "Embedding service... "
if docker compose -f ~/.ai-memory/docker/docker-compose.yml ps embedding 2>/dev/null | grep -q "running"; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${RED}✗ Not running${NC}"
    echo "  → Run: docker compose -f ~/.ai-memory/docker/docker-compose.yml up -d embedding"
    echo "  → See: docs/RECOVERY.md#embedding-service-unavailable"
    ((ERRORS++))
fi

# Check 6: Embedding service health
echo -n "Embedding health... "
if curl -sf http://localhost:28080/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Healthy${NC}"
else
    echo -e "${YELLOW}⚠ Unhealthy (may be loading model)${NC}"
    echo "  → Wait 30-90s for model load, then retry"
    echo "  → See: docs/RECOVERY.md#embedding-service-unavailable"
    ((WARNINGS++))
fi

# Check 7: Embedding generation
echo -n "Embedding generation... "
EMBED_TEST=$(curl -sf -X POST http://localhost:28080/embed \
  -H "Content-Type: application/json" \
  -d '{"texts":["test"]}' 2>/dev/null)
if echo "$EMBED_TEST" | grep -q "embeddings"; then
    echo -e "${GREEN}✓ Working${NC}"
else
    echo -e "${RED}✗ Failed${NC}"
    echo "  → See: docs/RECOVERY.md#embedding-service-unavailable"
    ((ERRORS++))
fi

# Check 8: Queue file
echo -n "Queue file... "
if [ -f ~/.claude-memory/pending_queue.jsonl ]; then
    QUEUE_SIZE=$(wc -l < ~/.claude-memory/pending_queue.jsonl)
    if [ "$QUEUE_SIZE" -eq 0 ]; then
        echo -e "${GREEN}✓ Empty (no pending items)${NC}"
    else
        echo -e "${YELLOW}⚠ $QUEUE_SIZE items pending${NC}"
        echo "  → Run: python scripts/memory/backfill_embeddings.py"
        ((WARNINGS++))
    fi
else
    echo -e "${GREEN}✓ Not created yet (normal on fresh install)${NC}"
fi

# Check 9: Stale locks
echo -n "Stale locks... "
STALE_LOCKS=$(find ~/.claude-memory -name "*.lock" -mmin +60 2>/dev/null | wc -l)
if [ "$STALE_LOCKS" -eq 0 ]; then
    echo -e "${GREEN}✓ None${NC}"
else
    echo -e "${YELLOW}⚠ Found $STALE_LOCKS stale locks${NC}"
    echo "  → Run: rm ~/.claude-memory/*.lock"
    echo "  → See: docs/RECOVERY.md#queue-file-issues"
    ((WARNINGS++))
fi

# Check 10: Disk space
echo -n "Disk space... "
DISK_FREE=$(df -h ~/.claude-memory 2>/dev/null | awk 'NR==2 {print $4}' | sed 's/G//')
if [ -n "$DISK_FREE" ]; then
    if (( $(echo "$DISK_FREE > 5" | bc -l 2>/dev/null || echo 0) )); then
        echo -e "${GREEN}✓ ${DISK_FREE}GB free${NC}"
    elif (( $(echo "$DISK_FREE > 1" | bc -l 2>/dev/null || echo 0) )); then
        echo -e "${YELLOW}⚠ ${DISK_FREE}GB free (low)${NC}"
        echo "  → Consider cleanup"
        ((WARNINGS++))
    else
        echo -e "${RED}✗ ${DISK_FREE}GB free (critical)${NC}"
        echo "  → Free space immediately"
        ((ERRORS++))
    fi
else
    echo -e "${YELLOW}⚠ Unable to check (directory may not exist)${NC}"
    ((WARNINGS++))
fi

# Check 11: End-to-end test (storage + retrieval)
echo -n "End-to-end test... "
E2E_RESULT=$(python -c "
import sys
try:
    from memory.storage import MemoryStorage
    from memory.search import MemorySearch
    import time

    # Store test memory
    storage = MemoryStorage()
    result = storage.store_memory(
        content='Health check test ' + str(time.time()),
        group_id='health-check',
        memory_type='implementation',
        source_hook='HealthCheck',
        session_id='health-check'
    )

    # Search for it
    time.sleep(1)  # Brief wait for embedding
    search = MemorySearch()
    results = search.search(query='Health check test', collection='implementations', limit=1)

    if len(results) > 0:
        print('success')
    else:
        print('no_results')
except Exception as e:
    print(f'error:{e}')
" 2>&1)

if echo "$E2E_RESULT" | grep -q "success"; then
    echo -e "${GREEN}✓ Passed${NC}"
elif echo "$E2E_RESULT" | grep -q "no_results"; then
    echo -e "${YELLOW}⚠ Storage works, search limited${NC}"
    echo "  → Embedding service may be slow"
    ((WARNINGS++))
else
    echo -e "${RED}✗ Failed: $E2E_RESULT${NC}"
    echo "  → Check docs/RECOVERY.md"
    ((ERRORS++))
fi

# Summary
echo ""
echo "=== Summary ==="
if [ "$ERRORS" -eq 0 ] && [ "$WARNINGS" -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed - system healthy${NC}"
    exit $EXIT_HEALTHY
elif [ "$ERRORS" -eq 0 ]; then
    echo -e "${YELLOW}⚠ $WARNINGS warnings - system functional with minor issues${NC}"
    exit $EXIT_HEALTHY
else
    echo -e "${RED}✗ $ERRORS errors, $WARNINGS warnings - recovery needed${NC}"
    echo ""
    echo "See docs/RECOVERY.md for detailed recovery procedures"
    exit $EXIT_NEEDS_ATTENTION
fi
