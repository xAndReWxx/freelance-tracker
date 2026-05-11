import os
import sys
import logging
from logging.handlers import RotatingFileHandler
import psutil
import time
import datetime
import threading
import re
import platform
import traceback

RUN_ID = datetime.datetime.now().strftime("RUN_%Y-%m-%d_%H-%M-%S")

LOG_FORMAT = "%(log_color)s%(asctime)s [%(run_id)s] [%(levelname)s] [%(name)s] %(message)s"
FILE_FORMAT = "%(asctime)s [%(run_id)s] [%(levelname)s] [%(name)s] [%(threadName)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LOG_DIR = os.path.join(APP_DIR, "logs")
try:
    os.makedirs(LOG_DIR, exist_ok=True)
except Exception:
    pass

SENSITIVE_PATTERNS = [
    (re.compile(r'(?i)(token|key|password|secret|auth|bearer|api_key)[\s:=]+[\'"]?([a-zA-Z0-9_\-\.:]+)[\'"]?'), r'\1=***REDACTED***'),
    (re.compile(r'mongodb(\+srv)?://([^:]+):([^@]+)@'), r'mongodb\1://\2:***REDACTED***@'),
    (re.compile(r'postgres(ql)?://([^:]+):([^@]+)@'), r'postgres\1://\2:***REDACTED***@')
]

class SanitizedFormatter(logging.Formatter):
    def format(self, record):
        if not hasattr(record, 'run_id'):
            record.run_id = RUN_ID
        original = super().format(record)
        for pattern, replacement in SENSITIVE_PATTERNS:
            original = pattern.sub(replacement, original)
        return original

try:
    import colorlog
    class SanitizedColorFormatter(colorlog.ColoredFormatter):
        def format(self, record):
            if not hasattr(record, 'run_id'):
                record.run_id = RUN_ID
            original = super().format(record)
            for pattern, replacement in SENSITIVE_PATTERNS:
                original = pattern.sub(replacement, original)
            return original
except ImportError:
    pass

_loggers = {}

def get_logger(name: str, file_name: str = "system.log", level: int = None) -> logging.Logger:
    """Get a centralized structured logger with sanitization, colors, and rotation."""
    if name in _loggers:
        return _loggers[name]

    if level is None:
        level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_str, logging.INFO)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False
    
    if logger.handlers:
        return logger

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    if 'colorlog' in sys.modules:
        console_handler.setFormatter(SanitizedColorFormatter(
            LOG_FORMAT,
            datefmt=DATE_FORMAT,
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        ))
    else:
        console_handler.setFormatter(SanitizedFormatter(FILE_FORMAT, datefmt=DATE_FORMAT))
    logger.addHandler(console_handler)

    # File Handler
    if file_name:
        log_path = os.path.join(LOG_DIR, file_name)
        try:
            file_handler = RotatingFileHandler(log_path, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
            file_handler.setFormatter(SanitizedFormatter(FILE_FORMAT, datefmt=DATE_FORMAT))
            logger.addHandler(file_handler)
        except Exception:
            pass

    # Global Error Log
    try:
        error_path = os.path.join(LOG_DIR, "errors.log")
        error_handler = RotatingFileHandler(error_path, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(SanitizedFormatter(FILE_FORMAT + " - %(pathname)s:%(lineno)d", datefmt=DATE_FORMAT))
        logger.addHandler(error_handler)
    except Exception:
        pass

    _loggers[name] = logger
    return logger

class PerformanceMonitor:
    def __init__(self):
        self.logger = get_logger("Performance", "performance.log")
        self.start_time = time.time()
        self.requests = 0
        self.detections = 0
        self.errors = 0
        
    def add_request(self):
        self.requests += 1
        
    def add_detection(self):
        self.detections += 1
        
    def add_error(self):
        self.errors += 1

    def log_metrics(self):
        uptime = time.time() - self.start_time
        rps = self.requests / max(uptime, 1)
        dpm = (self.detections / max(uptime, 1)) * 60
        
        try:
            mem = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
            cpu = psutil.Process(os.getpid()).cpu_percent(interval=None)
            self.logger.info(f"[PERF] RPS={rps:.2f} | Detections={dpm:.2f}/min | Errors={self.errors} | RAM={mem:.1f}MB | CPU={cpu}% | Uptime={uptime:.0f}s")
        except Exception:
            pass

perf_monitor = PerformanceMonitor()

class LatencyTracker:
    def __init__(self, project_id, stage, logger):
        self.project_id = project_id
        self.stage = stage
        self.logger = logger
        self.start = 0

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        latency = time.time() - self.start
        if exc_type:
            self.logger.error(f"[TRACE] ProjectID={self.project_id} | Stage={self.stage} | Status=FAILED | Latency={latency:.3f}s | Error={exc_val}")
        else:
            self.logger.debug(f"[TRACE] ProjectID={self.project_id} | Stage={self.stage} | Status=SUCCESS | Latency={latency:.3f}s")

def generate_crash_dump(exc_type, exc_value, exc_traceback, context_msg=""):
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dump_path = os.path.join(LOG_DIR, f"crash_report_{timestamp}.txt")
        
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        
        mem = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
        cpu = psutil.Process(os.getpid()).cpu_percent(interval=None)
        sys_info = platform.platform()
        py_ver = sys.version
        
        dump = f"""CRASH REPORT
━━━━━━━━━━━━━━
RUN_ID: {RUN_ID}
Timestamp: {datetime.datetime.now()}
Context: {context_msg}

Exception:
{exc_type.__name__}: {exc_value}

Traceback:
{tb_str}

Memory Usage:
{mem:.1f}MB

CPU Usage:
{cpu}%

Platform:
{sys_info}
Python {py_ver}
"""
        for pattern, replacement in SENSITIVE_PATTERNS:
            dump = pattern.sub(replacement, dump)
            
        with open(dump_path, 'w', encoding='utf-8') as f:
            f.write(dump)
            
        get_logger("System").critical(f"FATAL CRASH! Dump saved to {dump_path}")
    except Exception as e:
        print(f"Failed to generate crash dump: {e}")

def _global_excepthook(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    generate_crash_dump(exc_type, exc_value, exc_traceback, "Uncaught Exception")

sys.excepthook = _global_excepthook

def _thread_excepthook(args):
    generate_crash_dump(args.exc_type, args.exc_value, args.exc_traceback, f"Thread Crash: {args.thread.name if args.thread else 'Unknown'}")

threading.excepthook = _thread_excepthook

def setup_async_crash_handler(loop):
    def async_exception_handler(loop, context):
        msg = context.get("message")
        exception = context.get("exception")
        
        if exception:
            exc_type = type(exception)
            exc_value = exception
            exc_tb = exception.__traceback__
            generate_crash_dump(exc_type, exc_value, exc_tb, f"Async Task Crash: {msg}")
        else:
            get_logger("AsyncIO").error(f"AsyncIO Loop Error: {msg}")
            
    loop.set_exception_handler(async_exception_handler)
