import type { Response } from 'express';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { errorHandler } from '../../src/middleware/error-handler.js';

function invoke(error: unknown) {
  let statusCode = 0;
  let body: unknown;
  const res = {
    status(code: number) {
      statusCode = code;
      return res;
    },
    json(payload: unknown) {
      body = payload;
      return res;
    },
  } as unknown as Response;
  errorHandler(error, {} as never, res, (() => undefined) as never);
  return { statusCode, body };
}

describe('error handler', () => {
  it('returns HTTP 400 for invalid client input without a stack', () => {
    const parsed = z.object({}).strict().safeParse({ extra: true });
    expect(parsed.success).toBe(false);
    if (parsed.success) return;
    const { statusCode, body } = invoke(parsed.error);
    expect(statusCode).toBe(400);
    expect(body).toMatchObject({ error: { code: 'INVALID_REQUEST' } });
    expect(JSON.stringify(body)).not.toContain('stack');
  });

  it('returns HTTP 500 for unexpected failures without the internal message', () => {
    const { statusCode, body } = invoke(new Error('database credential detail'));
    expect(statusCode).toBe(500);
    expect(body).toEqual({
      error: { code: 'INTERNAL_SERVER_ERROR', message: 'An unexpected error occurred.' },
    });
    expect(JSON.stringify(body)).not.toContain('database credential detail');
    expect(JSON.stringify(body)).not.toContain('stack');
  });
});
