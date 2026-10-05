.PHONY: run worker test demo container-up container-down

run:
	.venv/bin/uvicorn app.main:app --reload

worker:
	.venv/bin/python -m app.worker

test:
	.venv/bin/python -m unittest discover -s tests -v

demo:
	.venv/bin/python -m scripts.seed_demo

container-up:
	docker compose up --build

container-down:
	docker compose down
