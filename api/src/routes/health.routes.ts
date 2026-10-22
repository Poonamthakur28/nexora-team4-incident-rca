import { Router } from 'express';
import { z } from 'zod';

export const healthRouter = Router();
const healthQuerySchema = z.object({}).strict();

healthRouter.get('/', (req, res) => {
  healthQuerySchema.parse(req.query);
  res.json({ status: 'ok', service: 'nexora-team4-incident-rca', timestamp: new Date().toISOString() });
});
