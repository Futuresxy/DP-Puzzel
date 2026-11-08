PYTHON ?= python3
.PHONY: all pdf reproduce diagrams check test clean
all: pdf
pdf:
	latexmk -xelatex -interaction=nonstopmode -halt-on-error -file-line-error main.tex
reproduce:
	$(PYTHON) scripts/reproduce.py
diagrams:
	$(PYTHON) scripts/plot_tensor_dp_background.py
	$(PYTHON) scripts/plot_kn_composition.py
check: reproduce
	$(PYTHON) scripts/check_reference.py
test:
	$(PYTHON) scripts/test_parameters.py
clean:
	latexmk -c main.tex
