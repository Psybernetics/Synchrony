from pkgutil import extend_path
__path__ = extend_path(__path__, __name__)
__all__ = ["run", "repl", "models", "resources", "views", "streams", "controllers", "templates", "static", "tests"]

import os
import flask_restful as restful
from flask_sqlalchemy import SQLAlchemy
from flask import Flask, request, make_response
from sqlalchemy.engine.reflection import Inspector
from flask_mako import MakoTemplates, render_template

static_files = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')

prog = "Synchrony"
app  = Flask(prog, static_folder=static_files)
db   = SQLAlchemy(app)
mako = MakoTemplates(app)
api  = restful.Api(app, prefix='/v1')
app.version = "0.0.1"
app.config["HTTP_BASIC_AUTH_REALM"] = "%s %s" % (prog, app.version)

# Define logging here to make it available in views
from synchrony.controllers import utils
log = utils.Log(prog,log_stdout=True)

from synchrony import streams
from synchrony.models import *
from synchrony.views import base
from synchrony.views.maps import maps
from synchrony.controllers.usergroups import init_user_groups

app.public = True
app.config.from_object("synchrony.config")
app.template_folder = os.path.join(os.path.dirname(__file__), 'templates') + os.path.sep

app.default_network = "alpha"

# Keep a record of how much data we've served and received
app.bytes_sent      = 0
app.bytes_received  = 0


@app.before_request
def fence_internet_hosts():
    """
    Relegate hosts connecting over the internet to the /v1/peers endpoint.
    """
    if not request.path.startswith('/v1/peers') and not request.remote_addr[:3] in ['127', '10.', '192']:
        log("%s tried to retrieve %s" % (request.remote_addr, request.path), "warning")
        return make_response("Forbidden.",403)    

# Read/write session cookie HMAC key
secret_key_path = os.path.abspath(os.path.curdir + os.path.sep + ".secret_key")
if not os.path.exists(secret_key_path):
    try:
        fd = open(secret_key_path, "w")
        secret_key = os.urandom(20)
        fd.write(secret_key)
        fd.close()
    except Exception, e:
        log("Error writing secret cookie key to disk: " + e.message)
else:
    try:
        fd = open(secret_key_path, "r")
        secret_key = fd.read()
        fd.close()
    except Exception, e:
        log("Error reading secret cookie key from disk: " + e.message)

app.secret_key = secret_key

# Get peers from the db
app.bootstrap_nodes = []

# Place shared objects on the views
base.BaseView.app = app
for view in maps.values():
    view.db = db
    view.register(app)
    view.log = log

# Use one file and pass the error type into the context.
@app.errorhandler(404)
def page_not_found(e):
    return make_response(render_template('error.html', text="404 - Page not found."), 404)

@app.errorhandler(403)
def forbidden(e):
    return make_response(render_template('error.html', text="403 - Forbidden."), 403)

def init():

    # Create schema
    inspector = Inspector.from_engine(db.engine)
    tables = [table_name for table_name in inspector.get_table_names()]
    if 'synchrony_domains' not in tables:
        db.create_all()

    init_user_groups()

    # Attach HTTP endpoints
    from synchrony.resources import users
    from synchrony.resources import groups
    from synchrony.resources import peers
    from synchrony.resources import domains
    from synchrony.resources import networks
    from synchrony.resources import revisions

    api.add_resource(networks.NetworkCollection,            "/networks")
    api.add_resource(networks.NetworkResource,              "/networks/<string:network>")
    api.add_resource(networks.NetworkPeerCollection,        "/networks/<string:network>/peers")

    api.add_resource(domains.DomainCollection,              "/domains")
    api.add_resource(domains.DomainResource,                "/domains/<domain>")
    api.add_resource(domains.DomainCountResource,           "/domains/count")

    api.add_resource(revisions.RevisionCollection,          "/revisions")
    api.add_resource(revisions.RevisionResource,            "/revisions/<string:hash>")
    api.add_resource(revisions.RevisionContentResource,     "/revisions/<string:hash>/content")
    api.add_resource(revisions.RevisionDownloadsCollection, "/revisions/downloads")
    api.add_resource(revisions.RevisionDownloadsResource,   "/revisions/downloads/<string:network>")
#    api.add_resource(revisions.RevisionFeedbackResource,    "/revisions/downloads/<string:network>/<path:url>")

    api.add_resource(users.UserCollection,                  "/users")
    api.add_resource(users.UserResource,                    "/users/<string:username>")
    api.add_resource(users.UserSessionsResource,            "/users/<string:username>/sessions")
    api.add_resource(users.UserFriendsCollection,           "/users/<string:username>/friends")
    api.add_resource(users.UserRevisionCollection,          "/users/<string:username>/revisions")
    api.add_resource(users.UserRevisionCountResource,       "/users/<string:username>/revisions/count")

    api.add_resource(groups.UserGroupCollection,            "/groups")
    api.add_resource(groups.UserGroupResource,              "/groups/<string:name>")

    api.add_resource(peers.PeerCollection,                  "/peers")
    api.add_resource(peers.PeerNetworkResource,             "/peers/<string:network>")
    api.add_resource(peers.PeerResource,                    "/peers/<string:network>/<int:node_id>")
    api.add_resource(peers.PublicRevisionCollection,        "/peers/revisions")
    api.add_resource(peers.PublicRevisionResource,          "/peers/revisions/<string:content_hash>")

    api.add_resource(peers.PeerTestSet,                     "/peers/test")
    api.add_resource(peers.PeerTestGet,                     "/peers/test/<path:url>")

# /users/username/revisions
# /domains/domain/resources
# /peers/peerid/revisions

