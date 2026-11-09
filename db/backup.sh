#!/bin/sh
# Respaldo programado: formato custom (-Fc) para restaurar con pg_restore.
set -e
while true; do
  f="/backups/mediagenda_$(date +%Y%m%d_%H%M%S).dump"
  pg_dump -Fc -f "$f" && echo "Respaldo creado: $f"
  ls -1t /backups/*.dump 2>/dev/null | tail -n +8 | xargs -r rm -f
  sleep "${BACKUP_INTERVAL:-86400}"
done
