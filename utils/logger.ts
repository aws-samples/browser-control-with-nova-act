/**
 * Frontend logging utility with structured logging support
 */

export enum LogLevel {
  DEBUG = 0,
  INFO = 1,
  WARN = 2,
  ERROR = 3,
}

interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
  context?: Record<string, any>;
  error?: Error;
}

class Logger {
  private logLevel: LogLevel;
  private isDevelopment: boolean;

  constructor(logLevel: LogLevel = LogLevel.INFO) {
    this.logLevel = logLevel;
    this.isDevelopment = process.env.NODE_ENV === 'development';
  }

  private shouldLog(level: LogLevel): boolean {
    return level >= this.logLevel;
  }

  private formatLogEntry(level: LogLevel, message: string, context?: Record<string, any>, error?: Error): LogEntry {
    return {
      timestamp: new Date().toISOString(),
      level: LogLevel[level],
      message,
      context,
      error,
    };
  }

  private writeLog(logEntry: LogEntry): void {
    if (!this.isDevelopment) {
      // In production, you could send logs to external service
      // For now, we'll still use console but with structured format
    }

    const { timestamp, level, message, context, error } = logEntry;
    const logMessage = `[${timestamp}] ${level}: ${message}`;

    switch (level) {
      case 'DEBUG':
        if (this.isDevelopment) {
          console.debug(logMessage, context || '', error || '');
        }
        break;
      case 'INFO':
        console.info(logMessage, context || '');
        break;
      case 'WARN':
        console.warn(logMessage, context || '');
        break;
      case 'ERROR':
        console.error(logMessage, context || '', error || '');
        break;
    }
  }

  debug(message: string, context?: Record<string, any>): void {
    if (this.shouldLog(LogLevel.DEBUG)) {
      const logEntry = this.formatLogEntry(LogLevel.DEBUG, message, context);
      this.writeLog(logEntry);
    }
  }

  info(message: string, context?: Record<string, any>): void {
    if (this.shouldLog(LogLevel.INFO)) {
      const logEntry = this.formatLogEntry(LogLevel.INFO, message, context);
      this.writeLog(logEntry);
    }
  }

  warn(message: string, context?: Record<string, any>): void {
    if (this.shouldLog(LogLevel.WARN)) {
      const logEntry = this.formatLogEntry(LogLevel.WARN, message, context);
      this.writeLog(logEntry);
    }
  }

  error(message: string, context?: Record<string, any>, error?: Error): void {
    if (this.shouldLog(LogLevel.ERROR)) {
      const logEntry = this.formatLogEntry(LogLevel.ERROR, message, context, error);
      this.writeLog(logEntry);
    }
  }

  setLogLevel(level: LogLevel): void {
    this.logLevel = level;
  }
}

// Create default logger instance
export const logger = new Logger(
  process.env.NODE_ENV === 'development' ? LogLevel.DEBUG : LogLevel.INFO
);

// Create context-aware loggers for different modules
export const createLogger = (module: string) => {
  return {
    debug: (message: string, context?: Record<string, any>) => 
      logger.debug(`[${module}] ${message}`, context),
    info: (message: string, context?: Record<string, any>) => 
      logger.info(`[${module}] ${message}`, context),
    warn: (message: string, context?: Record<string, any>) => 
      logger.warn(`[${module}] ${message}`, context),
    error: (message: string, context?: Record<string, any>, error?: Error) => 
      logger.error(`[${module}] ${message}`, context, error),
  };
};