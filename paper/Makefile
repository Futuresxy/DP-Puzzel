PYTHON ?= python3
.PHONY: all pdf watch reproduce diagrams cost-figures check test clean
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

# Editable area/power data; PNG figures only.
cost-figures:
	$(PYTHON) data/DP_area_power/plot_area_power.py
	$(PYTHON) data/H16Q32E64_area/plot_area.py

# Optional terminal watcher; Ctrl-C stops it. The VS Code recipe already builds on save.
watch:
	latexmk -pvc -view=none -xelatex -interaction=nonstopmode -halt-on-error -file-line-error main.tex
