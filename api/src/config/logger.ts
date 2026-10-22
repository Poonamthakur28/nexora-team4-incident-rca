import pino from 'pino';
import { env } from './env.js';

export const logger = pino({ level: env.LOG_LEVEL, base: { service: 'nexora-team4-incident-rca' }, timestamp: pino.stdTimeFunctions.isoTime });
