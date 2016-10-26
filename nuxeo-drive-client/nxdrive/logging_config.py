"""Utilities to log nxdrive operations and failures"""

import logging
import logging.handers
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler, BufferingHandler
import os
from copy import copy


TRACE = 5
logging.addLevelName(TRACE, 'TRACE')
logging.TRACE = TRACE
FILE_HANDLER = None

# Singleton logging context for each process.
# Alternatively we could use the setproctitle to handle the command name
# package and directly change the real process name but this requires to build
# a compiled extension under Windows...

_logging_context = dict()

is_logging_configured = False
MAX_LOG_DISPLAYED = 5000


class CustomMemoryHandler(BufferingHandler):
    def __init__(self, capacity=MAX_LOG_DISPLAYED):
        super(CustomMemoryHandler, self).__init__(capacity)
        self._old_buffer = None

    def flush(self):
        # Flush
        self.acquire()
        try:
            self._old_buffer = copy(self.buffer)
            self.buffer = []
        finally:
            self.release()

    def get_buffer(self, size):
        adds = []
        result = []
        self.acquire()
        try:
            result = copy(self.buffer)
            result.reverse()
            if len(result) < size and self._old_buffer is not None:
                adds = copy(self._old_buffer[(size-len(result)-1):])
        finally:
            self.release()
        adds.reverse()
        for record in adds:
            result.append(record)
        return result


def configure(use_file_handler=False, log_filename=None, file_level='INFO',
              console_level='INFO', filter_inotify=True, command_name=None, log_rotate_keep=30,
              log_rotate_max_bytes=None, log_rotate_when=None, force_configure=False):

    global is_logging_configured
    global FILE_HANDLER

    if not is_logging_configured or force_configure:
        is_logging_configured = True

        _logging_context['command'] = command_name

        if file_level is None:
            file_level = 'INFO'
        # convert string levels
        if hasattr(file_level, 'upper'):
            file_level = getattr(logging, file_level.upper())
        if hasattr(console_level, 'upper'):
            console_level = getattr(logging, console_level.upper())

        # find the minimum level to avoid filtering by the root logger itself:
        root_logger = logging.getLogger()
        sumo_logger = logging.getLogger("sumologger")
        min_level = min(file_level, console_level)
        root_logger.setLevel(min_level)

        # define the formatter
        formatter = logging.Formatter(
            "%(asctime)s %(process)d %(thread)d %(levelname)-8s %(name)-18s"
            " %(message)s"
        )

        # define a Handler which writes INFO messages or higher to the
        # sys.stderr
        console_handler_name = 'console'
        console_handler = get_handler(root_logger, console_handler_name)
        sumo_handler = get_handler(sumo_logger, 'sumo')

        if console_handler is None:
            console_handler = logging.StreamHandler()
            console_handler.set_name(console_handler_name)
            # tell the console handler to use this format
            console_handler.setFormatter(formatter)
        console_handler.setLevel(console_level)

        if sumo_handler is None:
            sumo_handler = logging.StreamHandler()
            sumo_handler.set_name(console_handler_name)
            # tell the sumo handler to use this format
            sumo_handler.setFormatter(formatter)
        sumo_handler.setLevel('sumo')

        # add the console handler to the root logger and all descendants
        root_logger.addHandler(console_handler)
        root_logger.addHandler(sumo_handler)

        # define a Handler for file based log with rotation if needed
        if use_file_handler and log_filename is not None:
            log_filename = os.path.expanduser(log_filename)
            log_folder = os.path.dirname(log_filename)
            if not os.path.exists(log_folder):
                os.makedirs(log_folder)
            if log_rotate_when is None and log_rotate_max_bytes is None:
                log_rotate_when = 'midnight'
            if log_rotate_when is not None:
                file_handler = TimedRotatingFileHandler(log_filename,
                                    when=log_rotate_when, backupCount=log_rotate_keep)
            elif log_rotate_max_bytes is not None:
                file_handler = RotatingFileHandler(
                                    log_filename, mode='a', maxBytes=log_rotate_max_bytes,
                                    backupCount=log_rotate_keep)
            file_handler.set_name('file')
            file_handler.setLevel(file_level)
            file_handler.setFormatter(formatter)
            FILE_HANDLER = file_handler
            root_logger.addHandler(file_handler)

        # Add memory logger to allow instant report
        memory_handler = CustomMemoryHandler()
        # Put in TRACE
        memory_handler.setLevel(5)
        memory_handler.set_name("memory")
        memory_handler.setFormatter(formatter)
        root_logger.addHandler(memory_handler)
        if filter_inotify:
            root_logger.addFilter(logging.Filter('watchdog.observers.inotify_buffer'))


def get_handler(logger, name):
    for handler in logger.handlers:
        if name == handler.get_name():
            return handler
    return None


def get_logger(name):
    logger = logging.getLogger(name)
    trace = lambda *args, **kwargs: logger.log(TRACE, *args, **kwargs)
    setattr(logger, 'trace', trace)
    return logger


class SumoHTTPHandler(logging.Handler):
    def __init__(self, url, host="collectors.sumologic.com", name=None, compressed=False):
        """
        Similar to HTTPHandler but with some custom Sumo-friendly headers
        """
        logging.Handler.__init__(self)
        self.host = host
        self.url = url
        self.name = name
        self.compressed = compressed

    def emit(self, record):
        try:
            import httplib, urllib
            host = self.host
            h = httplib.HTTPS(host)
            url = self.url
            data = urllib.quote(self.format(record))
            sep = "?"
            url = url + "%c%s" % (sep, data)
            h.putrequest("GET", url)
            h.putheader("Host", host)
            if self.compressed:
                h.putheader("Content-Encoding", "gzip")
            if self.name:
                h.putheader("X-Sumo-Name", self.name)
            h.endheaders()
            h.getreply()    #can't do anything with the result
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)

#logging config for sumo
LOGGING = {
    'version': 1,
    'handlers': {
        'sumo':{
            'level': "TRACE",
            'class': '__main__.SumoHTTPHandler',
            'url': '/receiver/v1/.....', #Replace with Sumo Hosted URL
        }
    },
    'loggers': {
        'sumologger': {
            'handlers': ['sumo'],
            'level': 'TRACE'
        }
    }
}