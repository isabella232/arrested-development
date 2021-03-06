#!/usr/bin/env python

"""
Project-wide application configuration.

DO NOT STORE SECRETS, PASSWORDS, ETC. IN THIS FILE.
They will be exposed to users. Use environment variables instead.
See get_secrets() below for a fast way to access them.
"""

import logging
import os

"""
NAMES
"""
# Project name used for display
PROJECT_NAME = 'Previously, On Arrested Development'
PROJECT_SUBTITLE = 'NPR\'s guide to the running gags from the show.'

# Project name used for paths on the filesystem and in urls
# Use dashes, not underscores
PROJECT_SLUG = 'arrested-development'

# The name of the repository containing the source
REPOSITORY_NAME = 'arrested-development'

"""
DEPLOYMENT
"""
PRODUCTION_S3_BUCKET = 'apps.npr.org'
PRODUCTION_SERVERS = ['cron.nprapps.org']

STAGING_S3_BUCKET = 'stage-apps.npr.org'
STAGING_SERVERS = ['50.112.92.131']

# Should code be deployed to the web/cron servers?
DEPLOY_TO_SERVERS = False

# Should the crontab file be installed on the servers?
# If True, DEPLOY_TO_SERVERS must also be True
DEPLOY_CRONTAB = False

# Should the service configurations be installed on the servers?
# If True, DEPLOY_TO_SERVERS must also be True
DEPLOY_SERVICES = False

# These variables will be set at runtime. See configure_targets() below
S3_BUCKETS = []
SERVERS = []
DEBUG = True

"""
APP CONSTANTS
"""
PRIMARY_CHARACTER_LIST = [
    'The Bluths',
    'Michael',
    'G.O.B.',
    'Tobias',
    'Lindsay',
    'Buster',
    'Oscar',
    'George Sr.',
    'Lucille',
    'Maeby',
    'George Michael',
    'Miscellaneous'
]

IMPORT_NEW_SEASON = True

"""
SHARING
"""
PROJECT_DESCRIPTION = 'NPR\'s slightly obsessive guide to the running gags on Arrested Development, updated for season 4.'
SHARE_URL = 'http://%s/%s/' % (PRODUCTION_S3_BUCKET, PROJECT_SLUG)


TWITTER = {
    'TEXT': 'We\'ve made a huge mistake. Now with season 4. Previously, on Arrested Development...',
    'URL': SHARE_URL
}

FACEBOOK = {
    'TITLE': PROJECT_NAME,
    'URL': SHARE_URL,
    'DESCRIPTION': PROJECT_DESCRIPTION,
    'IMAGE_URL': 'http://apps.npr.org/arrested-development/img/promo-facebook.png',
    'APP_ID': '138837436154588'
}

NPR_DFP = {
    'STORY_ID': '184818002',
    'TARGET': '\/arts___life_pop_culture;storyid=184818002'
}

"""
SERVICES
"""
GOOGLE_ANALYTICS_ID = 'UA-5828686-4'


"""
Logging
"""
LOG_FORMAT = '%(levelname)s:%(name)s:%(asctime)s: %(message)s'

"""
Utilities
"""
def get_secrets():
    """
    A method for accessing our secrets.
    """
    env_var_prefix = PROJECT_SLUG.replace('-', '')

    secrets = [
        '%s_TUMBLR_APP_KEY' % env_var_prefix,
        '%s_TUMBLR_OAUTH_TOKEN' % env_var_prefix,
        '%s_TUMBLR_OAUTH_TOKEN_SECRET' % env_var_prefix,
        '%s_TUMBLR_APP_SECRET' % env_var_prefix
    ]

    secrets_dict = {}

    for secret in secrets:
        # Saves the secret with the old name.
        secrets_dict[secret.replace('%s_' % env_var_prefix, '')] = os.environ.get(secret, None)

    return secrets_dict

def configure_targets(deployment_target):
    """
    Configure deployment targets. Abstracted so this can be
    overriden for rendering before deployment.
    """
    global S3_BUCKET
    global SERVERS
    global DEBUG
    global LOG_LEVEL

    global APPS_NODE_PATH

    APPS_NODE_PATH = 'node_modules/.bin'

    if os.path.exists('node_modules/bin/lessc'):
        APPS_NODE_PATH = 'node_modules/bin'

    if deployment_target == 'production':
        S3_BUCKET = PRODUCTION_S3_BUCKET
        SERVERS = PRODUCTION_SERVERS
        DEBUG = False
        LOG_LEVEL = logging.WARNING
    else:
        S3_BUCKET = STAGING_S3_BUCKET
        SERVERS = STAGING_SERVERS
        DEBUG = True
        LOG_LEVEL = logging.DEBUG

"""
Run automated configuration
"""
DEPLOYMENT_TARGET = os.environ.get('DEPLOYMENT_TARGET', None)

configure_targets(DEPLOYMENT_TARGET)
