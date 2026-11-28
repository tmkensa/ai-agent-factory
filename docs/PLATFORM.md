# AI Agent Factory v0.3 platform preview

[العربية](PLATFORM.ar.md) · [Architecture v0.2](ARCHITECTURE.md)

This additive CLI extends the review-branch architecture. Requires Python 3.10+. Existing commands remain supported. The platform is local-first and has **no production-autonomy claim**. All external actions are opt-in commands, not model-issued tool calls.

## Run and provider routing

```sh
python -m factory.platform --project demo run examples/architecture.en.json
python -m factory.platform --project work --route ollama/YOUR_MODEL run examples/architecture.en.json
python -m factory.platform --project work --route ollama/YOUR_MODEL resume RUN_ID
python -m factory.platform --project work --route ollama/YOUR_MODEL --role-route security=ollama/YOUR_OTHER_MODEL run examples/architecture.en.json
```

Resume with the exact model route configuration used for the run. Use a model actually installed in Ollama. The demo is a deterministic fixture, not AI. For cloud models use an actual supported model ID and set the provider key **outside chat** in the environment (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`). Never commit keys. For example:

```sh
python -m factory.platform --route openai/YOUR_MODEL --allow-cloud run examples/architecture.en.json --calls 8
python -m factory.platform --route anthropic/YOUR_MODEL --allow-cloud run examples/architecture.en.json --calls 8
python -m factory.platform --route gemini/YOUR_MODEL --allow-cloud run examples/architecture.en.json --calls 8
```

`--allow-cloud` explicitly permits sending task/evidence to the named provider and potentially billable requests for that invocation. No automatic fallback or retry. The output token limit is 2048 by default and run calls are capped (30 maximum); these are not a hard monetary spending cap. Set provider-side budgets separately. Models must support the request and JSON response modes used. Cloud adapters use fixed TLS endpoints; no automatic package/model installation. Output validation does not prove facts or security.

## Custom agents and skills

```sh
python -m factory.platform --route ollama/YOUR_MODEL run examples/architecture.en.json --specialists examples/specialists.json --calls 24
```

Define up to five operator-approved specialist roles, unique names/jobs and dependencies in a JSON array. Independent specialists run in parallel; generated findings are marked unverified and passed to the original workflow as source data. The specialist phase consumes the same call budget but is not resumable until the main checkpoint has been created. For one independent role (`depends_on: []`), `python -m factory.platform skill role.json` prints a reusable skill. No arbitrary execution privileges are assigned to specialists.

## Read-only evidence and MCP

```sh
python -m factory.platform web https://example.org/ --host example.org --approve > web.json
python -m factory.platform mcp --port 8765 --tool read_document --args args.json --approve > mcp.json
python -m factory.platform run examples/architecture.en.json --source web.json --source mcp.json
```

Use a trusted local MCP server exposing `/mcp`, protocol 2026-07-28, JSON responses, non-paginated tools, no custom parameter headers or interaction extensions. `args.json` is an object. Only the exact requested tool with `readOnlyHint: true` is admitted; the server annotation is a hint, not a security boundary. The operator must independently trust the server and tool. No arbitrary remote MCP server, OAuth, SSE, autonomous tool discovery/calling, or browser automation. HTTPS evidence uses an exact host, public IP pinning, no redirects, no queries/credentials, and bounded plain-text extraction. It does not provide a search engine; users supply public URLs. Never use sensitive inputs.

## Governed code staging and Docker tests

```sh
python -m factory.platform digest examples/stage-plan.json
python -m factory.platform stage examples/stage-plan.json new-workspace --digest EXACT_DIGEST
python -m factory.platform sandbox-test new-workspace --image YOUR_INSTALLED_IMAGE_AT_SHA256_DIGEST --approve
```

Review the complete file plan before approval. Only a new directory is created; existing files are not edited. File types, counts, sizes and known secret patterns are checked. Docker is optional and must already be installed. The operator must supply an already installed, trusted Linux image pinned by digest, with Python available for the default unittest suite. `--suite php-lint` uses `php -l` with PHP 8.3+ for PHP files (not full Laravel testing). A sanitized snapshot is mounted read-only with networking disabled, non-root user, dropped capabilities and resource limits. Docker daemon/image trust and host security remain essential; this is not a guarantee against container escapes. No package install, arbitrary shell, production deployment or Docker image pulls. Review generated code and run only in a disposable environment.

## Local memory, metrics and dashboard

```sh
python -m factory.platform --project work remember notes.txt
python -m factory.platform --project work recall "backup"
python -m factory.platform --project work remember notes.txt --embedding-model YOUR_LOCAL_EMBEDDING_MODEL
python -m factory.platform --project work recall "backup" --embedding-model YOUR_LOCAL_EMBEDDING_MODEL
python -m factory.platform --project work run examples/architecture.en.json --memory-query backup
python -m factory.platform --project work compare RUN_A RUN_B
python -m factory.platform --project work dashboard dashboard.html
```

SQLite notes and job definitions are project-scoped. Lexical lookup and optional local cosine similarity are available. A task may explicitly retrieve notes, labeled unverified. Use the same embedding model when searching. No secret storage, encryption, shared-memory service or automatic learning. `compare` requires identical task contracts and reports actual call counts and role-time sums, not model truth or financial cost. Dashboard is a read-only offline HTML snapshot; open the generated file in a browser. No server or authentication system is started.

## Scheduling

```sh
python -m factory.platform --project weekly --route ollama/YOUR_MODEL schedule examples/architecture.en.json --interval 604800 --approve
python -m factory.platform --project weekly jobs
python -m factory.platform --project weekly tick
python -m factory.platform --project weekly cancel JOB_ID
```

Schedule is stored in SQLite, not automatically registered with an operating-system timer. Use a user-configured cron/Task Scheduler to call `tick` periodically if desired. Recurring cloud calls are disabled. Jobs claim their run atomically and never auto-retry failed or interrupted jobs. A running job after a crash needs operator inspection; no duplicate external effects are automatically retried. Keep storage private and use trusted checkpoints. The dashboard shows only summaries.

## Verification boundaries

- HTTP contracts use official provider specifications: [OpenAI](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create), [Anthropic](https://platform.claude.com/docs/en/api/messages/create), [Gemini](https://ai.google.dev/api/generate-content), [Ollama embeddings](https://docs.ollama.com/api/embed), [MCP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http), [Docker](https://docs.docker.com/reference/cli/docker/container/run/).
- Unit tests use fixtures/mocks for provider APIs, MCP, web and Docker. No live inference, actual Docker execution, live MCP server or public web fetch was performed in the local build environment. No external actions or keys required to run unit tests.
- Hosted CI was blocked by the account's billing error. Do not mark the branch production-ready until live integration and independent security review succeed.
