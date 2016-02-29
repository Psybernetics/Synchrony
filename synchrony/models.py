# This file implements database models for Synchrony.
import os
import time
import magic
import bcrypt
import hashlib
from io import BytesIO
from sqlalchemy import and_
from synchrony import log, db
from flask import make_response
import sqlalchemy.types as types
from synchrony.controllers.utils import uid, tconv

class BinaryBuffer(types.TypeDecorator):
    """
    Automagically return BytesIO objects for revisions of binaries.
    """
    impl = types.LargeBinary

    def process_bind_param(self, value, dialect):
        if not value: return ''
        return value.getvalue()

    def process_result_value(self, value, dialect):
        return BytesIO(value)

# A table for peers who've got what you've got
sufferer_table = db.Table('sufferers',
    db.Column('rev_id', db.Integer(), db.ForeignKey('revisions.id')),
    db.Column('peer_id', db.Integer(), db.ForeignKey('peers.id'))
)

class Domain(db.Model):
    """
    A Domain is a way of organising relations of resources.
    Domains have resources and those resources have revisions.
    """
    __tablename__ = "domains"
    id            = db.Column(db.Integer(), primary_key=True)
    name          = db.Column(db.String())
    resources     = db.relationship("Resource", backref="domain")
    created       = db.Column(db.DateTime(), default=db.func.now())

    def jsonify(self):
        response = {}
        response['domain']    = self.name
        response['created']   = time.mktime(self.created.timetuple())
        response['resources'] = len(self.resources)
        return response

    def __repr__(self):
        if self.name:
            return '<Domain %s with %i resources>' % \
                (self.name, len(self.resources))
        return "<Domain>"

class Resource(db.Model):
    """
    Resource.path = "/path/to/resource?q=param"
    """
    __tablename__ = "content"
    id            = db.Column(db.Integer(), primary_key=True)
    domain_id     = db.Column(db.Integer(), db.ForeignKey('domains.id'))
    path          = db.Column(db.String())
    created       = db.Column(db.DateTime(), default=db.func.now())
    revisions     = db.relationship("Revision", backref="resource")

    def jsonify(self, with_revisions=False):
        response = {}
        response['path'] = self.path
        response['count'] = len(self.revisions)
        if with_revisions:
            response['revisions'] = [r.jsonify() for r in self.revisions]
        response['created'] = time.mktime(self.created.timetuple())
        return response

    def __repr__(self):
        if self.domain:
            return '<Resource %s%s with %i revisions>' %\
                 (self.domain.name, self.path, len(self.revisions))
        return "<Resource>"

class Revision(db.Model):
    """
    A revision maps to a path on a domain at some point in time, or is an edit.
    Edits may come from local users or select peers.
    """
    __tablename__ = "revisions"
    id            = db.Column(db.Integer(), primary_key=True)
    parent_id     = db.Column(db.Integer(), db.ForeignKey("revisions.id"))
    user_id       = db.Column(db.Integer(), db.ForeignKey('users.id'))
    content_id    = db.Column(db.Integer(), db.ForeignKey('content.id'))
    network_id    = db.Column(db.Integer(), db.ForeignKey("networks.id")) 
    friend_id     = db.Column(db.Integer(), db.ForeignKey("friends.id"))
    created       = db.Column(db.DateTime(), default=db.func.now())
    hash          = db.Column(db.String())
    public        = db.Column(db.Boolean(), default=False) # Publicly available
    sufferers     = db.relationship("Peer", secondary=sufferer_table, backref="revisions")
    content       = db.Column(db.String())
    bcontent      = db.Column(BinaryBuffer(20*1000000000)) # 20gb default limit
    mimetype      = db.Column(db.String())
    size          = db.Column(db.Integer())
    parent        = db.relationship("Revision", backref="edits", remote_side=[id])
    status        = 200

    def jsonify(self):
        res = {}
        res['hash']        = self.hash
        res['created']     = time.mktime(self.created.timetuple())
        res['mimetype']    = self.mimetype
        res['size']        = self.size
        res['public']      = self.public
        if self.user:
            res['user']    = self.user.username
        if self.parent:
            res['parent']  = self.parent.hash
            res['url']     = self.parent.url
        else:
            res['url']     = self.url
        if self.network:
            res['network'] = self.network.name
        return res

    def __repr__(self):
        if self.size and self.created:
            return '<%s by %s %s ago (%i bytes)>' % \
                ("Original " + self.url if not self.parent else "Edited " + self.parent.url,
                self.user.username if self.user else "(no user)",
                tconv(int(time.time()) - int(time.mktime(self.created.timetuple()))),
                self.size)
        return "<Revision>"

    @property
    def url(self):
        url = "%s%s" % (
            self.resource.domain.name if self.resource else "",
            self.resource.path if self.resource else ""
        )
        return url or self.hash

    @property
    def url_hash(self):
        url = "%s%s" % (
            self.resource.domain.name if self.resource else "",
            self.resource.path if self.resource else ""
        )
        return hashlib.sha1(url).hexdigest()

    @property
    def as_response(self):
        response = make_response()
        response.data = self.read()
        response.headers['Content-Type'] = self.mimetype
        response.headers['Content-Hash'] = self.hash
        if self.network:
            response.headers['Overlay-Network'] = self.network.name
        return response

    def add(self, container):
        if hasattr(container, "content"):
            self.get_mimetype(container)
        elif hasattr(container, "stream"):
            self.bcontent = container.stream
            self.mimetype = container.mimetype
        self.hash = hashlib.sha1(self.read()).hexdigest()
        self.size = self.get_size()

    def get_mimetype(self, response=None, overwrite=False):
        m = magic.Magic(flags=magic.MAGIC_MIME_TYPE)

        if not response:
            mimetype = m.id_buffer(self.read(1024))
        else:
            # Add an HTTP response according to its mimetype
            mimetype = m.id_buffer(response.text.encode("utf-8","ignore")[:1024])
            if not "text" in mimetype:
                self.bcontent = BytesIO(response.content)
            else:
                self.content = response.text

        if not self.mimetype or overwrite:
            self.mimetype = mimetype

        return mimetype

    def read(self, l=None):
        if not self.content:
            self.bcontent.seek(0)
            if not l:
                res = self.bcontent.read()
            else:
                res = self.bcontent.read(l)
        else:
            res =  self.content.encode("utf-8", "ignore")[:l]
        return res

    def get_size(self):
        if self.bcontent:
            self.bcontent.seek(0, os.SEEK_END)
            return self.bcontent.tell()
        return len(self.content)

    def save(self, user, domain_name, path):
        if not user or not user.active or not user.can("create_revision"):
            return

        if not self.content and not self.bcontent:
            return

        if not path:
            path = '/'

        # Make sure an entry for the domain exists
        domain = Domain.query.filter_by(name=domain_name).first()
        if not domain:
            domain = Domain(name=domain_name)
            resource = Resource(path=path)
        else:
            resource = Resource.query.filter(
                and_(Resource.domain == domain, Resource.path == path)
            ).first()

        # Gaurantee the resource is known to us
        if not resource:
            resource = Resource(path=path)

        domain.resources.append(resource)

        # Transfer attributes
        self.original = True
        self.size     = self.get_size()
        self.hash     = hashlib.sha1(self.read()).hexdigest()

        # Create relational joins
        user.revisions.append(self)
        resource.revisions.append(self)

        # Add these objects to the db session and commit
        db.session.add(user)
        db.session.add(domain)
        db.session.add(resource)
        db.session.add(self)
        db.session.commit()

class Acl(db.Model):
    """
    An Acl is a coupling between a UserGroup and a Priv defining an access right
    of UserGroup members.

    Example:
    >>> user  = User(name="Luke")
    >>> group = UserGroup(name="Users")
    >>> priv  = Priv(name="edit")
    >>> acl   = Acl()
    >>> acl.priv    = priv
    >>> acl.group   = group
    >>> acl.allowed = True
    >>> group.users.append(user)
    >>> user.can("edit")
    True

    The user only needs to be in one UserGroup with an Acl for "edit" set to True.
    Refer to User.can to see what's going on here.
    """
    __tablename__ = 'acl'
    priv_id  = db.Column(db.Integer(),  db.ForeignKey('privs.id'), primary_key=True)
    group_id = db.Column(db.Integer(),  db.ForeignKey('user_groups.id'), primary_key=True)
    created  = db.Column(db.DateTime(), default=db.func.now())
    allowed  = db.Column(db.Boolean())    
    priv     = db.relationship('Priv', backref="groups")

    def jsonify(self):
        res = {}
        res['allowed'] = self.allowed
        if self.group:
            res['group'] = self.group.name
        if self.priv:
            res['privilege'] = self.priv.name
        if self.created:
            res['created'] = time.mktime(self.created.timetuple())
        return res

    def __repr__(self):
        if not self.priv or not self.group:
            return "<Acl>"
        a = "deny"
        if self.allowed: a = "allow"
        return "<Acl %s/%s:%s>" % (self.group.name, self.priv.name, a)

class Priv(db.Model):
    __tablename__ = 'privs'
    id      = db.Column(db.Integer, primary_key=True)
    name    = db.Column(db.String(20))
    created = db.Column(db.DateTime(), default=db.func.now())

    def __repr__(self):
        return "<Priv %s>" % self.name

    def jsonify(self):
        response =  {'name': self.name}
        if self.groups:
            response['groups'] = [_.jsonify() for _ in self.groups]
        if self.created:
            response['created'] = time.mktime(self.created.timetuple())
        return response

user_groups_joint = db.Table('user_groups_join_table',
    db.Column('group_id', db.Integer(), db.ForeignKey('user_groups.id')),
    db.Column('user_id', db.Integer(), db.ForeignKey('users.id'))
)

class UserGroup(db.Model):
    """
    See controllers.usergroups.init for the default set of ACLs.
    """
    __tablename__ = 'user_groups'
    id        = db.Column(db.Integer, primary_key=True)
    name      = db.Column(db.String(20))
    users     = db.relationship("User", secondary=user_groups_joint, backref="user_groups")
    privs     = db.relationship("Acl", backref="group")
    created   = db.Column(db.DateTime(), default=db.func.now())

    def add_parent(self, parent):
        self.parents.append(parent)

    def add_parents(self, *parents):
        for parent in parents:
            self.add_parent(parent)

    @staticmethod
    def get_by_name(name):
        return Group.query.filter_by(name=name).first()

    def __repr__(self):
        return "<Group %s>" % self.name

    def jsonify(self, with_users=False, with_privs=False):
        response = {'name': self.name}
        if self.created:
            response['created'] = time.mktime(self.created.timetuple())
        if with_users:
            users = []
            for i in self.users: users.append(i.username)
            response['users'] = users
        if with_privs:
            privs = []
            for i in self.privs: privs.append({i.priv.name: i.allowed})
            response['privileges'] = privs
        return response

class User(db.Model):
    """
    A local user account.
    """
    __tablename__ = "users"
    id            = db.Column(db.Integer(), primary_key=True)          # User.uid permits encrypted chat messages to be directed to, eg:
    uid           = db.Column(db.String(), default=uid(short_id=True)) # jk2NTk2NTQzNA @ 1126832256713749902797130149365664841530600157134
    username      = db.Column(db.String())
    password      = db.Column(db.String())
    email         = db.Column(db.String())
    avatar        = db.relationship("Revision", uselist=False)
#    admin         = db.Column(db.Boolean(), default=False)
    public        = db.Column(db.Boolean(), default=False)
    active        = db.Column(db.Boolean(), default=True)
#    can_store     = db.Column(db.Boolean(), default=True)
    created       = db.Column(db.DateTime(), default=db.func.now())
    last_login    = db.Column(db.DateTime(), default=db.func.now())
    friends       = db.relationship("Friend", backref="user")
    sessions      = db.relationship("Session", backref="user")
    revisions     = db.relationship("Revision", backref="user")

    def __init__(self, username, password):
        self.username = username
        self.password = bcrypt.hashpw(
            password.encode(), bcrypt.gensalt(16)
        ).decode()
    
    def verify_password(self, password):
        if bcrypt.hashpw(
            password.encode(), self.password.encode()
        ) == self.password.encode():
            return True
        else:
            return False

    def change_password(self, password):
        self.password = bcrypt.hashpw(
            password.encode(), bcrypt.gensalt(16)
        ).decode()

    def jsonify(self, revision_count=True, groups=False, sessions=False):
        response = {}
        if self.username:
            response['username']        = self.username
            response['uid']             = self.uid
            response['email']           = self.email
            response['active']          = self.active
            response['created']         = time.mktime(self.created.timetuple())
            response['revision_count']  = len(self.revisions)
            if sessions:
                response['sessions']    = [s.jsonify() for s in self.sessions]
            if groups:
                response['user_groups'] = [g.jsonify() for g in self.user_groups]
        return response

    def can(self, priv_name):
        """
        Logs whether a user has an access right and returns True, None or False.

        None here means the user wasn't a member of any groups associated with
        the Priv being queried.
        """
        log_message = "Checking whether %s can %s: " % (self.username, priv_name)
        permission = []
        priv = Priv.query.filter(Priv.name == priv_name).first()
        if priv:
            for r in self.user_groups:
                for p in r.privs:
                    if p.priv_id == priv.id:
                        permission.append(p.allowed)
            if any(permission):
                log(log_message + "Yes.")
                return True
        else:
            log(log_message + "No.")
            return None
        log(log_message + "No.")
        return False

    def __repr__(self):
        if self.username:
            return '<User "%s">' % self.username
        return "<User>"

class Session(db.Model):
    """
    Represents the server side of an HTTP session cookie.
    """
    __tablename__ = "sessions"
    id            = db.Column(db.Integer(), primary_key=True)
    session_id    = db.Column(db.String(), default=uid())
    ip            = db.Column(db.String())
    user_agent    = db.Column(db.String())
    created       = db.Column(db.DateTime(), default=db.func.now())
    user_id       = db.Column(db.Integer(), db.ForeignKey('users.id'))

    def from_request(self, request):
        self.session_id = uid()
        self.ip = request.environ['REMOTE_ADDR']
        self.user_agent = request.user_agent.string

    def jsonify(self):
        response = {}
        if self.created:
            response['ip'] = self.ip
            response['user_agent'] = self.user_agent
            response['created'] = time.mktime(self.created.timetuple())
        return response

class Friend(db.Model):
    """
    Represents a Users' friend by their network/node_id/uid address.
    """
    __tablename__ = "friends"
    id            = db.Column(db.Integer(), primary_key=True)
    user_id       = db.Column(db.Integer(), db.ForeignKey('users.id'))
    peer_id       = db.Column(db.Integer(), db.ForeignKey('peers.id'))
    avatar        = db.relationship("Revision", uselist=False)
    name          = db.Column(db.String())
    received      = db.Column(db.Boolean(), default=None) # Can we set state to "Added"?
    state         = db.Column(db.Integer(), default=0)
    address       = db.Column(db.String())  # network/node_id/uid
    network       = db.Column(db.String())
    node_id       = db.Column(db.String())  # Remote node id
    uid           = db.Column(db.String())  # Remote user id
    ip            = db.Column(db.String())  # Find once, contact any time.
    port          = db.Column(db.Integer())
    created       = db.Column(db.DateTime, default=db.func.now())
    states        = {
                        0: "Uninitialised",
                        1: "Pending",
                        2: "Added",
                        3: "Blocked"
                    }

    def __init__(self, address=""):
        if address.count("/") != 2:
            return
        self.address = address
        self.network, self.node_id, self.uid = address.split("/")
        self.name = self.uid

    def parse_status(self):
        if not self.state:
            return self.states[0]
        return self.states.get(self.state, None)

    def __repr__(self):
        if self.address and self.user:
            return "<Friend of %s %s>" % (self.user.username, self.name)
        return "<Friend>"

    def jsonify(self):
        response = {}
        response['name']     = self.name
        response['status']   = self.parse_status()
        response['address']  = self.address
        response['name']     = self.name
        response['received'] = self.received
        response['ip']       = self.ip
        response['port']     = self.port
        if self.created:
            response['created']  = time.mktime(self.created.timetuple())
        if self.user:
            response['user'] = self.user.username
        return response

class Network(db.Model):
    """
    Represents an overlay network and peers. Used for persisting
    state to the backend database on shutdown and giving the system some sort of
    hysteresis for restarts, removing reliance on scarce bootstrap nodes once
    networks acheive a decent size.
    """
    __tablename__ = "networks"
    id        = db.Column(db.Integer(), primary_key=True)
    name      = db.Column(db.String())
    peers     = db.relationship("Peer", backref="network")
    revisions = db.relationship("Revision", backref="network")
    created   = db.Column(db.DateTime, default=db.func.now())

    def delete(self):
        for peer in self.peers:
            db.session.delete(peer)
        db.session.delete(self)
        db.session.commit()

    def __repr__(self):
        if self.name:
            return "<Network %s with %i peers>" % (self.name, len(self.peers))
        return "<Network>"

    def jsonify(self, with_peers=False):
        response = {}
        response['name']       = self.name
        response['peer_count'] = len(self.peers)
        if with_peers:
            response['peers']  = [p.jsonify() for p in self.peers]
        return response

class Peer(db.Model):
    """
    Represents a cached peer node, including their unique ID,
    public key and altruism rating.

    A peer may rejoin and get a different network identifier, but
    they will probably keep the public/private keypair. This can
    let us update our understanding of who we know by nicknaming friends
    and verifying their signatures.
    """
    __tablename__ = "peers"
    id            = db.Column(db.Integer(), primary_key=True)
    network_id    = db.Column(db.Integer(), db.ForeignKey("networks.id")) 
    node_id       = db.Column(db.String())
    ip            = db.Column(db.String())
    port          = db.Column(db.Integer())
    pubkey        = db.Column(db.String())
    name          = db.Column(db.String())
    trust         = db.Column(db.Float(),    default=0.00)
    friends       = db.relationship("Friend", backref="peer")
    created       = db.Column(db.DateTime(), default=db.func.now())

    def load_node(self, node):
        self.ip       = node.ip
        self.port     = node.port
        self.trust    = node.trust
        self.pubkey   = node.pubkey
        self.long_id  = node.long_id  # Stored as a string

    def jsonify(self):
        response = {}
        response['node']        = [self.long_id, self.ip, self.port]
        response['pubkey']      = self.pubkey
        response['trust']       = self.trust
        if self.network:
            response['network'] = self.network.name
        response['name']        = self.name
        response['created']     = time.mktime(self.created.timetuple())
        return response

    def __repr__(self):
        return "<Peer %s %.2fT>" % \
                (self.name if self.name else self.ip+':'+str(self.port), self.trust)
 
local_subnets = ['127', '10.', '192.168', '172']
