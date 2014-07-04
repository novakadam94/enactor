#
# Copyright (C) 2014 MTA SZTAKI
#

__all__ = ['Enactor']

import itertools as it
from instructions import *

flattened = it.chain.from_iterable

class Enactor(object):
    def __init__(self, infrastructure_id, infobroker, infraprocessor, **config):
        self.infra_id = infrastructure_id
        self.infobroker = infobroker
        self.infraprocessor = infraprocessor
    def get_static_description(self, infra_id):
        return self.infobroker.get('infrastructure.static_description',
                                   infra_id=infra_id)
    def acquire_dynamic_state(self, infra_id):
        return self.infobroker.get('infrastructure.state', infra_id=infra_id)
    def calc_target(self, node):
        # Should set defaults upon loading
        node.setdefault('scaling', dict(min=1, max=1))
        node['scaling'].setdefault('min', 1)
        return node['scaling']['min']
    def select_nodes_to_drop(self, existing, dropcount):
        # Select last <dropcount> nodes to be dropped
        return existing[-dropcount:]
    def gen_bootstrap_instructions(self, infra_id):
        if not self.infobroker.get('infrastructure.started', infra_id=infra_id):
            yield IPCreateEnvironment(environment_id=infra_id)
    def calculate_delta(self, static_description, dynamic_state):
        infra_id = static_description.infra_id

        def mk_instructions(fun, nodelist):
            return flattened(
                fun(node,
                    existing=dynamic_state[node['name']],
                    target=self.calc_target(node))
                for node in nodelist)
        def mkdelinst(node, existing, target):
            exst_count = len(existing)
            if target < exst_count:
                return (IPDropNode(node_id=node_id)
                        for node_id in self.select_nodes_to_drop(
                                existing, exst_count - target))
            return []
        def mkcrinst(node, existing, target):
            exst_count = len(existing)
            if target > exst_count:
                return (IPStartNode(node=node) for i in xrange(target - exst_count))
            return []

        # Create environment if necessary
        yield self.gen_bootstrap_instructions(infra_id)
        # Drop nodes as necessary
        yield flattened(mk_instructions(mkdelinst, nodelist)
                        for nodelist in static_description.topological_order)
        # Create nodes as necessary
        for nodelist in static_description.topological_order:
            yield mk_instructions(mkcrinst, nodelist)

    def enact_delta(self, delta):
        for iset in delta:
            print '[%s]'%(', '.join('%s'%i for i in iset))

    def make_a_pass(self):
        static_description = self.get_static_description(self.infra_id)
        dynamic_state = self.acquire_dynamic_state(self.infra_id)
        delta = self.calculate_delta(static_description, dynamic_state)
        self.enact_delta(delta)
