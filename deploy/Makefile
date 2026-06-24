# Allerion deploy convenience targets.
#
# Run these from inside deploy/ (where docker-compose.yml lives):
#
#   make up        # build + start the stack
#   make logs      # tail all logs   (make logs s=store  tails one service)
#   make pull      # git pull --ff-only, then rebuild + restart (the "update" flow)
#   make backup    # snapshot the SQLite volumes to timestamped tarballs
#
# Compose prefixes named volumes with the project name (the deploy/ dir),
# so store_data becomes deploy_store_data. Override with: make backup PROJECT=allerion
PROJECT ?= deploy

# Optional single-service selector for `logs` (e.g. make logs s=store)
s ?=

.PHONY: help up down restart logs ps pull backup

# Default target: list what's available.
help:
	@echo "Allerion deploy targets (run from deploy/):"
	@echo "  make up        - build and start the stack (docker compose up -d --build)"
	@echo "  make down      - stop the stack (data persists in named volumes)"
	@echo "  make restart   - down then up"
	@echo "  make logs      - tail all logs; 'make logs s=store' tails one service"
	@echo "  make ps        - show container status"
	@echo "  make pull      - git pull --ff-only then rebuild + restart (update flow)"
	@echo "  make backup    - tar store_data + platform_data to timestamped tarballs"
	@echo "  make help      - show this message (default)"
	@echo ""
	@echo "  PROJECT=$(PROJECT)  (compose volume prefix; override for backup if needed)"

up:
	docker compose up -d --build

down:
	docker compose down

restart: down up

# Tail logs. With s=<service> tail just that one (e.g. make logs s=store).
logs:
	docker compose logs -f $(s)

ps:
	docker compose ps

# Standard update: fast-forward the checkout, then rebuild + restart.
pull:
	git pull --ff-only && docker compose up -d --build

# Back up the SQLite named volumes to timestamped tarballs in the current dir,
# using a throwaway busybox container to read each volume. Volume names are
# compose-prefixed (PROJECT_<name>); override PROJECT if your project name differs.
backup:
	@ts=$$(date +%Y%m%d-%H%M%S); \
	echo "Backing up $(PROJECT)_store_data -> store_data-$$ts.tar.gz"; \
	docker run --rm -v $(PROJECT)_store_data:/data:ro -v "$$PWD":/backup busybox \
		tar czf /backup/store_data-$$ts.tar.gz -C /data .; \
	echo "Backing up $(PROJECT)_platform_data -> platform_data-$$ts.tar.gz"; \
	docker run --rm -v $(PROJECT)_platform_data:/data:ro -v "$$PWD":/backup busybox \
		tar czf /backup/platform_data-$$ts.tar.gz -C /data .; \
	echo "Done. Tarballs written to $$PWD"
