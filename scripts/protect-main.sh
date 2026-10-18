#!/bin/sh
# Включает защиту main. Запускать владельцу репозитория: gh auth login && sh scripts/protect-main.sh
# Включает: PR + 1 approve + зелёный CI (backend, frontend), запрет force-push и удаления.
set -e
REPO="${1:-GoGlode/GoGlobe}"
gh api "repos/$REPO/branches/main/protection" -X PUT --input - <<'JSON'
{"required_status_checks":{"strict":false,"contexts":["backend","frontend"]},
 "enforce_admins":false,
 "required_pull_request_reviews":{"required_approving_review_count":1},
 "restrictions":null,"allow_force_pushes":false,"allow_deletions":false}
JSON
echo "Защита main включена для $REPO"
