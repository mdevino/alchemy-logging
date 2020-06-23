# *****************************************************************
#
# Licensed Materials - Property of IBM
#
# (C) Copyright IBM Corp. 2017. All Rights Reserved.
#
# US Government Users Restricted Rights - Use, duplication or
# disclosure restricted by GSA ADP Schedule Contract with IBM Corp.
#
# *****************************************************************
"""Alchemy Logger is a logging framework built on top of the standard python
logging package with a number of additional features, including log channels,
configurable formatting and scoped loggers.
"""
import functools
import json
import logging
import time
import threading
import traceback
from datetime import datetime, timedelta

## Formatters ##################################################################

g_thread_id_enabled = False

class AlogFormatterBase(logging.Formatter):
    """Base class with common functionality for alog formatters.
    """

    class ThreadLocalIndent(threading.local):
        '''Private subclass of threading.local which initializes to 0 on
        construction
        '''
        def __init__(self):
            self.indent = 0

        def __getstate__(self):
            return None

        def __setstate__(self, d):
            pass

    def __init__(self):
        # Hold a thread-local map for storing indentation so that the counts are
        # kept independently for each thread. Note that threading.local values
        # are cleaned up when their local thread dies, so this is safe to use
        # with ephemeral threads.
        self._indent = self.ThreadLocalIndent()

        # Initialize the underlying logger with this formatter
        logging.Formatter.__init__(self)

    def formatTime(self, record, datefmt=None):
        """A wrapper for the parent formatTime that returns UTC timezone
        time stamp inISO format.

        Args:
            record (LogRecord):  Log record to pull the created date from.
            datefmt (str):       Ignored.

        Returns:
            A string representation of created datetime.
        """
        return datetime.utcfromtimestamp(record.created).isoformat()

    def indent(self):
        """Add a level of indentation for this thread.
        """
        self._indent.indent += 1

    def deindent(self):
        """Remove a level of indentation for this thread.
        """
        if self._indent.indent > 0:
            self._indent.indent -= 1

class AlogJsonFormatter(AlogFormatterBase):
    """Log formatter which prints messages a single-line json.
    """
    _FIELDS_TO_PRINT = ['name', 'levelname', 'asctime', 'message',
                        'exc_text', 'region-id', 'org-id', 'tran-id',
                        'watson-txn-id', 'channel']

    def __init__(self):
        AlogFormatterBase.__init__(self)

    @staticmethod
    def _map_to_common_key_name(log_record_keyname):
        if log_record_keyname == 'levelname':
            return 'level'
        elif log_record_keyname == 'asctime':
            return 'timestamp'
        elif log_record_keyname == 'exc_text':
            return 'exception'
        elif log_record_keyname == 'name':
            return 'channel'
        else:
            return log_record_keyname

    def _extract_fields_from_record_as_dict(self, record):
        """Extracts the fields we want out of log record and puts them into an
        dict for easy jsonification.

        Args:
            record (logging.LogRecord): The log record object to extract from.

        Returns:
            The relevant fields pulled out from the log record object and
            initialized into a dictionary.
        """
        out = {}
        for field_name in self._FIELDS_TO_PRINT:
            if hasattr(record, field_name):
                record_field = getattr(record, field_name)
                if isinstance(record_field, dict):
                    out.update(record_field)
                else:
                    out[self._map_to_common_key_name(field_name)] = record_field

        out["level"] = out["level"].lower()
        return out

    def format(self, record):
        """Formats the log record as a JSON formatted string
       (also removes new line characters so everything prints on a single line)

        Args:
            record (logging.LogRecord):  The record to extract from.

        Returns:
            The jsonified string representation of the record.
        """
        # Maintain the message as a dict if passed in as one
        if isinstance(record.msg, dict):
            record.message = record.msg
        else:
            record.message = record.getMessage()

        record.asctime = self.formatTime(record, self.datefmt)
        if record.exc_info:
            record.exc_text = self.formatException(record.exc_info)

        if record.stack_info:
            record.stack_info = self.formatStack(record.stack_info)

        log_record = self._extract_fields_from_record_as_dict(record)

        # Add indent to all log records
        log_record['num_indent'] = self._indent.indent

        # If enabled, add thread id
        if g_thread_id_enabled:
            log_record['thread_id'] = threading.get_ident()

        return json.dumps(log_record, sort_keys=True)

class AlogPrettyFormatter(AlogFormatterBase):
    """Log formatter that pretty-prints lines for easy visibility.
    """
    _INDENT = "  "
    _LEVEL_MAP = {
        "critical": "FATL",
        "fatal": "FATL",
        "error": "ERRR",
        "warning": "WARN",
        "info": "INFO",
        "trace": "TRCE",
        "debug": "DBUG",
        "debug1": "DBG1",
        "debug2": "DBG2",
        "debug3": "DBG3",
        "debug4": "DBG4",
    }

    def __init__(self, channel_len=5):
        AlogFormatterBase.__init__(self)
        self.channel_len = channel_len

    def _make_header(self, timestamp, channel, level, log_code):
        """Create the header for a log line with proper padding.
        """
        # Get the padded or truncated channel
        chan = channel
        if len(channel) > self.channel_len:
            chan = channel[:self.channel_len]

        elif len(channel) < self.channel_len:
            chan = channel + ' ' * (self.channel_len - len(channel))

        # Get the mapped level
        lvl = self._LEVEL_MAP.get(level.lower(), "UNKN")

        # If thread id enabled, add it
        header = "%s [%s:%s" % (timestamp, chan, lvl)
        if g_thread_id_enabled:
            header += ":%d" % threading.get_ident()
        header += "]"

        # Add log code if present
        if log_code is not None:
            header += " %s" % log_code

        return header

    def format(self, record):
        """Formats the log record as pretty-printed lines of the format:

        timestamp [CHANL:LEVL] message
        """
        # Extract special values from the message if it's a dict
        metadata = None
        if isinstance(record.msg, dict):
            if 'message' in record.msg:
                record.message = record.msg.pop('message')
            if 'log_code' in record.msg:
                record.log_code = record.msg.pop('log_code')
            metadata = record.msg
        else:
            record.message = record.getMessage()

        # Add metadata if present
        if not hasattr(record, 'message'):
            record.message = ''
        if metadata is not None and len(metadata) > 0:
            if len(record.message) > 0:
                record.message += ' '
            record.message += json.dumps(metadata)

        level = record.levelname
        channel = record.name
        timestamp = self.formatTime(record, self.datefmt)
        log_code = record.log_code if hasattr(record, 'log_code') else None
        header = self._make_header(timestamp, channel, level, log_code)
        # Pretty format the message
        indent = self._INDENT*self._indent.indent
        if isinstance(record.message, str):
            formatted = ['%s %s%s' % (header, indent, line) for line in record.message.split('\n')]
        else:
            formatted = ['%s %s%s' % (header, indent, str(record.message))]

        # Add stack trace if present
        if record.exc_info:
            formatted.extend(['%s %s%s' % (header, indent, line) for line in self.formatException(record.exc_info).split('\n')])

        formatted = '\n'.join(formatted)
        return formatted

## Constants ###################################################################

# Global maps from name <-> level, pull from logging packages for consistency
# pylint: disable=protected-access
g_alog_level_to_name = {level: name.lower() for level, name in logging._levelToName.items()}

# Extra custom log levels
g_alog_level_to_name.update({
    60: "off",
    15: "trace",
    9: "debug1",
    8: "debug2",
    7: "debug3",
    6: "debug4",
})

g_alog_name_to_level = {name: level for level, name in g_alog_level_to_name.items()}

# Global map of default formatters
g_alog_formatters = {
    "json": AlogJsonFormatter,
    "pretty": AlogPrettyFormatter,
}

scope_start_str = "BEGIN: "
scope_end_str = "END: "

## Implementation Details ######################################################

g_alog_formatter = None

def is_log_code(arg):
    return arg.startswith('<') and arg.endswith('>')

def _log_with_code_method_override(self, value, arg_one, *args, **kwargs):
    """This helper is used as an override to the native logging.Logger instance
    methods for each level. As such, it's first argument, self, is the logger
    instance (or the global root logger singleton) on which to call the method.
    Having this as the first argument allows it to override the native methods
    and support functionality like:

    ch = alog.use_channel('FOO')
    ch.debug('<FOO80349757I>', 'Logging is fun!')
    """

    # If no positional args, arg_one is message
    if len(args) == 0:
        self.log(value, arg_one, **kwargs)

    # If arg_one looks like a log code, use the first positional arg as message
    elif is_log_code(arg_one):
        message = args[0] % tuple(args[1:]) if len(args) > 1 else args[0]
        self.log(value, {"log_code": arg_one, "message": message}, **kwargs)

    # Otherwise, treat arg_one as the message
    else:
        self.log(value, arg_one, *args, **kwargs)

def _add_level_fn(name, value):
    logging.addLevelName(value, name.upper())

    log_using_self_func = lambda self, arg_one, *args, **kwargs: \
        _log_with_code_method_override(self, value, arg_one, *args, **kwargs)
    setattr(log_using_self_func, '_value', value)
    setattr(logging.Logger, name, log_using_self_func)

    log_using_logging_func = lambda arg_one, *args, **kwargs: \
        _log_with_code_method_override(logging, value, arg_one, *args, **kwargs)
    setattr(log_using_logging_func, '_value', value)
    setattr(logging, name, log_using_logging_func)

def _add_is_enabled():
    is_enabled_func = lambda self, level: \
        self.isEnabledFor(level if isinstance(level, int) else g_alog_name_to_level.get(level))
    setattr(logging.Logger, 'isEnabled', is_enabled_func)

def _setup_formatter(formatter):
    # If the formatter is a string, pull it from the defaults
    global g_alog_formatter
    if isinstance(formatter, str):
        # Get the formatter class
        fmt_class = g_alog_formatters.get(formatter, None)
        if fmt_class is None:
            raise ValueError("Invalid formatter: %s" % formatter)

        # Set up the formatter if different type
        if not isinstance(g_alog_formatter, fmt_class):
            g_alog_formatter = fmt_class()

    # If the formatter is a valid AlogFormatterBase, use it directly
    elif isinstance(formatter, AlogFormatterBase):
        g_alog_formatter = formatter

    # Otherwise, log a warning and use the pretty printer
    else:
        raise ValueError("Invalid formatter type: %s" % type(formatter))

def _parse_filters(filters):
    # Check to see if we've got a dictionary. If we do, keep the valid filter entries
    if isinstance(filters, dict):
        return _parse_dict_of_filters(filters)
    elif isinstance(filters, str):
        if len(filters):
            return _parse_str_of_filters(filters)
        else:
            return {}
    else:
        logging.warning("Invalid filter type [%s] was ignored!", type(filters).__name__)
        return {}

def _parse_dict_of_filters(filters):
    for entry, level_name in filters.items():
        if g_alog_name_to_level.get(level_name, None) is None:
            logging.warning("Invalid filter entry [%s]", entry)
            del filters[entry]
    return filters

def _parse_str_of_filters(filters):
    chan_map = {}
    for entry in filters.split(','):
        if len(entry):
            parts = entry.split(':')
            if len(parts) != 2:
                logging.warning("Invalid filter entry [%s]", entry)
            else:
                chan, level_name = parts
                level = g_alog_name_to_level.get(level_name, None)
                if level is None:
                    logging.warning("Invalid level [%s] for channel [%s]", level_name, chan)
                else:
                    chan_map[chan] = level_name
        else:
            logging.warning("Invalid filter entry [%s]", entry)
    return chan_map

## Core ########################################################################

def configure(default_level, filters="", formatter='pretty', thread_id=False):
    """Top-level configuration function for the alog module. This function
    configures the logging package to use the given default level and
    overwrites the levels for all filters as specified. It can also configure
    the formatter type.

    Args:
        default_level   str
            This is the level that will be enabled for a given channel when a
            specific level has not been set in the filters.
        filters         str/dict
            This is a mapping from channel name to level that allows levels to
            be set on a per-channel basis. If a string, it is formatted as
            "CHAN:info,FOO:debug". If a dict, it should map from channel string
            to level string.
        formatter       str ('pretty' or 'json')/AlogFormatterBase
            The formatter is either the string 'pretty' or 'json' to indicate
            one of the default formatting options or an instance of
            AlogFormatterBase for a custom formatter implementation
        thread_id       bool
            If true, include thread
    """
    # Set up the formatter if different type
    _setup_formatter(formatter)

    # Set up thread id logging
    global g_thread_id_enabled
    g_thread_id_enabled = thread_id

    # Remove any existing handlers
    formatters = [h for h in logging.root.handlers if isinstance(h.formatter, AlogFormatterBase)]
    for handler in formatters:
        logging.root.removeHandler(handler)

    # Add the formatter
    handler = logging.StreamHandler()
    handler.setFormatter(g_alog_formatter)
    logging.root.addHandler(handler)

    # Add custom low levels
    for level, name in g_alog_level_to_name.items():
        if name not in ["off", "notset"]:
            _add_level_fn(name, level)

    # Patch over isEnabledFor to support level names
    _add_is_enabled()

    # Set default level
    default_level_val = g_alog_name_to_level.get(default_level, None)
    if default_level_val is not None:
        logging.root.setLevel(default_level_val)
        for handler in logging.root.handlers:
            handler.setLevel(default_level_val)
    else:
        logging.warning("Invalid default_level [%s]", default_level)

    # Add level filters by name
    # NOTE: All levels assumed valid after call to _parse_filters
    for chan, level_name in _parse_filters(filters).items():
        level = g_alog_name_to_level[level_name]
        handler = logging.StreamHandler()
        handler.setFormatter(g_alog_formatter)
        handler.setLevel(level)
        lgr = logging.getLogger(chan)
        lgr.setLevel(level)
        lgr.propagate = False
        lgr.addHandler(handler)

def use_channel(channel):
    """Interface wrapper for python alog implementation to keep consistency with
    other languages.
    """
    return logging.getLogger(channel)

## Scoped Loggers ##############################################################

# The whole point of this class is act on scope changes
# pylint: disable=too-few-public-methods
class _ScopedLogBase:
    """Base class for scoped loggers.  This class provides methods for starting
    and stopping the logger and expects the child class to call them when
    appropriate.
    """
    def __init__(self, log_fn, format_str="", *args):
        """Construct a new scoped logger.
        """
        self.log_fn = log_fn
        self.format_str = format_str
        self.args = args

        # This context is enabled IFF the function bound to it is enabled. To
        # get at that information, we need to figure out which function it is,
        # and to do that, we need to poke around in the guts of it.
        assert hasattr(self.log_fn, '_value'), \
            'Cannot use non-logging function for scoped log'
        self.enabled = self.log_fn.__self__.isEnabledFor(self.log_fn._value)

    def _start_scoped_log(self):
        """Log the start message for a scoped logger and increment the indentor.
        """
        if self.enabled:
            self.log_fn(scope_start_str + str(self.format_str), *self.args)
            global g_alog_formatter
            g_alog_formatter.indent()

    def _end_scoped_log(self):
        """Log the end message for a scoped logger and decrement the indentor.
        """
        if self.enabled:
            global g_alog_formatter
            g_alog_formatter.deindent()
            self.log_fn(scope_end_str + str(self.format_str), *self.args)

# pylint: disable=too-few-public-methods
class ScopedLog(_ScopedLogBase):
    """Scoped log prints a begin message when constructed and an end message on
    deletion, i.e., soon after the object leaves scope.

    Examples:
        >>> def test_function():
        >>>     # will log begin message here and end message after returning
        >>>     _ = alog.ScopedLog(log_channel.debug)
    """
    def __init__(self, log_fn, format_str="", *args):
        """Construct a new scoped logger and print the begin message.
        """
        super().__init__(log_fn, format_str, *args)
        self._start_scoped_log()

    def __del__(self):
        """Print the end message when this logger is deleted.
        """
        self._end_scoped_log()

# pylint: disable=too-few-public-methods
class ContextLog(_ScopedLogBase):
    """Context log prints a begin message when a context manager is entered and
    the end message when the context manager exits.

    Examples:
        >>> with alog.ContextLog(chan.debug):
        >>>   # logs begin message when context manager is entered
        >>>   print('hello world')
        >>>   # logs the end message when the context manager exits
    """
    def __enter__(self):
        """Log the begin message when the context manager starts.
        """
        self._start_scoped_log()
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        """Log the end message when the context manager exits.
        """
        self._end_scoped_log()

# pylint: disable=too-few-public-methods
class FunctionLog(ScopedLog):
    """Function log behaves like a ScopedLog but adds the function name to the
    begin and end messages.  This is intended to be used for loging when a
    function starts and ends.

    Notes:
        Using the @alog.logged_function decorator is the prefered (pythonic) method
        for logging functions, consider using that instead.

    Examples:
        >>> def test_function():
        >>>     # will log the begin message here and end message after the
        >>>     # function returns messages will include the name test_function
        >>>     _ = alog.FunctionLog(log_channel.debug)
    """
    def __init__(self, log_fn, format_str="", *args):
        fn_name = traceback.format_stack()[-2].strip().split(',')[2].split(' ')[2].strip()
        format_str = "%s(" + format_str + ")"
        super().__init__(log_fn, format_str, fn_name, *args)

# older name for FunctionLog, provided for compatibility
class FnLog(FunctionLog):
    pass

def logged_function(log_fn, format_str="", *fmt_args):
    """Function log decorator is a scoped log that adds the function name to the
    begin and end messages.  This is intended to be used for loging when a
    function starts and ends.

    Examples:
        >>> @alog.logged_function(log_channel.debug)
        >>> def test_function():
        >>>     # will log the begin message before the function is entered and
        >>>     # the end message after the function exits
        >>>     print('hello world!')
    """
    # decorator function returned after arguments are passed
    def decorator(func):
        # wrapper function returned by decorator
        @functools.wraps(func) # ensures that docstrings are maintained
        def wrapper(*args, **kwargs):
            fmt_str = "%s(" + format_str + ")"
            with ContextLog(log_fn, fmt_str, func.__name__, *fmt_args):
                return func(*args, **kwargs)
        return wrapper
    return decorator

## Timers ######################################################################

class _TimedLogBase:
    """Base class for timed loggers.  This class provides methods for starting
    and stopping the logger and expects the child class to call them when
    appropriate.
    """
    def __init__(self, log_fn, format_str="", *args):
        """Construct a new timed logger.
        """
        self.log_fn = log_fn
        self.format_str = format_str
        self.args = args
        self.start_time = 0

    def _start_timed_log(self):
        """Get the start time for this timed logger.
        """
        self.start_time = time.time()

    def _end_timed_log(self):
        """Gets the end time and prints the end message for this timed logger.
        """
        duration = str(timedelta(seconds=time.time() - self.start_time))
        fmt = self.format_str + "%s"
        args = list(self.args) + [duration]
        self.log_fn(fmt, *args)

# pylint: disable=too-few-public-methods
class ScopedTimer(_TimedLogBase):
    """Scoped timer that starts a timer at construction and logs the time delta
    at destruction.

    Notes:
        Using the @alog.timed_function decorator is the prefered (pythonic)
        method for timing entire functions, consider using that instead.

    Examples:
        >>> def test_function():
        >>>     # will log the time delta when the function exits
        >>>     _ = alog.ScopedTimer(log_channel.debug)
    """
    def __init__(self, log_fn, format_str="", *args):
        """Construct a new scoped timer and get the start time.
        """
        super().__init__(log_fn, format_str, *args)
        self._start_timed_log()

    def __del__(self):
        """Log the end message, including time delta, when this timer is deleted.
        """
        self._end_timed_log()

class ContextTimer(_TimedLogBase):
    """Context timer that starts a timer when a context is entered and logs the
    time delta when the context exits.

    Examples:
        >>> with alog.ContextTimer(chan.debug):
        >>>   # starts the timer when the context starts
        >>>   print('hello world')
        >>>   # logs the time delta when the context manager exits
    """
    def __enter__(self):
        """Start the timer when a context is entered.
        """
        self._start_timed_log()
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        """Log the end message, including time delta, when the context exits.
        """
        self._end_timed_log()

def timed_function(log_fn, format_str="", *fmt_args):
    """Timed function decorator is a scoped timer that adds the function name to
    the end messages.  This is intended to be used for loging the time required
    for a function to complete.

    Examples:
        >>> @alog.timed_function(log_channel.debug)
        >>> def test_function():
        >>>     # will start the timer just before test_function begins and log
        >>>     # the time spent after it returns
        >>>     print('hello world!')
    """
    # decorator function returned after arguments are passed
    def decorator(func):
        # wrapper function returned by decorator
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with ContextTimer(log_fn, format_str, *fmt_args):
                return func(*args, **kwargs)
        return wrapper
    return decorator
