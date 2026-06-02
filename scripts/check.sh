#!/usr/bin/env bash
# DESC: Fast-fail gate: arch → lint → smoke → unit → property → appearance → integration → cohesion → outputgen → docs
# Usage: ./dev check [-v]
#
# Tiered staircase, ordered by cost × blast-radius — cheapest / most fundamental
# failures abort first, so you never read noise from a downstream tier when the
# foundation is broken:
#   0. Static     arch invariants (AST only) + ty + ruff — no code executes
#   1. Smoke      import every submodule + demo/tour/slide liveness (cheapest tests
#                 that can FAIL; arch only parses, never imports — catches cycle rot)
#   2. Unit       pure unit tests (arch excluded — it ran in tier 0)
#   3. Property   Hypothesis laws (width-awareness, compose arithmetic, writer totality)
#   4. Appearance structured char+style snapshots (the styled-layer contract; the
#                 successor to the retired demo-text goldens — see golden-migration-plan.md)
#   5. Integration end-to-end run_cli/run_app dispatch through the real CLI path
#   6. Cohesion   the WHOLE suite in ONE process — tiers 1-5 run in separate pytest
#                 processes, so a cross-test leak (sys.modules / lazy-facade / ContextVar
#                 pollution) can be green per-tier yet red in the single-process run that
#                 `./dev test`, CI, and IDEs actually do. This backstop is redundant by
#                 design: it re-runs everything to assert the tiers cohere as one process.
#   7. Outputgen  demo → HTML → markdown integration
#   8. Docs       fragment bodies not drifted (docgen --update is current) + consumer-guide
#                 README<->CLAUDE.md symlinks present. Scoped to docs-system managed
#                 surfaces (the legacy guide/slide selectors are repaired in a later pass).
# Budget (coverage, perf, mutation) is intentionally NOT here — run `./dev cov`.
# Coverage is informational and not gated (no --cov-fail-under floor today).
source "$(dirname "$0")/lib/dev.sh"

# Unit tier re-running the arch file would duplicate tier 0; skip it there.
UNIT_ARGS=(tests/unit/ --ignore=tests/unit/test_architecture_invariants.py)

main() {
    local verbose=0

    for arg in "$@"; do
        case "$arg" in
            -v|--verbose) verbose=1 ;;
            --help|-h)
                echo "Usage: ./dev check [-v]"
                echo "  -v  Show verbose output on each step"
                exit 0
                ;;
        esac
    done

    cd "$PROJECT_ROOT"

    if [ $verbose -eq 1 ]; then
        echo -e "${BOLD}=== Architecture ===${NC}"
        run_uv pytest tests/unit/test_architecture_invariants.py -v --tb=short
        echo ""
        echo -e "${BOLD}=== Lint ===${NC}"
        run_uv ty check src/
        run_uv ruff format --check src/ tests/
        echo ""
        echo -e "${BOLD}=== Smoke ===${NC}"
        run_uv pytest tests/smoke/ -v --tb=short
        echo ""
        echo -e "${BOLD}=== Unit ===${NC}"
        run_uv pytest "${UNIT_ARGS[@]}" -v --tb=short
        echo ""
        echo -e "${BOLD}=== Property ===${NC}"
        run_uv pytest tests/property/ -v --tb=short
        echo ""
        echo -e "${BOLD}=== Appearance ===${NC}"
        run_uv pytest tests/appearance/ -v --tb=short
        echo ""
        echo -e "${BOLD}=== Integration ===${NC}"
        run_uv pytest tests/integration/ -v --tb=short
        echo ""
        echo -e "${BOLD}=== Cohesion (whole suite, one process) ===${NC}"
        run_uv pytest tests/ --tb=short
        echo ""
        echo -e "${BOLD}=== Outputgen ===${NC}"
        run_uv python -m tools.outputgen --check
        echo ""
        echo -e "${BOLD}=== Docs ===${NC}"
        bash "$PROJECT_ROOT/scripts/docs.sh" --check
    else
        step "Arch"
        run_uv pytest tests/unit/test_architecture_invariants.py -q --tb=line > /dev/null 2>&1 && ok || { fail; run_uv pytest tests/unit/test_architecture_invariants.py -v --tb=short; exit 1; }

        step "Lint"
        run_uv ty check src/ > /dev/null 2>&1 && run_uv ruff format --check src/ tests/ > /dev/null 2>&1 && ok || { fail; run_uv ty check src/; run_uv ruff format --check src/ tests/; exit 1; }

        step "Smoke"
        run_uv pytest tests/smoke/ -q --tb=line > /dev/null 2>&1 && ok || { fail; run_uv pytest tests/smoke/ -q --tb=short; exit 1; }

        step "Unit"
        run_uv pytest "${UNIT_ARGS[@]}" -q --tb=line > /dev/null 2>&1 && ok || { fail; run_uv pytest "${UNIT_ARGS[@]}" -q --tb=short; exit 1; }

        step "Property"
        run_uv pytest tests/property/ -q --tb=line > /dev/null 2>&1 && ok || { fail; run_uv pytest tests/property/ -q --tb=short; exit 1; }

        step "Appearance"
        run_uv pytest tests/appearance/ -q --tb=line > /dev/null 2>&1 && ok || { fail; run_uv pytest tests/appearance/ -q --tb=short; exit 1; }

        step "Integration"
        run_uv pytest tests/integration/ -q --tb=line > /dev/null 2>&1 && ok || { fail; run_uv pytest tests/integration/ -q --tb=short; exit 1; }

        step "Cohesion"
        run_uv pytest tests/ -q --tb=line > /dev/null 2>&1 && ok || { fail; run_uv pytest tests/ -q --tb=short; exit 1; }

        step "Outputgen"
        run_uv python -m tools.outputgen --check > /dev/null 2>&1 && ok || { fail; run_uv python -m tools.outputgen --check; exit 1; }

        step "Docs"
        bash "$PROJECT_ROOT/scripts/docs.sh" --check > /dev/null 2>&1 && ok || { fail; bash "$PROJECT_ROOT/scripts/docs.sh" --check; exit 1; }
    fi

    echo -e "\n${GREEN}All checks passed${NC}"
}

main "$@"
