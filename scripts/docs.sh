#!/usr/bin/env bash
# DESC: Assemble docs from fragments (docgen) + manage README<->CLAUDE.md symlinks
# Usage: ./dev docs [--link | --check]
#
# One canonical source per fact: authored prose lives in docs/_fragments/*.md and is
# injected into every surface via `frag:` docgen markers. Consumer guides keep ONE body
# under two discovery names: README.md (the real file) + CLAUDE.md (a symlink to it).
#
#   ./dev docs          assemble fragment bodies into the managed surfaces (docgen --update)
#   ./dev docs --link   create/repair the README -> CLAUDE.md symlinks for consumer guides
#   ./dev docs --check  GATE: bodies not drifted AND consumer-guide symlinks correct
#
# Scope is intentionally the docs-system MANAGED surfaces only. The legacy guide/slide
# docgen markers reference stale modules (see docs/dev/plans/2026-06-01-docs-system-design.md
# §5) and are repaired in Phase 1 before a full-tree check is gated.
source "$(dirname "$0")/lib/dev.sh"

# Markdown roots scanned for frag:/docgen markers.
DOCS_ROOTS=(src)
# Dedicated snippet store, kept separate from the orphaned docs/.extract/snippets.v1.json.
DOCS_STORE="docs/.extract/docs-system.v1.json"
# Consumer guides: README.md is the real body; CLAUDE.md is a symlink to it.
CONSUMER_GUIDES=(src/painted src/painted/views src/painted/tui)

_docgen() {
    run_uv python -m tools.docgen "$@" --roots "${DOCS_ROOTS[@]}" --snippets-out "$DOCS_STORE"
}

link_guides() {
    local made=0
    for dir in "${CONSUMER_GUIDES[@]}"; do
        local readme="$PROJECT_ROOT/$dir/README.md"
        local claude="$PROJECT_ROOT/$dir/CLAUDE.md"
        [ -f "$readme" ] || continue   # not collapsed yet — skip
        if [ -L "$claude" ]; then
            [ "$(readlink "$claude")" = "README.md" ] && continue
            echo "  fix:  $dir/CLAUDE.md -> README.md"
            rm "$claude"; ln -s README.md "$claude"; made=1
        elif [ -e "$claude" ]; then
            echo "  ERROR: $dir/CLAUDE.md is a real file, not a symlink (refusing to clobber)"
            return 1
        else
            echo "  link: $dir/CLAUDE.md -> README.md"
            ln -s README.md "$claude"; made=1
        fi
    done
    [ $made -eq 0 ] && echo "  symlinks already correct"
    return 0
}

check_links() {
    local bad=0
    for dir in "${CONSUMER_GUIDES[@]}"; do
        local readme="$PROJECT_ROOT/$dir/README.md"
        local claude="$PROJECT_ROOT/$dir/CLAUDE.md"
        [ -f "$readme" ] || continue
        if [ ! -L "$claude" ] || [ "$(readlink "$claude")" != "README.md" ]; then
            echo "  MISSING/WRONG symlink: $dir/CLAUDE.md -> README.md"
            bad=1
        fi
    done
    return $bad
}

main() {
    cd "$PROJECT_ROOT"
    case "${1:-}" in
        --link)
            step "Link"; echo; link_guides && ok || { fail; exit 1; }
            ;;
        --check)
            step "Bodies"; _docgen --check > /dev/null 2>&1 && ok || { fail; _docgen --check; exit 1; }
            step "Symlinks"; check_links > /dev/null 2>&1 && ok || { fail; check_links; exit 1; }
            ;;
        "")
            step "Assemble"; _docgen --update > /dev/null 2>&1 && ok || { fail; _docgen --update; exit 1; }
            ;;
        --help|-h)
            echo "Usage: ./dev docs [--link | --check]"; exit 0
            ;;
        *)
            echo "Unknown option: $1"; echo "Usage: ./dev docs [--link | --check]"; exit 1
            ;;
    esac
}

main "$@"
