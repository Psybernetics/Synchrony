"""
Test multiple peers handling calls to RoutingTable.__setitem__
"""
import unittest
from synchrony.controllers import dht
from synchrony.tests.utils import BaseSuite

class User(object):
    def __init__(self):
        self.username = None
        self.uid      = None

class Friend(object):
    def __init__(self):
        self.address  = None


class TestSuite(BaseSuite):

    peer_amount = 25

    def add_friend(self):
        node_id = str(self.peers[0].node.long_id)
        addr    = "Test Network/%s/foo" % node_id
        self.peers[0].protocol.rpc_add_friend("foo", addr)

    def accept_friend_request(self):
        pass

    def reject_friend_request(self):
        pass
    
    def remove_friend(self):
        pass

def run():
    suite = unittest.TestSuite()
    suite.addTest(TestSuite('add_friend'))
    unittest.TextTestRunner(verbosity=2).run(suite)
