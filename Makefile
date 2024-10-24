mrproper:
	@rm -rf build dist spicepy.egg-info spicepy/__pycache__

.PHONY: test
test:
	pip install pytest
	pytest -s

.PHONY: apple-silicon-requirements
apple-silicon-requirements:
	conda install pyarrow=12 pandas

.PHONY: lint
lint:
	pip install pylint flake8
	pylint spicepy tests
	flake8 spicepy tests