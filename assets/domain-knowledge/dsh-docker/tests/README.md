# DSH Docker domain tests

From the knowledge-base root, run the registered validation command:

```sh
UV_CACHE_DIR=.uv-cache uv run --with pytest==9.1.1 pytest assets/domain-knowledge/dsh-docker/tests -q
```

The suite checks the catalog-to-manifest registration, required domain manifest mappings, documented resources, and the project checkout identity. The passing criterion is all tests green with exit code zero.
