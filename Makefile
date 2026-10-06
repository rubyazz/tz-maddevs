.PHONY: up down rebuild logs ps test seed-history clean

up:            ## build & start the whole stack
	docker compose up -d --build

down:          ## stop the stack (data volume kept)
	docker compose down

rebuild:       ## force rebuild images and restart
	docker compose up -d --build --force-recreate

logs:
	docker compose logs -f --tail=100

ps:
	docker compose ps

test:          ## run the backend test suite (unit + db) in containers
	docker compose --profile test build test
	docker compose --profile test run --rm test

seed-history:  ## insert synthetic history (perf proof for month queries)
	docker compose exec api python scripts/seed_history.py --days 30

clean:         ## stop everything and drop the data volume
	docker compose --profile test down -v
