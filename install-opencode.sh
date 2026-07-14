#!/usr/bin/env bash
# Установка плагина OPP в OpenCode (https://opencode.ai).
#
# OpenCode понимает скиллы формата SKILL.md, но не знает переменную ${CLAUDE_PLUGIN_ROOT} —
# поэтому навыки не симлинкуются, а копируются с подстановкой абсолютного пути установки.
# Идемпотентно: повторный запуск обновляет репозиторий и перекладывает навыки заново.
#
# Использование:
#   curl -fsSL https://raw.githubusercontent.com/dggalimov/opp-plugin/main/install-opencode.sh | bash
set -euo pipefail

REPO_URL="https://github.com/dggalimov/opp-plugin.git"
INSTALL_DIR="${OPP_INSTALL_DIR:-$HOME/.local/share/opp-plugin}"
OC_DIR="${OPENCODE_CONFIG_DIR:-$HOME/.config/opencode}"
PLUGIN_ROOT="$INSTALL_DIR/plugins/opp"

command -v git >/dev/null || { echo "Нужен git"; exit 1; }
command -v python3 >/dev/null || { echo "Нужен python3 (единственное обязательное требование OPP)"; exit 1; }

echo "OPP → OpenCode: установка в $OC_DIR"

# 1. Репозиторий плагина: клон или обновление.
if [ -d "$INSTALL_DIR/.git" ]; then
    git -C "$INSTALL_DIR" pull --ff-only -q
    echo "  репозиторий обновлён: $INSTALL_DIR"
else
    git clone -q "$REPO_URL" "$INSTALL_DIR"
    echo "  репозиторий склонирован: $INSTALL_DIR"
fi

# 2. Навыки: копия с подстановкой пути вместо ${CLAUDE_PLUGIN_ROOT}.
mkdir -p "$OC_DIR/skills" "$OC_DIR/commands"
INSTALLED=""
for src in "$PLUGIN_ROOT"/skills/*/; do
    name="$(basename "$src")"
    dest="$OC_DIR/skills/$name"
    rm -rf "$dest"
    cp -R "$src" "$dest"
    PLUGIN_ROOT="$PLUGIN_ROOT" DEST="$dest" python3 - <<'PY'
import os
from pathlib import Path
root, dest = os.environ["PLUGIN_ROOT"], Path(os.environ["DEST"])
for p in dest.rglob("*"):
    if p.is_file() and p.suffix in (".md", ".yaml", ".yml", ".py", ".sh", ""):
        try:
            t = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue
        if "CLAUDE_PLUGIN_ROOT" in t:
            t = t.replace("${CLAUDE_PLUGIN_ROOT}", root)
            p.write_text(t, encoding="utf-8")
PY
    INSTALLED="$INSTALLED $name"
done
echo "  навыки:$INSTALLED"

# 3. Команды-обёртки /opp-<имя> для каждого навыка.
for src in "$PLUGIN_ROOT"/skills/*/; do
    name="$(basename "$src")"
    desc="$(python3 -c "
import re, sys
t = open('$src/SKILL.md', encoding='utf-8').read()
m = re.search(r'description:\s*>?-?\s*\n?((?:\s{2,}.*\n)+|.*\n)', t)
line = re.sub(r'\s+', ' ', m.group(1)).strip() if m else '$name'
line = re.sub(r'\"\\\$\{CLAUDE_PLUGIN_ROOT\}/opp\"', 'opp', line)      # команда — коротким именем
line = re.sub(r'\\\$\{CLAUDE_PLUGIN_ROOT\}/?', '', line)                # прочие техвставки — вон
print(line.split('. ')[0][:120])")"
    cat > "$OC_DIR/commands/opp-$name.md" <<EOF
---
description: $desc
---
Загрузи скил \`$name\` через инструмент skill и выполни его инструкции. Аргументы пользователя: \$ARGUMENTS
EOF
done
echo "  команды: $(ls "$OC_DIR/commands" | grep -c '^opp-') шт. (/opp-<имя>)"

echo "Готово. Первый запуск любой команды сам поднимет python-окружение OPP."
echo "Обновление: повторите эту же команду установки."
