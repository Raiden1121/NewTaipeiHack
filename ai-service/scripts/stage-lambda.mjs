// Stages what the AI Service Lambda zip needs besides the esbuild bundle.
// Terraform runs this right after esbuild (infrastructure/modules/ai_service/main.tf)
// with ai-service/ as the working directory.
//
// Precomputed explain / policyCopilot results live in .precomputed/ (gitignored,
// produced by `npm run precompute`). They are copied rather than bundled because
// FilePrecomputedStore reads one JSON file per fingerprint at request time
// (AI_PRECOMPUTE_DIR=/var/task/precomputed).
import { cpSync, existsSync, mkdirSync, readdirSync, rmSync } from 'node:fs';

const source = '.precomputed';
const target = 'dist-lambda/precomputed';

// Start clean so results from an older snapshot never ride along.
rmSync(target, { recursive: true, force: true });
mkdirSync(target, { recursive: true });

const files = existsSync(source)
  ? readdirSync(source).filter((name) => name.endsWith('.json'))
  : [];
for (const name of files) {
  cpSync(`${source}/${name}`, `${target}/${name}`);
}

if (files.length === 0) {
  console.warn(
    '[stage-lambda] ai-service/.precomputed/ has no results: explain / policyCopilot will ' +
      'recompute live (50-58s per request). See ai-service/DEPLOYMENT.md for how to generate them.',
  );
} else {
  console.log(`[stage-lambda] staged ${files.length} precomputed results`);
}
