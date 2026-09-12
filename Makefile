# bemyself: die Testsuite, ein Beispiel-Report und das Pruefset.
PYTHON ?= python3

.PHONY: all check eval test

all: test check eval

test:
	$(PYTHON) -m unittest discover -s tests

check:
	$(PYTHON) -m bemyself check --report tests/data/beispiel-report.md --repo . --base 7c7392cf130e9da23c2ee3ec0602faec79b7266d

eval:
	$(PYTHON) -m bemyself eval --set tests/data/pruefset.json
