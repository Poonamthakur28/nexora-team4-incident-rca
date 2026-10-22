import { app } from './app.js';
import { env } from './config/env.js';
import { logger } from './config/logger.js';

const server = app.listen(env.PORT, () => logger.info({ port: env.PORT }, 'Team 4 API listening'));

function shutdown(signal: string) {
  logger.info({ signal }, 'Shutting down API');
  server.close((error) => { if (error) { logger.error({ err: error }, 'Server shutdown failed'); process.exitCode = 1; } });
}

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
