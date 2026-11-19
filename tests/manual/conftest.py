# Scripts in this directory are run by hand (`python -m tests.manual.<name>`
# from the repository root). Several need live credentials or call provider
# APIs at import time, so keep pytest from collecting them.
collect_ignore_glob = ["test_*.py"]
