.PHONY: test eval demo run build clean

test:
	pytest tests -v

eval:
	python -m reclaim.eval.report --sample-size 30 --seed 42

demo:
	python scripts/demo_seed.py
	python scripts/demo_razorpay_live.py --scenario insufficient_funds --capture
	python -m reclaim.eval.report --sample-size 30 --seed 42

run:
	python main.py

build:
	docker compose build
