.PHONY: setup test eval benchmark demo-reset judge-demo demo run build clean

setup:
	pip install -r requirements.txt

test:
	pytest tests -v

benchmark:
	python -m reclaim.eval.report --sample-size 1500 --seed 42 --force-heuristic

eval:
	python -m reclaim.eval.report --sample-size 1500 --seed 42 --force-heuristic

demo-reset:
	python scripts/reset_demo.py

judge-demo:
	python scripts/golden_demo.py

demo:
	python scripts/golden_demo.py

run:
	python -m uvicorn reclaim.main:app --reload

build:
	docker compose build


