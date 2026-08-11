#!/usr/bin/env bash
# CFD Trading System - instala los timers paper-trade como servicios de usuario systemd.
# Requiere: systemd de usuario (systemctl --user). Opcional: enable-linger para correr sin login.
set -euo pipefail

TARGET="$HOME/.config/systemd/user"
SRC="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$TARGET"

for unit in cfd-paper-1m.service cfd-paper-1m.timer \
            cfd-paper-1h.service cfd-paper-1h.timer \
            cfd-paper-1d.service cfd-paper-1d.timer; do
    cp "$SRC/$unit" "$TARGET/$unit"
    echo "instalado: $TARGET/$unit"
done

systemctl --user daemon-reload
systemctl --user enable cfd-paper-1m.timer cfd-paper-1h.timer cfd-paper-1d.timer
systemctl --user start  cfd-paper-1m.timer cfd-paper-1h.timer cfd-paper-1d.timer

echo
echo "Timers activos:"
systemctl --user list-timers 'cfd-paper-*'
echo
echo "Para que corran sin sesión gráfica (login): loginctl enable-linger alainolea"
echo "Ver logs de una corrida: journalctl --user -u cfd-paper-1m"