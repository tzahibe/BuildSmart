import os
os.environ["TEST_MODE"] = "REGRESSION"
import pytest
raise SystemExit(pytest.main(["-q", "tests/regression_corpus/test_frozen_regression_corpus.py"]))
