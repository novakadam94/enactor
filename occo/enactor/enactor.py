#
# Copyright (C) 2014 MTA SZTAKI
#

__all__ = ['Enactor']

import itertools as it

flattened = it.chain.from_iterable

class Enactor(object):
    """Maintains a single infrastructure

    infrastructure_id: The identifier of the infrastructure. The description
                       will be acquired from the infobroker.
    infobroker:        The information broker providing information about the
                       infrastructure.
    infraprocessor:    The InfrastructureProcessor that will handle the
                       instructions generated by the Enactor.
    """
    def __init__(self, infrastructure_id, infobroker, infraprocessor, **config):
        self.infra_id = infrastructure_id
        self.infobroker = infobroker
        self.ip = infraprocessor
    def get_static_description(self, infra_id):
        """Acquires the static description of the infrastructure."""
        # This implementation uses the infobroker to do this
        # Alternatively, the description could be stored in self.
        return self.infobroker.get(
            'infrastructure.static_description', infra_id)
    def acquire_dynamic_state(self, infra_id):
        """Acquires the dynamic state of the infrastructure."""
        return self.infobroker.get('infrastructure.state', infra_id)
    def calc_target(self, node):
        """Calculates the target instance count for the given node"""
        # This implementation uses the minimum number of nodes specified.
        # A more sophisticated version could use other information, and/or
        # scaling functions.

        # Should set defaults upon loading
        node.setdefault('scaling', dict(min=1, max=1))
        node['scaling'].setdefault('min', 1)
        return node['scaling']['min']

    def select_nodes_to_drop(self, existing, dropcount):
        """Selects <dropcount> nodes to be dropped form <existing>."""
        # This implementation simply select last nodes to be dropped
        return existing[-dropcount:]
    def gen_bootstrap_instructions(self, infra_id):
        """Generates a list of instructions to bootstrap the infrastructure."""
        # Currently, only the environment needs to be created before the
        # infrastructure is started
        if not self.infobroker.get('infrastructure.started', infra_id):
            yield self.ip.cri_create_env(environment_id=infra_id)
    def calculate_delta(self, static_description, dynamic_state):
        """Calculates a list of instructions to be executed to bring the
        infrastructure in its desired state.

        The result is a list of lists (generator of generators).
        The main result list is called the delta. Each item of the delta
        is a list of instructions that can be executed asynchronously and
        independently of each other. Each such a list pertains to a level of
        the topological ordering of the infrastructure.
        """
        infra_id = static_description.infra_id

        def mk_instructions(fun, nodelist):
            # Creates a list of independent instructions based on a single
            # topological level. The type of instructions will be determined
            # by the logical core function, `fun'.
            return flattened(
                fun(node,
                    existing=dynamic_state[node['name']],
                    target=self.calc_target(node))
                for node in nodelist)
        def mkdelinst(node, existing, target):
            # Creates a list of DropNode instructions, for a single node type,
            # as necessary.
            exst_count = len(existing)
            if target < exst_count:
                return (self.ip.cri_drop_node(node_id=node_id)
                        for node_id in self.select_nodes_to_drop(
                                existing, exst_count - target))
            return []
        def mkcrinst(node, existing, target):
            # Creates a list of StartNode instructions, for each node type,
            # as necessary.
            exst_count = len(existing)
            if target > exst_count:
                return (self.ip.cri_create_node(node=node)
                        for i in xrange(target - exst_count))
            return []

        # Create environment if necessary
        # This is a single list.
        yield self.gen_bootstrap_instructions(infra_id)
        # Drop nodes as necessary
        # Drop instructions are brought together, as they have no dependencies
        # among them.
        yield flattened(mk_instructions(mkdelinst, nodelist)
                        for nodelist in static_description.topological_order)
        # Create nodes as necessary
        # These are multiple lists.
        for nodelist in static_description.topological_order:
            yield mk_instructions(mkcrinst, nodelist)

    def enact_delta(self, delta):
        """Transforms IP instructions into messages, and pushes them to the
        `infraprocessor' backend."""
        for instruction_set in delta:
            instruction_list = list(instruction_set)
            if instruction_list:
                self.ip.push_instructions(instruction_list)

    def make_a_pass(self):
        """Make a maintenance pass on the infrastructure."""
        static_description = self.get_static_description(self.infra_id)
        dynamic_state = self.acquire_dynamic_state(self.infra_id)
        delta = self.calculate_delta(static_description, dynamic_state)
        self.enact_delta(delta)
