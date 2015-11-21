import socket
import requests
import urlparse
from synchrony import app, log, db
from sqlalchemy import and_, desc
from synchrony.models import Domain, Resource, Revision, local_subnets
requests.packages.urllib3.disable_warnings()

def get(url, user_agent, user=None):
    """
    Return a Revision of a url.
    Check for the presence of a URL
     At its original location on the web.
     In the database.
     In the DHT.
    """
    revision = Revision()

    # Ignore for now if the addr is on our LAN, VLAN or localhost.
    url = urlparse.urlparse(url)
    domain = url.netloc
    path = url.path or '/'

    try:    host = socket.gethostbyname(domain)
    except: host = ''

    if host:
        log(host)

#    Making deep assumptions about the future of ipv4 here..
    if any([host.startswith(subnet) for subnet in local_subnets]):
        revision.status = 403
        revision.mimetype = "text"
        revision.data = "We're not currently proxying to local subnets."
        return revision

    # Check the web
    response = None
    try:
        log("Fetching %s from the original domain." % url.geturl())
        response = requests.get(url.geturl(), headers={'User-Agent': user_agent}, 
            timeout=app.config['HTTP_TIMEOUT'])
    except Exception, e:
        log("Error retrieving %s: %s" % (url.geturl(), e.message))
 
    if response:
        revision.add(response)
        if 'content-type' in response.headers:
            revision.mimetype = response.headers['content-type']
            revision.save(user, domain, path)
        return revision

    # Check an overlay network
    if user and user.can("retrieve_from_dht"):
        log("Fetching %s from network \"%s\"." % \
            (url.geturl(), app.routes._default.network))
        revision = app.routes._default[url.netloc + url.path]
        if revision:
            return revision

    # Last but not least, check the database
    domain_from_db = Domain.query.filter_by(name=domain).first()
    rev = Revision.query.filter(
        and_(Revision.original == True,
            Revision.resource.has(domain=domain_from_db),
            Revision.resource.has(path=path))
    ).order_by(desc(Revision.created)).first()
    log(domain_from_db)
    if rev:
        return rev

