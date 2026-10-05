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

test:          ## run backend tests against the db-test service
	docker compose --profile test up -d db-test
	docker compose run --rm --no-deps \
		-e DATABASE_URL=postgresql+asyncpg://pulse:pulse@db-test:5432/pulse_test \
		-e TEST_DATABASE_URL=postgresql+asyncpg://pulse:pulse@db-test:5432/pulse_test \
		api pytest -q
	docker compose --profile test down db-test

seed-history:  ## insert synthetic history (perf proof for month queries)
	docker compose exec api python scripts/seed_history.py --days 30

clean:         ## stop everything and drop the data volume
	docker compose down -v
