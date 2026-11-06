# packages/shared

`openapi.json` is the generated OpenAPI 3 contract of the Axiom API (also served live at
`/api/openapi.json` and browsable at `/api/docs`). The web app's TypeScript types live in
`apps/web/src/lib/types.ts` and mirror this contract.

Regenerate after API changes:

```bash
cd apps/api && python -c "import json; from app.main import app; open('../../packages/shared/openapi.json','w').write(json.dumps(app.openapi(), indent=1))"
```
