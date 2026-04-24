### algobooth Quality Gates

Determine which gates are relevant based on the files modified:
- TypeScript changes → `npm run qg -- ts`
- Rust changes → `npm run qg -- rust`
- Sidecar changes → `npm run qg -- sidecar`
- Mixed → `npm run qg` (all gates)
