#!/bin/bash
# Daily PostgreSQL backup for Vella
# Add to cron: 0 3 * * * /root/vella/backup.sh

BACKUP_DIR="/root/vella/backups"
MAX_BACKUPS=14  # keep 2 weeks

mkdir -p "$BACKUP_DIR"

FILENAME="vella_$(date +%Y%m%d_%H%M%S).sql.gz"

docker compose -f /root/vella/docker-compose.yml exec -T db \
  pg_dump -U vella vella | gzip > "$BACKUP_DIR/$FILENAME"

if [ $? -eq 0 ]; then
  echo "[Backup] OK: $FILENAME ($(du -h "$BACKUP_DIR/$FILENAME" | cut -f1))"
else
  echo "[Backup] FAILED"
  exit 1
fi

# Remove old backups
ls -t "$BACKUP_DIR"/vella_*.sql.gz | tail -n +$((MAX_BACKUPS + 1)) | xargs -r rm
