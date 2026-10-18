# Как работать в репозитории

См. раздел 5 в [README](README.md). Коротко:

1. `git fetch && git rebase origin/main` в своей ветке `dev/<роль>` каждое утро.
2. Маленький PR в `main` → смежный ревьюер → зелёный CI → merge (squash).
3. Контракт API меняет только PR с меткой `contract`, после согласования в чате.
4. Перед PR: `make lint test`.
5. Секреты — только в `.env`.
