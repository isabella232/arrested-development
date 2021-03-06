#!/usr/bin/env python

from glob import glob
import gzip
import os

import boto
from boto.s3.connection import OrdinaryCallingFormat
from fabric.api import *
from jinja2 import Template
import requests

import app
import app_config
import app_utils
from etc import github
from models import Joke, Episode

import flat
import utils

"""
Base configuration
"""
env.project_slug = app_config.PROJECT_SLUG
env.repository_name = app_config.REPOSITORY_NAME

env.deploy_to_servers = app_config.DEPLOY_TO_SERVERS
env.deploy_crontab = app_config.DEPLOY_CRONTAB
env.deploy_services = app_config.DEPLOY_SERVICES

env.repo_url = 'git@github.com:nprapps/%(repository_name)s.git' % env
env.alt_repo_url = None  # 'git@bitbucket.org:nprapps/%(repository_name)s.git' % env
env.user = 'ubuntu'
env.python = 'python2.7'
env.path = '/home/%(user)s/apps/%(project_slug)s' % env
env.repo_path = '%(path)s/repository' % env
env.virtualenv_path = '%(path)s/virtualenv' % env
env.forward_agent = True

SERVICES = [
    ('nginx', '/etc/nginx/locations-enabled/'),
    ('uwsgi', '/etc/init/')
]

"""
Environments

Changing environment requires a full-stack test.
An environment points to both a server and an S3
bucket.
"""
def production():
    env.settings = 'production'
    env.s3_buckets = app_config.PRODUCTION_S3_BUCKET
    env.hosts = app_config.PRODUCTION_SERVERS
    app_config.configure_targets(env.settings)

def staging():
    env.settings = 'staging'
    env.s3_buckets = app_config.STAGING_S3_BUCKET
    env.hosts = app_config.STAGING_SERVERS

"""
Branches

Changing branches requires deploying that branch to a host.
"""
def stable():
    """
    Work on stable branch.
    """
    env.branch = 'stable'

def master():
    """
    Work on development branch.
    """
    env.branch = 'master'

def branch(branch_name):
    """
    Work on any specified branch.
    """
    env.branch = branch_name

"""
Template-specific functions

Changing the template functions should produce output
with fab render without any exceptions. Any file used
by the site templates should be rendered by fab render.
"""
def less():
    """
    Render LESS files to CSS.
    """
    for path in glob('less/*.less'):
        filename = os.path.split(path)[-1]
        name = os.path.splitext(filename)[0]
        out_path = 'www/css/%s.less.css' % name

        local('%s/lessc %s %s' % (app_config.APPS_NODE_PATH, path, out_path))

def jst():
    """
    Render Underscore templates to a JST package.
    """
    local('%s/jst --template underscore jst www/js/templates.js' % app_config.APPS_NODE_PATH)

def app_config_js():
    """
    Render app_config.js to file.
    """
    from app import _app_config_js

    response = _app_config_js()
    js = response[0]

    with open('www/js/app_config.js', 'w') as f:
        f.write(js)


def render():
    """
    Render HTML templates and compile assets.
    """
    from flask import g

    less()
    jst()

    # Fake out deployment target
    app_config.configure_targets(env.get('settings', None))

    app_config_js()

    compiled_includes = []

    for rule in app.app.url_map.iter_rules():
        rule_string = rule.rule
        name = rule.endpoint

        if name == 'static' or name.startswith('_'):
            print 'Skipping %s' % name
            continue

        if rule_string.endswith('/'):
            filename = 'www' + rule_string + 'index.html'
        elif rule_string.endswith('.html'):
            filename = 'www' + rule_string
        else:
            print 'Skipping %s' % name
            continue

        dirname = os.path.dirname(filename)

        if not (os.path.exists(dirname)):
            os.makedirs(dirname)

        print 'Rendering %s' % (filename)

        with app.app.test_request_context(path=rule_string):
            g.compile_includes = True
            g.compiled_includes = compiled_includes

            view = app.__dict__[name]
            content = view()

            compiled_includes = g.compiled_includes

        with open(filename, 'w') as f:
            f.write(content.encode('utf-8'))

    # Un-fake-out deployment target
    app_config.configure_targets(env.settings)


def render_pages():
    render()
    local('rm -rf www/episode*.html')
    local('rm -rf www/joke*.html')
    _render_iterable(Joke.select(), 'joke', 'code')
    _render_iterable(Episode.select(), 'episode', 'code')


def _render_iterable(iterable, model, lookup):
    """
    View should be named _model_detail().
    Path should be model-lookup.html.
    Template is handled from the view.
    """

    from flask import g

    # Fake out deployment target
    app_config.configure_targets(env.get('settings', None))

    compiled_includes = []

    for instance in iterable:
        path = '%s-%s.html' % (model, getattr(instance, lookup))
        with app.app.test_request_context(path=path):

            g.compile_includes = True
            g.compiled_includes = compiled_includes

            view = app.__dict__['_%s_detail' % model]
            content = view(getattr(instance, lookup))

            compiled_includes = g.compiled_includes

        with open('www/%s' % path, 'w') as f:
            f.write(content.encode('utf-8'))

    # Un-fake-out deployment target
    app_config.configure_targets(env.settings)


def tests():
    """
    Run Python unit tests.
    """
    local('nosetests')

"""
Setup

Changing setup commands requires a test deployment to a server.
Setup will create directories, install requirements and set up logs.
It may also need to set up Web services.
"""
def setup():
    """
    Setup servers for deployment.
    """
    require('settings', provided_by=[production, staging])
    require('branch', provided_by=[stable, master, branch])

    setup_directories()
    setup_virtualenv()
    clone_repo()
    checkout_latest()
    install_requirements()

    if env['deploy_services']:
        deploy_confs()

def setup_directories():
    """
    Create server directories.
    """
    require('settings', provided_by=[production, staging])

    run('mkdir -p %(path)s' % env)
    run('mkdir -p /var/www/uploads/%(project_slug)s' % env)

def setup_virtualenv():
    """
    Setup a server virtualenv.
    """
    require('settings', provided_by=[production, staging])

    run('virtualenv -p %(python)s --no-site-packages %(virtualenv_path)s' % env)
    run('source %(virtualenv_path)s/bin/activate' % env)

def clone_repo():
    """
    Clone the source repository.
    """
    require('settings', provided_by=[production, staging])

    run('git clone %(repo_url)s %(repo_path)s' % env)

    if env.get('alt_repo_url', None):
        run('git remote add bitbucket %(alt_repo_url)s' % env)

def checkout_latest(remote='origin'):
    """
    Checkout the latest source.
    """
    require('settings', provided_by=[production, staging])
    require('branch', provided_by=[stable, master, branch])

    env.remote = remote

    run('cd %(repo_path)s; git fetch %(remote)s' % env)
    run('cd %(repo_path)s; git checkout %(branch)s; git pull %(remote)s %(branch)s' % env)

def install_requirements():
    """
    Install the latest requirements.
    """
    require('settings', provided_by=[production, staging])

    run('%(virtualenv_path)s/bin/pip install -U -r %(repo_path)s/requirements.txt' % env)

def install_crontab():
    """
    Install cron jobs script into cron.d.
    """
    require('settings', provided_by=[production, staging])

    sudo('cp %(repo_path)s/crontab /etc/cron.d/%(project_slug)s' % env)

def uninstall_crontab():
    """
    Remove a previously install cron jobs script from cron.d
    """
    require('settings', provided_by=[production, staging])

    sudo('rm /etc/cron.d/%(project_slug)s' % env)

def bootstrap_issues():
    """
    Bootstraps Github issues with default configuration.
    """
    auth = github.get_auth()
    github.delete_existing_labels(auth)
    github.create_labels(auth)
    github.create_tickets(auth)

"""
Deployment

Changes to deployment requires a full-stack test. Deployment
has two primary functions: Pushing flat files to S3 and deploying
code to a remote server if required.
"""
def _deploy_to_s3():
    """
    Deploy the gzipped stuff to S3.
    """
    s3cmd = 's3cmd -P --add-header=Cache-Control:max-age=5 --guess-mime-type --recursive --exclude-from gzip_types.txt sync gzip/ %s'
    s3cmd_gzip = 's3cmd -P --add-header=Cache-Control:max-age=5 --add-header=Content-encoding:gzip --guess-mime-type --recursive --exclude "*" --include-from gzip_types.txt sync gzip/ %s'

    for bucket in env.s3_buckets:
        env.s3_bucket = bucket
        local(s3cmd % ('s3://%(s3_bucket)s/%(project_slug)s/' % env))
        local(s3cmd_gzip % ('s3://%(s3_bucket)s/%(project_slug)s/' % env))

def _gzip_www():
    """
    Gzips everything in www and puts it all in gzip
    """
    local('python gzip_www.py')
    local('rm -rf gzip/live-data')


def render_confs():
    """
    Renders server configurations.
    """
    require('settings', provided_by=[production, staging])

    with settings(warn_only=True):
        local('mkdir confs/rendered')

    context = app_config.get_secrets()
    context['PROJECT_SLUG'] = app_config.PROJECT_SLUG
    context['PROJECT_NAME'] = app_config.PROJECT_NAME
    context['DEPLOYMENT_TARGET'] = env.settings

    for service, remote_path in SERVICES:
        file_path = 'confs/rendered/%s.%s.conf' % (app_config.PROJECT_SLUG, service)

        with open('confs/%s.conf' % service, 'r') as read_template:

            with open(file_path, 'wb') as write_template:
                payload = Template(read_template.read())
                write_template.write(payload.render(**context))


def deploy_confs():
    """
    Deploys rendered server configurations to the specified server.
    This will reload nginx and the appropriate uwsgi config.
    """
    require('settings', provided_by=[production, staging])

    render_confs()

    with settings(warn_only=True):
        run('touch /tmp/%s.sock' % app_config.PROJECT_SLUG)

        for service, remote_path in SERVICES:
            service_name = '%s.%s' % (app_config.PROJECT_SLUG, service)
            file_name = '%s.conf' % service_name
            local_path = 'confs/rendered/%s' % file_name
            remote_path = '%s%s' % (remote_path, file_name)

            a = local('md5 -q %s' % local_path, capture=True)
            b = run('md5sum %s' % remote_path).split()[0]

            if a != b:
                put(local_path, remote_path, use_sudo=True)

                if service == 'nginx':
                    sudo('service nginx reload')
                else:
                    sudo('initctl reload-configuration')
                    sudo('service %s restart' % service_name)


def deploy(remote='origin'):
    """
    Deploy the latest app to S3 and, if configured, to our servers.
    """
    require('settings', provided_by=[production, staging])

    if env.get('deploy_to_servers', False):
        require('branch', provided_by=[stable, master, branch])

    if (env.settings == 'production' and env.branch != 'stable'):
        _confirm("You are trying to deploy the '%(branch)s' branch to production.\nYou should really only deploy a stable branch.\nDo you know what you're doing?" % env)

    render_pages()
    _gzip_www()

    print app_config.S3_BUCKET

    flat.deploy_folder(
        app_config.S3_BUCKET,
        'www',
        app_config.PROJECT_SLUG,
        headers={
            'Cache-Control': 'max-age=20'
        },
        ignore=['www/assets/*', 'www/live-data/*']
    )

    flat.deploy_folder(
        app_config.S3_BUCKET,
        'www/assets',
        '%s/assets' % app_config.PROJECT_SLUG,
        headers={
            'Cache-Control': 'max-age=86400'
        }
    )

    if env['deploy_to_servers']:
        checkout_latest(remote)

        if env['deploy_crontab']:
            install_crontab()

        if env['deploy_services']:
            deploy_confs()

"""
Cron jobs
"""
def cron_test():
    """
    Example cron task. Note we use "local" instead of "run"
    because this will run on the server.
    """
    require('settings', provided_by=[production, staging])

    local('echo $DEPLOYMENT_TARGET > /tmp/cron_test.txt')


"""
Application-specific jobs
"""
def ship_db():
    require('settings', provided_by=[production, staging])
    local_path = 'data/app.db'

    for bucket in env.s3_buckets:
        conn = boto.connect_s3()
        bucket = conn.get_bucket(bucket)
        key = boto.s3.key.Key(bucket)
        key.key = '%s/%s' % (app_config.PROJECT_SLUG, local_path)
        key.set_contents_from_filename(
            local_path,
            policy='public-read',
            headers={
                'Cache-Control': 'max-age=5 no-cache no-store must-revalidate',
                'Content-Encoding': 'text/plain'
            }
        )


def get_db():
    require('settings', provided_by=[production, staging])
    for bucket in env.s3_buckets:
        r = requests.get('http://%s/%s/data/app.db' % (bucket, app_config.PROJECT_SLUG))
        with open('data/app.db', 'wb') as dbfile:
            dbfile.write(r.content)


def bootstrap_data():
    """
    Runs all the commands necessary to build the system from scratch
    or rebuild the system to the latest available data.
    """
    setup_tables()
    update_episodes()
    update_jokes()
    update_episodejokes()
    update_episode_extras()
    update_joke_blurbs()
    update_details()
    update_connection()
    build_connections()
    write_jokes_json()


def setup_tables():
    """
    Deletes the sqlite db and associated data csv files.
    Rebuilds the db and the tables for our models.
    """
    with settings(warn_only=True):
        local('rm -rf data/app.db')
        local('rm -rf data/broken.csv')
        local('rm -rf data/arrested*.csv')
    app_utils.setup_tables()


def update_episodes():
    """
    GoogleDocs: Parses episode data.
    """
    import_sheet('1')
    parse_sheet('1', 'episodes')


def update_jokes():
    """
    GoogleDocs: Parses joke data.
    """
    import_sheet('0')
    parse_sheet('0', 'jokes')


def update_episodejokes():
    """
    GoogleDocs: Parses episodejoke data.
    """
    import_sheet('0')
    parse_sheet('0', 'episodejokes')


def update_joke_blurbs():
    """
    GoogleDocs: Gets Adam's joke blurbs.
    """
    import_sheet('7')
    parse_sheet('7', 'blurbs')


def update_connection():
    """
    GoogleDocs: Parses episodejoke connection data.
    """
    import_sheet('5')
    parse_sheet('5', 'episodejokes')


def update_details():
    """
    GoogleDocs: Parses episodejoke detail data.
    """
    import_sheet('3')
    parse_sheet('3', 'episodejokes')


def import_sheet(sheet):
    """
    Imports a sheet from GoogleDocs.
    Don't call this directly from fab.
    """
    app_utils.import_sheet(sheet)


def parse_sheet(sheet, model):
    """
    Parses a sheet from GoogleDocs.
    Don't call this directly from fab.
    """
    app_utils.parse_sheet(sheet, model)


def update_episode_extras():
    """
    Gets episode extras from Wikipedia.
    """
    app_utils.update_episode_extras()


def write_jokes_json():
    """
    Writes jokes JSON.
    """
    app_utils.write_jokes_json()


def build_connections():
    """
    Builds connections between instances of episodejokes.
    """
    app_utils.build_connections()


def build_regression_csv():
    """
    Writes a CSV for @stiles to use to do a regression.
    """
    app_utils.build_regression_csv()


"""
Destruction

Changes to destruction require setup/deploy to a test host in order to test.
Destruction should remove all files related to the project from both a remote
host and S3.
"""
def _confirm(message):
    answer = prompt(message, default="Not at all")

    if answer.lower() not in ('y', 'yes', 'buzz off', 'screw you'):
        exit()


def nuke_confs():
    """
    DESTROYS rendered server configurations from the specified server.
    This will reload nginx and stop the uwsgi config.
    """
    require('settings', provided_by=[production, staging])

    for service, remote_path in SERVICES:
        with settings(warn_only=True):
            service_name = '%s.%s' % (app_config.PROJECT_SLUG, service)
            file_name = '%s.conf' % service_name

            if service == 'nginx':
                sudo('rm -f %s%s' % (remote_path, file_name))
                sudo('service nginx reload')
            else:
                sudo('service %s stop' % service_name)
                sudo('rm -f %s%s' % (remote_path, file_name))
                sudo('initctl reload-configuration')


def shiva_the_destroyer():
    """
    Deletes the app from s3
    """
    require('settings', provided_by=[production, staging])

    _confirm("You are about to destroy everything deployed to %(settings)s for this project.\nDo you know what you're doing?" % env)

    with settings(warn_only=True):
        s3cmd = 's3cmd del --recursive %s'

        for bucket in env.s3_buckets:
            env.s3_bucket = bucket
            local(s3cmd % ('s3://%(s3_bucket)s/%(project_slug)s' % env))

        if env['deploy_to_servers']:
            run('rm -rf %(path)s' % env)

            if env['deploy_crontab']:
                uninstall_crontab()

            if env['deploy_services']:
                nuke_confs()
