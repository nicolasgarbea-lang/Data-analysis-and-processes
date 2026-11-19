# D All tests and what they check

<div class="inshort" markdown="1">

{{n:n_test_files}} test files with {{n:n_test_funcs}} test functions; pytest collects {{n:n_tests}} tests because some are parametrised. Run them with
`.venv/bin/python -m pytest`. Most tests read the processed files and model outputs, so run the pipeline once on a fresh
clone. The list below is generated from the test files (docstring, or the readable test name if there is none).

</div>

{{t:tests_summary|Test files. "Collected" counts each parameter case separately (from `pytest --collect-only`).}}

## Every test

{{t:tests_full}}
