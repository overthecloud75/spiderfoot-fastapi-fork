import os
import sys

from spiderfoot import SpiderFootHelpers
from spiderfoot import SpiderFootDb
from spiderfoot import SpiderFootCorrelator
from .logging_config import logger


SF_CONFIG = {
    '_debug': False,  # Debug
    '_maxthreads': 3,  # Number of modules to run concurrently
    '__logging': True,  # Logging in general
    '__outputfilter': None,  # Event types to filter from modules' output
    '_useragent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36',
    '_dnsserver': '',  # Override the default resolver
    '_fetchtimeout': 5,  # number of seconds before giving up on a fetch
    '_internettlds': 'https://publicsuffix.org/list/effective_tld_names.dat',
    '_internettlds_cache': 72,
    '_genericusers': ",".join(SpiderFootHelpers.usernamesFromWordlists(['generic-usernames'])),
    '__modules__': None,  # List of modules. Will be set after start-up.
    '__correlationrules__': None,  # List of correlation rules. Will be set after start-up.
    '_socks1type': '',
    '_socks2addr': '',
    '_socks3port': '',
    '_socks4user': '',
    '_socks5pwd': '',
}

OPT_DESCS = {
    '_debug': "Enable debugging?",
    '_maxthreads': "Max number of modules to run concurrently",
    '_useragent': "User-Agent string to use for HTTP requests. Prefix with an '@' to randomly select the User Agent from a file containing user agent strings for each request, e.g. @C:\\useragents.txt or @/home/bob/useragents.txt. Or supply a URL to load the list from there.",
    '_dnsserver': "Override the default resolver with another DNS server. For example, 8.8.8.8 is Google's open DNS server.",
    '_fetchtimeout': "Number of seconds before giving up on a HTTP request.",
    '_internettlds': "List of Internet TLDs.",
    '_internettlds_cache': "Hours to cache the Internet TLD list. This can safely be quite a long time given that the list doesn't change too often.",
    '_genericusers': "List of usernames that if found as usernames or as part of e-mail addresses, should be treated differently to non-generics.",
    '_socks1type': "SOCKS Server Type. Can be '4', '5', 'HTTP' or 'TOR'",
    '_socks2addr': 'SOCKS Server IP Address.',
    '_socks3port': 'SOCKS Server TCP Port. Usually 1080 for 4/5, 8080 for HTTP and 9050 for TOR.',
    '_socks4user': 'SOCKS Username. Valid only for SOCKS4 and SOCKS5 servers.',
    '_socks5pwd': "SOCKS Password. Valid only for SOCKS5 servers.",
    '_modulesenabled': "Modules enabled for the scan."  # This is a hack to get a description for an option not actually available.
}

# Add descriptions of the global config options
SF_CONFIG['__globaloptdescs__'] = OPT_DESCS

mod_dir = 'modules/'
SF_MODULES = SpiderFootHelpers.loadModulesAsDict(mod_dir, ['sfp_template.py'])

def initialize():
    
    # Initialize database handle
    try:
        dbh = SpiderFootDb()
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}", exc_info=True)
        sys.exit(-1)

    try:
        correlations_dir = 'correlations/'
        correlationRulesRaw = SpiderFootHelpers.loadCorrelationRulesRaw(correlations_dir, ['template.yaml'])
    except BaseException as e:
        logger.critical(f"Failed to load correlation rules: {e}", exc_info=True)
        sys.exit(-1)

    # Sanity-check the rules and parse them
    sfCorrelationRules = list()
    if not correlationRulesRaw:
        logger.error(f"No correlation rules found in correlations directory: {correlations_dir}")
    else:
        try:
            correlator = SpiderFootCorrelator(dbh, correlationRulesRaw)
            sfCorrelationRules = correlator.get_ruleset()
            dbh.close()
        except Exception as e:
            logger.critical(f"Failure initializing correlation rules: {e}", exc_info=True)
            sys.exit(-1)

    # Add modules and correlation rules to SF_CONFIG so they can be used elsewhere
    SF_CONFIG['__modules__'] = SF_MODULES
    SF_CONFIG['__correlationrules__'] = sfCorrelationRules

initialize()

