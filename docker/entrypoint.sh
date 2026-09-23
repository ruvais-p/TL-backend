#!/bin/sh
set -eu

is_enabled() {
    case "${1:-}" in
        1|true|TRUE|yes|YES|on|ON) return 0 ;;
        *) return 1 ;;
    esac
}

if is_enabled "${RUN_MIGRATIONS:-false}"; then
    python manage.py migrate --noinput
fi

if is_enabled "${RUN_SETUP_GROUPS:-false}"; then
    python manage.py setup_groups
fi

exec "$@"
