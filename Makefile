IMAGE := redline-kit
PYPI_INDEX ?= https://pypi.org/simple

.PHONY: install fixtures test lint docker-build docker-test demo

install:
	uv sync

docker-build:
	docker build --build-arg PYPI_INDEX=$(PYPI_INDEX) -t $(IMAGE) .

fixtures: docker-build
	docker run --rm -v "$(PWD)/tests/fixtures:/app/tests/fixtures" $(IMAGE) python scripts/make_fixtures.py --pdf

test:
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check .

docker-test: docker-build
	docker run --rm $(IMAGE)

demo:
	mkdir -p out
	uv run redline apply tests/fixtures/contract.docx examples/edits.json -o out/out.docx
	uv run redline apply tests/fixtures/contract.pdf examples/edits.json -o out/out.pdf
	uv run redline mine out/out.docx -o out/playbook.json
