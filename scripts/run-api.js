// Runs a Python command inside api/ using the API virtual environment when it exists.
// Usage: node scripts/run-api.js <python args...>   e.g. node scripts/run-api.js -m pytest
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const apiDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'api');
const isWindows = process.platform === 'win32';
const venvPython = path.join(apiDir, '.venv', isWindows ? 'Scripts/python.exe' : 'bin/python');
const activeVenvPython = process.env.VIRTUAL_ENV
  ? path.join(process.env.VIRTUAL_ENV, isWindows ? 'Scripts/python.exe' : 'bin/python')
  : undefined;

const python = [venvPython, activeVenvPython].find((candidate) => candidate && existsSync(candidate));
if (!python) {
  const setup = isWindows
    ? '  cd api; py -3.11 -m venv .venv; .venv\\Scripts\\python -m pip install -r requirements-dev.txt'
    : '  cd api && python3 -m venv .venv && .venv/bin/python -m pip install -r requirements-dev.txt';
  console.error(
    `No Python virtual environment found at ${path.join(apiDir, '.venv')}.\n` +
      `Create it first (see README "Backend setup"):\n${setup}`,
  );
  process.exit(1);
}

const result = spawnSync(python, process.argv.slice(2), { cwd: apiDir, stdio: 'inherit' });
if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}
process.exit(result.status ?? 1);
