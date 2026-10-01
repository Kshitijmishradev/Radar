.PHONY: run worker test container-up container-down

run:
	.venv/bin/uvicorn app.main:app --reload

worker:
	.venv/bin/python -m app.worker

test:
	.venv/bin/python -m unittest discover -s tests -v

container-up:
	docker compose up --build

container-down:
	docker compose down
