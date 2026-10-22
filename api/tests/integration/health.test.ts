import { describe, expect, it } from 'vitest';
import { app } from '../../src/app.js';

describe('health API', () => {
  it('answers the unversioned health endpoint', async () => {
    const server = app.listen(0);
    try {
      const address = server.address();
      if (!address || typeof address === 'string') throw new Error('No TCP address');
      const response = await fetch(`http://127.0.0.1:${address.port}/health`);
      expect(response.status).toBe(200);
      expect((await response.json()).status).toBe('ok');
      const versioned = await fetch(`http://127.0.0.1:${address.port}/api/v1/health`);
      expect(versioned.status).toBe(200);
      const invalid = await fetch(`http://127.0.0.1:${address.port}/api/v1/health?extra=1`);
      expect(invalid.status).toBe(400);
      const invalidBody = await invalid.json();
      expect(invalidBody.error.code).toBe('INVALID_REQUEST');
      expect(JSON.stringify(invalidBody)).not.toContain('stack');
    } finally { await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve())); }
  });
});
