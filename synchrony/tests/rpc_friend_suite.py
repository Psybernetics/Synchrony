"""
Test multiple peers handling calls to RoutingTable.__setitem__
"""
import unittest
from synchrony.controllers import dht
from synchrony.tests.utils import BaseSuite

class TestSuite(BaseSuite):

    peer_amount = 25

    def add_friend(self):
        pass

def run():
    suite = unittest.TestSuite()
    suite.addTest(TestSuite('add_friend'))
    unittest.TextTestRunner(verbosity=2).run(suite)
