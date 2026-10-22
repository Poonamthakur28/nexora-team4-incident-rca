import cors from 'cors';
import express from 'express';
import pinoHttp from 'pino-http';
import swaggerUi from 'swagger-ui-express';
import { env } from './config/env.js';
import { logger } from './config/logger.js';
import { errorHandler } from './middleware/error-handler.js';
import { notFound } from './middleware/not-found.js';
import { apiRouter } from './routes/api.routes.js';

const openApiDocument = {
  openapi: '3.0.3',
  info: {
    title: 'Nexora Team 4 Incident RCA API',
    version: '0.1.0',
    description: 'Team 4 incident investigation API foundation.',
  },
  servers: [{ url: '/api/v1' }],
  paths: {
    '/health': {
      get: { summary: 'API health', responses: { '200': { description: 'Service is healthy' } } },
    },
  },
};

export const app = express();
app.disable('x-powered-by');
app.use(cors({ origin: env.CORS_ORIGIN.split(',').map((origin) => origin.trim()) }));
app.use(express.json({ limit: '1mb' }));
app.use(pinoHttp({ logger }));
app.get('/health', (_req, res) =>
  res.json({
    status: 'ok',
    service: 'nexora-team4-incident-rca',
    timestamp: new Date().toISOString(),
  }),
);
app.use('/api/v1', apiRouter);
app.get('/openapi.json', (_req, res) => res.json(openApiDocument));
app.use('/docs', swaggerUi.serve, swaggerUi.setup(openApiDocument));
app.use(notFound);
app.use(errorHandler);
