#!/usr/bin/env python2
# _*_ coding: utf-8 _*_
import gevent
from gevent.socket import socket
from socketio.server import SocketIOServer

import os
import sys
import pwd
import time
import json
import _socket
import optparse
from synchrony import log, app, init
from synchrony.controllers import dht
from synchrony.tests.maps import maps
from synchrony.models import Revision
from synchrony.controllers import utils

from Crypto import Random
from Crypto.PublicKey import RSA

try:
    import setproctitle
    setproctitle.setproctitle('synchrony')
except ImportError:
    pass

def write_revision_to_disk(options):
    # query for revision by hash
    rev = Revision.query.filter(Revision.hash == options.write).first()
    # query dht for hash
    if not rev:
        rev = app.routes._default[options.write]
    if not rev:
        log("Couldn't find %s locally or via the overlay network." % options.write, "error")
        raise SystemExit
    if not rev.size:
        log("Revision contains no data.", "error")
        raise SystemExit
    output_path = options.out
    if rev.resource and not output_path:
        output_path = rev.resource.path.split('/')[-1]
    if not output_path:
        output_path = options.write
            
    # write to resource name, index.html or options.out.
    if not rev.content:
        fd = open(output_path, 'wb')
    else:
        fd = open(output_path, 'w')
    fd.write(rev.read())
    fd.close()
    log("Wrote %s to disk." % output_path)
    raise SystemExit

def daemon(pidfile):
    """
    Detach from the TTY by reparenting to init.
    """
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0) # parent
    except OSError, e:
        sys.stderr.write("fork #1 failed: %d (%s)\n" % (e.errno, e.strerror))
        sys.exit(-2)
    os.setsid()
    os.umask(0)
    try:
        pid = os.fork()
        if pid > 0:
            try:
                f = file(pidfile, 'w')
                f.write(str(pid))
                f.close()
            except IOError, err:
                log(err,'error')
            sys.exit(0) # parent
    except OSError, e:
        sys.stderr.write("fork #2 failed: %d (%s)\n" % (e.errno, e.strerror))
        sys.exit(-2)
    for fd in (0, 1, 2):
        try:
            os.close(fd)
        except OSError: pass

if __name__ == "__main__":
    epilog = "Available test suites: %s" % ', '.join([test for test in maps.keys()])
    parser = optparse.OptionParser(epilog=epilog)
    parser.add_option("-p", "--port", dest="port", action="store", default=8080, help="(defaults to 8080)")
    parser.add_option("--key", dest="key", action="store", default="id_rsa", help="(defaults to id_rsa)")
    parser.add_option("-c", "--config", dest="config", action="store", default='synchrony.config')
    parser.add_option("-a", "--address", dest="address", action="store", default='0.0.0.0')
    parser.add_option("--stop", dest="stop", action="store_true",default=False)
    parser.add_option("--restart", dest="restart", action="store_true",default=False)
    parser.add_option("--test-suite", dest="test_suite", action="store",default=False)
    parser.add_option("--debug", dest="debug", action="store_true",default=False, help="Enable debugging output.")
#    parser.add_option("--autoreplicate", dest="autoreplicate", action="store", default="2G", help="Automatically replicate peer data.")
    parser.add_option("-w", "--write", dest="write", action="store",default=None, help="Write a revision object (by content hash) to disk. [TEMPERAMENTAL]")
    parser.add_option("-o", "--out", dest="out", action="store",default=None, help="Output path for --write")
    parser.add_option("--pidfile", dest="pidfile", action="store",default='synchrony.pid', help="(defaults to ./synchrony.pid)")
    parser.add_option("--logfile", dest="logfile", action="store",default='synchrony.log', help="(defaults to ./synchrony.log)")
    parser.add_option("--run-as", dest="run_as", action="store",default=None, help="(defaults to the invoking user)")
    parser.add_option("--network", dest="network", action="store", default=None, help="(defaults to \"%s\")" % app.default_network)
    parser.add_option("--bootstrap", dest="bootstrap", action="store", default="synchrony.link:8080", help="(defaults to synchrony.link:8080)")
    parser.add_option("--dont-bootstrap", dest="dont_bootstrap", action="store_true", default=False, help="(don't try to add peers on startup)")
    (options, args) = parser.parse_args()
    options.port    = int(options.port)

    log.add_fh(options.logfile)
    log.debug = options.debug

    if options.stop or options.restart:
        pid = None
        try:
            f = file(options.pidfile, 'r')
            pid = int(f.readline())
            f.close()
            os.unlink(options.pidfile)
        except ValueError, e:
            sys.stderr.write('Error in pid file `%s`. Aborting\n' % options.pidfile)
            sys.exit(-1)
        except IOError, e:
            pass

        if pid:
            os.kill(pid, 15)
        else:
            sys.stderr.write('synchrony not running or no PID file found\n')

        if not options.restart:
            sys.exit(0)

    # Load/generate cryptographic keys
    if os.path.exists(options.key):
        try:
            fd = open(os.path.abspath(options.key), "r")
            log("Loading %s" % os.path.abspath(options.key))
            key = RSA.importKey(fd.read())
            fd.close()            
        except Exception, e:
            log("Error reading %s (%s)" % (options.key, e.message))
            raise SystemExit
    else:
        log("No key found at %s" % os.path.abspath(options.key))
        log("Generating new cryptographic keys.")
        random_generator = Random.new().read
        key = RSA.generate(1024, random_generator)
        fd = open(options.key, "w")
        fd.write(key.exportKey())
        fd.close()
        fd = open(options.key + '.pub', "w")
        fd.write(key.publickey().exportKey())
        fd.close()

    app.key = key

    # Check whether we're just running a test suite
    if options.test_suite:
        if options.test_suite in maps:
            sys.argv = [sys.argv[0]]
            maps[options.test_suite]()
        else:
            print "Unknown suite \"%s\"." % options.test_suite
            print "Available test suites: %s" % ', '.join([test for test in maps.keys()])
        raise SystemExit

    # This call to init writes a database schema and binds API endpoints
    init()

    # Get some nodes to bootstrap in from
    if not options.dont_bootstrap:
        bootstrap_node = options.bootstrap.split(':')
        bootstrap_node[1] = int(bootstrap_node[1])
        app.bootstrap_nodes.extend([tuple(bootstrap_node)])

#    app.debug = options.debug
    sock = (options.address, int(options.port))

    if options.run_as:
        sock = socket(family=_socket.AF_INET)
        try:
            sock.bind((options.address, int(options.port)))
        except _socket.error:
            ex = sys.exc_info()[1]
            strerror = getattr(ex, 'strerror', None)
            if strerror is not None:
                ex.strerror = strerror + ': ' + repr(options.address+':'+options.port)
            raise
        sock.listen(50)
        sock.setblocking(0)
        uid = pwd.getpwnam(options.run_as)[2]
        try:
            os.setuid(uid)
            log("Now running as %s." % options.run_as)
        except Exception, e: raise

    if options.debug:
        app.debug = options.debug
    else:
        sys.tracebacklimit = 0
        daemon(options.pidfile)

    httpd = SocketIOServer(sock, app, resource="stream", policy_server=False)

    # Create a portmapping with UPnP so other nodes can initiate
    # connections to us, then bootstrap and bind to a network interface
    try:
        portmap_success, upnp = utils.forward_port(options.port)
    except:
        portmap_success, upnp = (None, None)

    if not portmap_success:
       log("Couldn't forward port at the gateway.", "warning")
       log("Internet hosts will not be able to initiate connections to us.", "warning")

    try:
        app.routes              = dht.Routers()
        sys.exitfunc            = app.routes.leave_networks

        router = dht.RoutingTable(options, httpd, upnp, nodes=app.bootstrap_nodes) 
        app.routes.append(router)

        # Write any specific revisions to disk now that we have some peers:
        if options.write:
            write_revision_to_disk(options)

        log("Binding to %s:%s" % (options.address, options.port))
        httpd.serve_forever()
    except KeyboardInterrupt:
        # Use sys.exitfunc and trap the sigterm (kill -15) for cleanup.
#        app.routes.leave_network()
        if portmap_success:
            utils.unforward_port(upnp, options.port) 
