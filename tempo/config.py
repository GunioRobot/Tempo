#!/usr/bin/env python
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 Rackspace
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
Routines for configuring Tempo
"""

import ConfigParser
import logging
import logging.config
import logging.handlers
import optparse
import os
import re
import sys


DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)8s [%(name)s] %(message)s"
DEFAULT_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def parse_options(parser, cli_args=None):
    """
    Returns the parsed CLI options, command to run and its arguments, merged
    with any same-named options found in a configuration file.

    The function returns a tuple of (options, args), where options is a
    mapping of option key/str(value) pairs, and args is the set of arguments
    (not options) supplied on the command-line.

    The reason that the option values are returned as strings only is that
    ConfigParser only accepts string values...

    :param parser: The option parser
    :param cli_args: (Optional) Set of arguments to process. If not present,
                     sys.argv[1:] is used.
    :retval tuple of (options, args)
    """

    (options, args) = parser.parse_args(cli_args)

    return (vars(options), args)


def add_common_options(parser):
    """
    Given a supplied optparse.OptionParser, adds an OptionGroup that
    represents all common configuration options.

    :param parser: optparse.OptionParser
    """
    help_text = "The following configuration options are common to "\
                "all tempo programs."

    group = optparse.OptionGroup(parser, "Common Options", help_text)
    group.add_option('-v', '--verbose', default=False, dest="verbose",
                     action="store_true",
                     help="Print more verbose output")
    group.add_option('-d', '--debug', default=False, dest="debug",
                     action="store_true",
                     help="Print debugging output")
    group.add_option('--config-file', default=None, metavar="PATH",
                     help="Path to the config file to use. When not specified "
                          "(the default), we generally look at the first "
                          "argument specified to be a config file, and if "
                          "that is also missing, we search standard "
                          "directories for a config file.")
    parser.add_option_group(group)


def add_log_options(parser):
    """
    Given a supplied optparse.OptionParser, adds an OptionGroup that
    represents all the configuration options around logging.

    :param parser: optparse.OptionParser
    """
    help_text = "The following configuration options are specific to logging "\
                "functionality for this program."

    group = optparse.OptionGroup(parser, "Logging Options", help_text)
    group.add_option('--log-config', default=None, metavar="PATH",
                     help="If this option is specified, the logging "
                          "configuration file specified is used and overrides "
                          "any other logging options specified. Please see "
                          "the Python logging module documentation for "
                          "details on logging configuration files.")
    group.add_option('--log-date-format', metavar="FORMAT",
                      default=DEFAULT_LOG_DATE_FORMAT,
                      help="Format string for %(asctime)s in log records. "
                           "Default: %default")
    group.add_option('--log-file', default=None, metavar="PATH",
                      help="(Optional) Name of log file to output to. "
                           "If not set, logging will go to stdout.")
    group.add_option("--log-dir", default=None,
                      help="(Optional) The directory to keep log files in "
                           "(will be prepended to --logfile)")
    parser.add_option_group(group)


def setup_logging(options, conf):
    """
    Sets up the logging options for a log with supplied name

    :param options: Mapping of typed option key/values
    :param conf: Mapping of untyped key/values from config file
    """

    if options.get('log_config', None):
        # Use a logging configuration file for all settings...
        if os.path.exists(options['log_config']):
            logging.config.fileConfig(options['log_config'])
            return
        else:
            raise RuntimeError("Unable to locate specified logging "
                               "config file: %s" % options['log_config'])

    # If either the CLI option or the conf value
    # is True, we set to True
    debug = options.get('debug') or \
            get_option(conf, 'debug', type='bool', default=False)
    verbose = options.get('verbose') or \
            get_option(conf, 'verbose', type='bool', default=False)
    root_logger = logging.root
    if debug:
        root_logger.setLevel(logging.DEBUG)
    elif verbose:
        root_logger.setLevel(logging.INFO)
    else:
        root_logger.setLevel(logging.WARNING)

    # Set log configuration from options...
    log_format = options.get('log_format', DEFAULT_LOG_FORMAT)
    log_date_format = options.get('log_date_format', DEFAULT_LOG_DATE_FORMAT)
    formatter = logging.Formatter(log_format, log_date_format)

    logfile = options.get('log_file')
    if not logfile:
        logfile = conf.get('log_file')

    if logfile:
        logdir = options.get('log_dir')
        if not logdir:
            logdir = conf.get('log_dir')
        if logdir:
            logfile = os.path.join(logdir, logfile)
        logfile = logging.FileHandler(logfile)
        logfile.setFormatter(formatter)
        logfile.setFormatter(formatter)
        root_logger.addHandler(logfile)
    else:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)


def find_config_file(app_name, options, args):
    """
    Return the first config file found for an application.

    We search for the paste config file in the following order:
    * If --config-file option is used, use that
    * If args[0] is a file, use that
    * Search for $app.conf in standard directories:
        * .
        * ~/.tempo/
        * ~
        * /etc/tempo
        * /etc

    :retval Full path to config file, or None if no config file found
    """

    fix_path = lambda p: os.path.abspath(os.path.expanduser(p))
    if options.get('config_file'):
        if os.path.exists(options['config_file']):
            return fix_path(options['config_file'])
    elif args:
        if os.path.exists(args[0]):
            return fix_path(args[0])

    # Handle standard directory search for $app_name.conf
    config_file_dirs = [fix_path(os.getcwd()),
                        fix_path(os.path.join('~', '.tempo')),
                        fix_path('~'),
                        '/etc/tempo/',
                        '/etc']

    for cfg_dir in config_file_dirs:
        cfg_file = os.path.join(cfg_dir, '%s.conf' % app_name)
        if os.path.exists(cfg_file):
            return cfg_file


def _load_config(app_name, options, args):
    """
    Looks for a config file to use for an app and returns the
    config file path and a configuration mapping from a paste config file.

    We search for the paste config file in the following order:
    * If --config-file option is used, use that
    * If args[0] is a file, use that
    * Search for $app_name.conf in standard directories:
        * .
        * ~/.tempo/
        * ~
        * /etc/tempo
        * /etc

    :param app_name: Name of the application to load config for, or None.
                     None signifies to only load the [DEFAULT] section of
                     the config file.
    :param options: Set of typed options returned from parse_options()
    :param args: Command line arguments from argv[1:]
    :retval Tuple of (conf_file, conf)

    :raises RuntimeError when config file cannot be located or there was a
            problem loading the configuration file.
    """
    conf_file = find_config_file(app_name, options, args)
    if not conf_file:
        raise RuntimeError("Unable to locate any configuration file")
    try:
        conf = ConfigParser.SafeConfigParser()
        conf.read(conf_file)
    except Exception, e:
        raise RuntimeError("Error trying to load config %s: %s"
                           % (conf_file, e))

    conf_data = dict(conf.items('DEFAULT'))
    if conf.has_section(app_name):
        conf_data.update(dict(conf.items(app_name)))
    return conf_file, conf_data


def load_config(app_name, options, args):
    """
    Loads configuration.

    We search for the config file in the following order:
    * If --config-file option is used, use that
    * If args[0] is a file, use that
    * Search for $app_name.conf in standard directories:
        * .
        * ~/.tempo/
        * ~
        * /etc/tempo
        * /etc

    :param app_name: Name of the application to load
    :param options: Set of typed options returned from parse_options()
    :param args: Command line arguments from argv[1:]

    :raises RuntimeError when config file cannot be located or application
            cannot be loaded from config file
    """
    conf_file, conf = _load_config(app_name, options, args)

    # Setup logging early, supplying both the CLI options and the
    # configuration mapping from the config file
    setup_logging(options, conf)

    # We only update the conf dict for the verbose and debug
    # flags. Everything else must be set up in the conf file...
    debug = options.get('debug') or \
            get_option(conf, 'debug', type='bool', default=False)
    verbose = options.get('verbose') or \
            get_option(conf, 'verbose', type='bool', default=False)
    conf['debug'] = debug
    conf['verbose'] = verbose

    # Log the options used when starting if we're in debug mode...
    if debug:
        logger = logging.getLogger(app_name)
        logger.debug("*" * 80)
        logger.debug("Configuration options gathered from config file:")
        logger.debug(conf_file)
        logger.debug("================================================")
        items = dict([(k, v) for k, v in conf.items()
                      if k not in ('__file__', 'here')])
        for key, value in sorted(items.items()):
            logger.debug("%(key)-30s %(value)s" % locals())
        logger.debug("*" * 80)

    return conf


def get_option(options, option, **kwargs):
    if option in options:
        value = options[option]
        type_ = kwargs.get('type', 'str')
        if type_ == 'bool':
            if hasattr(value, 'lower'):
                return value.lower() == 'true'
            else:
                return value
        elif type_ == 'int':
            return int(value)
        elif type_ == 'float':
            return float(value)
        else:
            return value
    elif 'default' in kwargs:
        return kwargs['default']
    else:
        raise KeyError("option '%s' not found" % option)
