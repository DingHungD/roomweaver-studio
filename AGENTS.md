# Repository working rules

- Read README.md first, then only relevant modules and tests.
- Keep runtime data in an explicit workspace. Never publish unrelated client data or credentials.
- Core Python is src/interior; the retained internal namespace is intentional. Do not restore dependencies on the original CAD platform.
- UI lives in frontend/src/features/visualization; render core in src/interior/visualization.
- Use synthetic fixtures. Keep sources immutable, preserve revision checks, job deduplication and provenance.
- Basic rendering must work without an Agent account; never silently enable cloud calls or switch paid providers.
- Run relevant checks and build. Report real Blender and live Agent tests separately from unit tests.
- Update setup documentation when commands or dependencies change. Do not commit workspace, artifacts, .venv or node_modules.
