.PHONY: run demo-api worker test demo container-up container-down

run:
	.venv/bin/uvicorn app.main:app --reload

worker:
	.venv/bin/python -m app.worker

test:
	.venv/bin/python -m unittest discover -s tests -v

demo:
	.venv/bin/python -m scripts.seed_demo

demo-api:
	RUN_LOCAL_WORKER=false .venv/bin/uvicorn app.main:app --reload

container-up:
	docker compose up --build

container-down:
	docker compose down
