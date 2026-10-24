"""Read-only syntax inventory, not a rewrite or a Python alias/liveness proof.

The view interface is explicitly different from a dict. This inventory reports
possible retained roots and JSON calls, without executing code or declaring
them safe, dead, dynamically reached, or removable.
"""
import ast

from return_use_scope import analyze as return_use


def inspect_program(source):
    result = return_use(source)
    tree = ast.parse(source)
    nodes = list(ast.walk(tree))
    parents = {child: node for node in nodes for child in ast.iter_child_nodes(node)}
    target_sites = [site for site in result['sites'] if site['existing_helper_target']]
    positions = {(site['line'], site['column']) for site in target_sites}
    retained = []
    for node in nodes:
        if not isinstance(node, ast.Call) or (node.lineno, node.col_offset) not in positions:
            continue
        assignment = parents.get(node)
        if (not isinstance(assignment, ast.Assign) or assignment.value is not node
                or len(assignment.targets) != 1 or not isinstance(assignment.targets[0], ast.Name)):
            continue
        loop = parents.get(assignment)
        if not isinstance(loop, ast.For) or assignment not in loop.body:
            continue
        name = assignment.targets[0].id
        # Report only a later statement in the same loop body. This is syntax,
        # not a claim that the binding has not been changed between statements.
        for later in loop.body[loop.body.index(assignment)+1:]:
            if (isinstance(later, ast.Assign) and isinstance(later.value, ast.Name)
                    and later.value.id == name):
                for destination in later.targets:
                    if isinstance(destination, ast.Subscript) and isinstance(destination.value, ast.Name):
                        retained.append({'target_line': node.lineno, 'store_line': later.lineno,
                            'same_loop_body': True, 'dynamic_alias_verified': False})
    json_names = {alias.asname or 'json' for node in nodes if isinstance(node, ast.Import)
                  for alias in node.names if alias.name == 'json'}
    json_calls = [{'line': node.lineno, 'column': node.col_offset}
                  for node in nodes if isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Attribute)
                  and isinstance(node.func.value, ast.Name) and node.func.value.id in json_names
                  and node.func.attr in {'dumps', 'dump'}]
    return {'source_sha256': result['source_sha256'], 'ast_nodes': result['ast_nodes'],
        'target_syntax_sites': target_sites, 'container_store_syntax': retained,
        'json_serialization_syntax': json_calls,
        'observations_name_loads': sum(isinstance(node, ast.Name) and node.id == 'observations'
                                      and isinstance(node.ctx, ast.Load) for node in nodes),
        'current_program_hazards': result['current_program_hazards'],
        'bridge_name_non_call_loads': result['bridge_name_non_call_loads'],
        'interface_compatibility_proved': False, 'dynamic_field_demand_established': False,
        'measured_savings': None}


def check_saved_boundary(source, result, wire):
    """Validate saved completion/RPC structure, without replaying any reply."""
    index = source.get('program_index')
    if type(index) is not int or index < 1 or result.get('program_index') != index:
        raise ValueError('saved_program_index_mismatch')
    if not isinstance(source.get('observations'), list) or not isinstance(source.get('api_schemas'), dict):
        raise ValueError('saved_input_shape_mismatch')
    if not wire or wire[-1].get('kind') != 'done' or wire[-1].get('program_index') != index:
        raise ValueError('saved_completion_missing')
    if any(wire[-1].get(k) != result.get(k) for k in ('stdout', 'stdout_truncated', 'error')):
        raise ValueError('saved_completion_differs')
    for number, packet in enumerate(wire[:-1], 1):
        if (packet.get('kind') != 'api' or type(packet.get('id')) is not int
                or packet['id'] != number or packet.get('program_index') != index):
            raise ValueError('saved_rpc_order_differs')
    if result.get('status') not in {'ok', 'execution_error'} or result.get('session_usable') is not True:
        raise ValueError('saved_boundary_not_usable')
    if type(result.get('api_requests')) is not int or not 0 <= result['api_requests'] <= len(wire)-1:
        raise ValueError('saved_api_account_malformed')
    return {'program_index': index, 'status': result['status'], 'session_usable': True,
        'observation_entries': len(source['observations']), 'wire_api_attempts': len(wire)-1,
        'original_api_requests': result['api_requests'], 'saved_boundary_structure_checked': True,
        'runtime_replay_executed': False}
