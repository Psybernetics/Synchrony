import os
import json
import gzip
import pytz
import time
import urllib
import gevent
import random
import base64
import hashlib
import logging
import urlparse
import functools 
import miniupnpc
from math import ceil
from copy import deepcopy
from hashlib import sha512
from synchrony import app, db
from functools import partial
from Crypto.Hash import SHA256
from flask_restful import abort
from sqlalchemy import or_, and_
from Crypto.PublicKey import RSA
from multiprocessing import Queue
from cStringIO import StringIO as IO
from datetime import datetime, timedelta
from flask import abort, session, request, after_this_request

def most_recent(items):
    def get_time(item):
        return item.last_modified(timestamp=True)
    items = sorted(items, key=get_time)
    items.reverse()
    return items

def gzipped(f):
    if not app.config['GZIP_HERE']:
        return f

    @functools.wraps(f)
    def view_func(*args, **kwargs):

        @after_this_request
        def zipper(response):
            accept_encoding = request.headers.get('Accept-Encoding', '')

            if 'gzip' not in accept_encoding.lower():
                return response

            response.direct_passthrough = False

            if (response.status_code < 200 or
                response.status_code >= 300 or
                'Content-Encoding' in response.headers):
                return response
            gzip_buffer = IO()
            gzip_file = gzip.GzipFile(mode='wb', fileobj=gzip_buffer)
            gzip_file.write(response.data)
            gzip_file.close()

            response.data = gzip_buffer.getvalue()
            response.headers['Content-Encoding'] = 'gzip'
            response.headers['Vary'] = 'Accept-Encoding'
            response.headers['Content-Length'] = len(response.data.replace(' ',''))

            return response

        return f(*args, **kwargs)

    return view_func

def uid(short_id=False):
    uid = hashlib.sha512(str(datetime.now().microsecond)).hexdigest()
    if short_id:
        return uid[-13:]
    return uid

class Log(object): 
    def __init__(self,program, log_file=None, log_stdout=False): 
        self.program = program 
        self.log = None  
        self.debug = False  
        self.counter = 0
        self.log_file = log_file
        self.formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s', '%d/%m/%Y %H:%M:%S'
        )

        if log_file or log_stdout:
            self.log = logging.getLogger(program)
            self.log.setLevel(logging.DEBUG)

            if log_stdout:
                ch = logging.StreamHandler()
                ch.setLevel(logging.DEBUG)
                ch.setFormatter(self.formatter)
                self.log.addHandler(ch)

            if log_file:
                ch = logging.FileHandler(log_file, 'a')
                ch.setLevel(logging.DEBUG)
                ch.setFormatter(self.formatter)
                self.log.addHandler(ch)

    def add_fh(self, log_file):
        "Attach a FileHandler to the log"
        self.log_file = log_file
        ch = logging.FileHandler(log_file, 'a')
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(self.formatter)
        self.log.addHandler(ch)


    def __call__(self, data, level='info'):
        # Perform log rotation every 50 calls if logfile is 10Mb
        if self.log_file and os.path.exists(self.log_file):
            self.counter += 1
            logsize = 0
            if self.counter >= 50:
                logsize = os.stat(self.log_file).st_size
            if logsize >= 10000000:
                new_file_name = self.log_file +'.'+ time.strftime("%d-%m-%Y-%H%M") + '.gz'
                # destroy current logging filehandler
                self.log.log(30, "Rotating log file...")
                self.log.handlers[1].close()

                # compress current logfile
                f_in = open(self.log_file, 'rb')
                f_out = gzip.open(new_file_name, 'wb')
                f_out.writelines(f_in)
                f_out.close()
                f_in.close()

                # empty the active log
                open(self.log_file, 'w').close()

                # create new logging object
                self.add_fh(self.log_file)

                # announce rotation
                self.log.log(30, "Previous logfile is now %s" % new_file_name)

        if self.log:
            if level == 'debug': level        = 10
            if level == 'info': level        = 20
            if level == 'warning': level    = 30
            if level == 'error': level        = 40
            if level == 'critical': level    = 50
            if (level > 15) or (self.debug):
                self.log.log(level,data)

    def __len__(self):
        return 0

class ServerSentEvent(object):
    def __init__(self, data, event=None, id=None):
        self.data = data
        self.event = event
        self.id = id
        self.desc_map = {
            self.data : "data",
            self.event : "event",
            self.id : "id"
        }

    def encode(self):
        if not self.data:
            return ""
        lines = ["%s: %s" % (v, k) for k, v in self.desc_map.iteritems() if k]
        return "%s\n\n" % "\n".join(lines)

def tconv(seconds):
    minutes, seconds = divmod(seconds, 60)
    hours,   minutes = divmod(minutes, 60)
    days,    hours   = divmod(hours, 24)
    weeks,   days    = divmod(days, 7)
    s=""
    if weeks:
        if weeks == 1:
            s+= "1 week, "
        else:
            s+= "%i weeks, " % (weeks)
    if days:
        if days == 1:
            s+= "1 day, "
        else:
            s+= "%i days, " % (days)
    if hours:
        if hours == 1:
            s+= "1 hour, "
        else:
            s+= "%i hours, " % (hours)
    if minutes:
        if minutes == 1:
            s+= "1 minute"
        else:
            s+= "%i minutes" % (minutes)
    if seconds:
        if len(s) > 0:
            if seconds == 1:
                s+= " and %i second" % (seconds)
            else:
                s+= " and %i seconds" % (seconds)
        else:
            if seconds == 1:
                s+= "1 second"
            else:
                s+= "%i seconds" % (seconds)
    return s

class Pagination(object):
    """
    Mimic a SQLAlchemy Pagination object with a list of data.
    """

    def __init__(self, items, page, per_page):
        self.page        = page
        self.per_page    = per_page
        self.total_count = len(items)
        self.items       = items[(page-1):(page-1+per_page)]


    @property
    def pages(self):
        return int(ceil(self.total_count / float(self.per_page)))

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def next_num(self):
        return self.page +1 if self.has_next else None

    def iter_pages(self, left_edge=2, left_current=2,
                   right_current=5, right_edge=2):
        last = 0
        for num in xrange(1, self.pages + 1):
            if num <= left_edge or \
               (num > self.page - left_current - 1 and \
                num < self.page + right_current) or \
               num > self.pages - right_edge:
                if last + 1 != num:
                    yield None
                yield num
                last = num

def generate_csrf_token():
    if not 'csrf_token' in session.keys(): session['csrf_token'] = uid()
    return session['csrf_token']

def check_csrf(request, token=None):
    if request.method in ['POST', 'PUT']:
        session_token = session.pop('csrf_token', None)
        if not session_token or session_token != request.form.get('csrf_token'):
            abort(403)

def generate_node_id(seed=None):
    """
    Guarantee a 160-bit binary string based on "ip:port:pubkey"
    """
    id = hashlib.sha1(seed).digest()
    if len(str(bin(long(id.encode('hex'), 16))[2:])) != 160:
        return generate_node_id(seed + 'A')
    return id

class OrderedSet(list):
    def push(self, thing):
        if thing in self:
            self.remove(thing)
        self.append(thing)

def forward_port(port):
    """
    Return a boolean denoting whether the port
    was fowarded and the upnp object used to do it.
    """
    upnp = miniupnpc.UPnP()
    upnp.discoverdelay = 200
    upnp.discover()
    try:
        upnp.selectigd()
    except:
        return False, False
    return upnp.addportmapping(
        port, "TCP", upnp.lanaddr, port,
        "Synchrony at %s:%i" % (upnp.lanaddr, port), ""
    ), upnp

def unforward_port(u, port):
    "Take a UPnP client and remove a port mapping with it."
    return u.deleteportmapping(port, "TCP")

def validate_signature(message):
    """
    Take a message from a DHT peer containing a public key and a signature and
    make sure the signature is for the time attribute in the message content.

    The reason for signing the time rather than the entire message is due to
    how the receive side recombines the attributes in a different order.
    """
    assert isinstance(message, dict)
    if not 'signature' in message or not 'pubkey' in message or not 'time' in message:
        return False
    message = deepcopy(message)
    signature = (long(message['signature']),)
    del message['signature']
    hash = SHA256.new(str(message['time'])).digest()
    key = RSA.importKey(message['pubkey'])
    return key.verify(hash, signature)

def exclude(values, to_exclude):
    return filter(lambda x: x if x != to_exclude else 0, values)

def update_url(url, params):
    url_parts = list(urlparse.urlparse(request.url))
    query = dict(urlparse.parse_qsl(url_parts[4]))
    query.update(params)
    url_parts[4] = urllib.urlencode(query)
    return urlparse.urlunparse(url_parts)

def make_response(url, query, jsonify=True):
    """
     Take a paginated SQLAlchemy query and return
     a response that's more easily reasoned about
     by other programs.
    """
    response = {}
    if jsonify:
        response['data'] = [i.jsonify() for i in query.items]   
    else:
        response['data'] = query.items

    response['links'] = {}
    response['links']['self'] = url
    if query.has_next:
        response['links']['next'] = update_url(url, {"page": str(query.next_num)})
    return response

def broadcast(httpd, socket_type, message_type, message, user=None, priv=None):
    """
    Send JSON data to stream users either specifically or by access control.
    """
    for connection in httpd.sockets.values():
        if connection.connected and connection.socket_type == socket_type:
            for c in connection.active_ns.values():
                if not hasattr(c, "socket_type") or c.socket_type != socket_type:
                    continue
                if not hasattr(c, "user"):
                    continue
                if priv and not c.user.can(priv):
                    continue
                if user and c.user.uid != user.uid:
                    continue
                c.emit(message_type, message)

def check_availability(httpd, socket_type, user):
    """
    Return True if the specified user has an active connection to the specified
    socket type, False otherwise.
    """
    for connection in httpd.sockets.values():
        if connection.connected and connection.socket_type == socket_type:
            for c in connection.active_ns.values():
                if not hasattr(c, "socket_type") or c.socket_type != socket_type:
                    continue
                if not hasattr(c, "user"):
                    continue
                if c.user.uid != user.uid:
                    continue
                return True
    return False

def change_channel(httpd, socket_type, user, channel):
    """
    Force a stream user to join an in-stream channel.
    Useful for enabling people to reply to RPC_CHAT messages.
    """
    for connection in httpd.sockets.values():
        if connection.connected and connection.socket_type == socket_type:
            for c in connection.active_ns.values():
                if not hasattr(c, "socket_type") or c.socket_type != socket_type:
                    continue
                if not hasattr(c, "user"):
                    continue
                if user and c.user.uid != user.uid:
                    continue
                print "Joining %s to %s." % (user.username, channel) 
                c.on_join(channel)

